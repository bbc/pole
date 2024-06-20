"""
Simple table formatting utilities.
"""

from shutil import get_terminal_size


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
