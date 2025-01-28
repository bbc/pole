"""
Utilities for working with the system clipboard.
"""

from typing import AsyncIterator, Union

import asyncio
from contextlib import asynccontextmanager

import pyperclip  # type: ignore


async def copy(value: Union[str, tuple[str, ...]]) -> tuple[str, ...]:
    """
    Copy a value to the clipboard.

    On platforms with a primary and secondary clipboard (e.g. X11), attempts to
    copy to the primary (middle-click) and system clipboards.

    A 1-tuple is treated the same way as passing a string.

    A 2-tuple is treated as a (primary, system) pair to set the system and
    primary cliboards to. If the system only has a single clipboard, the
    primary value will be set instead.

    Returns the copied value as a tuple. This is a 1-tuple if the system has
    just one clipboard or a 2-tuple if it has a primary and secondary.
    """
    copy, _paste = await asyncio.to_thread(pyperclip.determine_clipboard)

    if isinstance(value, str):
        value = (value,)
    if len(value) == 1:
        value = (value[0], value[0])

    primary_value, system_value = value

    try:
        await asyncio.to_thread(lambda: copy(primary_value, primary=True))
        await asyncio.to_thread(lambda: copy(system_value, primary=False))
        return (primary_value, system_value)
    except TypeError:
        await asyncio.to_thread(copy, primary_value)
        return (primary_value,)


async def paste() -> tuple[str, ...]:
    """
    Return the value in the system's clipboards.

    On platforms with a primary (middle click) and system clipboard, returns
    two values (primary first). Otherwise returns a single value.
    """
    _copy, paste = await asyncio.to_thread(pyperclip.determine_clipboard)
    try:
        return (
            await asyncio.to_thread(lambda: paste(primary=True)),
            await asyncio.to_thread(lambda: paste(primary=False)),
        )
    except TypeError:
        return (await asyncio.to_thread(paste),)


@asynccontextmanager
async def temporarily_copy(value: str) -> AsyncIterator[tuple[str, ...]]:
    """
    A context manager which copies the provided value into the clipboard and
    restores the previous values on leaving the context manager.
    """
    before = await paste()
    try:
        assigned = await copy(value)
        yield before
    finally:
        # Restore clipboard values (unless they've changed, in which case leave
        # them as their changed value)
        current = await paste()
        to_set = tuple(
            before_value if cur_value == assigned_value else cur_value
            for before_value, assigned_value, cur_value in zip(
                before, assigned, current
            )
        )
        await copy(to_set)
