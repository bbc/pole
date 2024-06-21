"""
Simple text-based formatting utilities.
"""

from typing import Generator

from shutil import get_terminal_size
from itertools import zip_longest


def dict_to_table(data: dict[str, str], term_width: int | None = None) -> str:
    r"""
    Produce a string containing an ASCII-art table for the provided dictionary.

    For example ``{"foo": "bar", "baz:" "qux"}`` becomes::

        Key  Value
        ===  =====
        foo  bar
        baz  qux

    The term_width argument is used purely to ensure that the underline under
    the value column heading doesn't exceed the width of the terminal, even if
    extremely long values are in use.

    .. note::

        We deliberately don't do fancy line-wrapping for values so that the
        printed value remains copyable from the terminal (even if it ends up
        crudely split over multiple lines).
    """

    key_width = max(3, max(map(len, data.keys()), default=0))
    value_width = max(5, max(map(len, data.values()), default=0))

    # Clamp value column width to terminal width (used only to limit length of
    # underline.
    if term_width is None:
        term_width = get_terminal_size((80, 10)).columns
    value_width = max(0, min(term_width - key_width - 2, value_width))

    out = f"{'Key':<{key_width}}  Value\n"
    out += ("=" * key_width) + "  " + ("=" * value_width) + "\n"

    for key, value in data.items():
        out += f"{key:<{key_width}}  {value}\n"

    # Don't include trailing newline
    return out[:-1]


class PathsToTrees:
    """
    Incrementally converts a seires of ``/`` separated leaf paths in a
    depth-first traversal order into a text-based visual representation.

    Usage::

        >>> out = ""
        >>> ptt = PathsToTrees()
        >>> out += ptt.push("foo")
        >>> out += ptt.push("bar/baz")
        >>> out += ptt.push("bar/qux")
        >>> out += ptt.push("quo")
        >>> out += ptt.close()
        >>> print(out)
        ├── foo
        ├── bar/
        │   ├── baz
        │   └── qux
        └── quo
    """

    # The last parent path printed by _get_line
    _last_parent: list[str]

    # A single buffered 'path' to be printed (we need to keep a path buffered
    # because how we print a path depends on whether the next path is in the
    # same directory or not!)
    _buffered_path: str | None

    SKP = "│   "
    TEE = "├── "
    END = "└── "

    def __init__(self) -> None:
        self._last_parent = []
        self._buffered_path = None

    def _get_line(self, path: str, next_parents: list[str] | None) -> str:
        """
        Format a given path, with foreknowledge of the parent path of the next
        item in the tree.
        """
        parts = path.split("/")
        name = parts[-1]
        parents = parts[:-1]

        out = ""

        # Print parent directories which we're entering
        printed_parents = []
        for before, now in zip_longest(self._last_parent, parents):
            if now is None:
                break
            printed_parents.append(now)
            if before != now:
                out += self.SKP * (len(printed_parents) - 1)
                out += f"{self.TEE}{printed_parents[-1]}/\n"

        # Print the current path
        out += self.SKP * len(parents)
        if next_parents is not None and parents == next_parents[: len(parents)]:
            out += self.TEE
        else:
            out += self.END
        out += f"{name}\n"

        self._last_parent = parents

        return out

    def push(self, path: str) -> str:
        """
        Given a path, return the next lines to print, including trailing
        newlines.
        """
        out = ""
        if self._buffered_path is not None:
            out = self._get_line(self._buffered_path, path.split("/")[:-1])

        self._buffered_path = path

        return out

    def close(self) -> str:
        """
        After the last path has been passed to :py:meth:`push`, call this
        method to return the remaining lines of output.
        """
        if self._buffered_path is not None:
            return self._get_line(self._buffered_path, None).rstrip("\n")
        else:
            return ""
