from typing import TypeVar, AsyncIterator, AsyncGenerator

import asyncio


T = TypeVar("T")


def eager_async_iter(
    gen: AsyncIterator[T], max_buffer: int = 0
) -> AsyncGenerator[T, None]:
    """
    Eagerly execute the provided asynchronous iterator in the background in a
    task. Internally buffers up to 'max_buffer' items until requested. If
    max_buffer is zero, an unlimited number items will be buffered.

    Returns an iterator over the iterated values which will wait as needed for
    new items to be generated if none are buffered.
    """
    # A queue to buffer up the iterator values in. Values are wrapped in a
    # 1-tuple and the end of the iteration is indicated by a None.
    buffer: asyncio.Queue[tuple[T] | None] = asyncio.Queue(max_buffer)

    # Execute the iterator eagerly into the buffer
    async def runner() -> None:
        try:
            async for item in gen:
                await buffer.put((item,))
        finally:
            await buffer.put(None)

    runner_task = asyncio.create_task(runner())

    # Iterate from the buffer
    async def receiver() -> AsyncGenerator[T, None]:
        try:
            while True:
                item_tuple = await buffer.get()
                if item_tuple is None:
                    # Will propagate any exception thrown by the runner
                    await runner_task
                    break
                else:
                    yield item_tuple[0]
                    buffer.task_done()
        except:
            runner_task.cancel()
            raise

    return receiver()
