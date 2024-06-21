import pytest

from textwrap import dedent

from pole.text_art import dict_to_table, PathsToTrees


class TestDictToTable:
    def test_empty(self) -> None:
        assert (
            dict_to_table({}, 100)
            == dedent(
                """
                Key  Value
                ===  =====
            """
            ).strip()
        )

    def test_short(self) -> None:
        assert (
            dict_to_table({"a": "A", "be": "B"}, 100)
            == dedent(
                """
                Key  Value
                ===  =====
                a    A
                be   B
            """
            ).strip()
        )

    def test_long(self) -> None:
        assert (
            dict_to_table({"long_key": "long_value", "longer_key": "longer_value"}, 100)
            == dedent(
                """
                Key         Value
                ==========  ============
                long_key    long_value
                longer_key  longer_value
            """
            ).strip()
        )

    def test_longer_than_terminal(self) -> None:
        assert (
            dict_to_table({"long_key": "long_value", "longer_key": "longer_value"}, 15)
            == dedent(
                #   15 chars  #
                ###############
                """
                Key         Value
                ==========  ===
                long_key    long_value
                longer_key  longer_value
            """
            ).strip()
        )

    def test_degenerate_terminal(self) -> None:
        assert (
            dict_to_table({"a": "A"}, 0)
            == dedent(
                """
                Key  Value
                ===  
                a    A
            """
            ).strip()
        )


@pytest.mark.parametrize(
    "paths, exp",
    [
        # Empty
        ([], ""),
        # Top-level only
        (
            ["foo"],
            """
                └── foo
            """,
        ),
        (
            ["foo", "bar"],
            """
                ├── foo
                └── bar
            """,
        ),
        # Nesting
        (
            [
                "foo/bar",
                "foo/baz",
                "foo/qux/deep/one",
                "foo/qux/deep/two",
                "foo/qux/deep/three",
                "foo/quo",
                "top",
            ],
            """
                ├── foo/
                │   ├── bar
                │   ├── baz
                │   ├── qux/
                │   │   ├── deep/
                │   │   │   ├── one
                │   │   │   ├── two
                │   │   │   └── three
                │   └── quo
                └── top
            """,
        ),
    ],
)
def test_paths_to_trees(paths: list[str], exp: str) -> None:
    ptt = PathsToTrees()
    assert "".join(map(ptt.push, paths)) + ptt.close() == dedent(exp).strip()
