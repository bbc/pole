from textwrap import dedent

from pole.tables import dict_to_table


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
