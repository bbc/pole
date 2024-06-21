import pytest

import re
from pathlib import Path
from textwrap import dedent

from pole.guess import (
    format_string_uses_none,
    Rule,
    PathTemplateHasTooManyAutoFieldsError,
    PathTemplateUnknownFieldError,
    InvalidPathError,
    parse_rule,
    UnnamedRuleError,
    MissingMatchError,
    InvalidMatchError,
    MissingPathError,
    UnknownRuleOptionsError,
    parse_rule_file,
    RuleNotListError,
    UnknownOptionsError,
    load_rules,
    NoRulesFilesError,
    NoRulesError,
    guess,
)


@pytest.mark.parametrize(
    "format_string, exp",
    [
        # Empty
        ("", False),
        # Uses non-None values
        ("{}", False),
        ("{0}", False),
        ("{two}", False),
        # Uses None values
        ("{1}", True),
        ("{one}", True),
        # Uses a mixture
        ("{}-{}", True),
        ("{0}-{1}", True),
        ("{zero}-{one}", True),
    ],
)
def test_format_string_uses_none(format_string: str, exp: bool) -> None:
    assert (
        format_string_uses_none(
            format_string,
            "0",
            None,
            "2",
            None,
            zero="0",
            one=None,
            two="2",
            three=None,
        )
        == exp
    )


class TestRule:
    @pytest.mark.parametrize(
        "pattern, path",
        [
            # Empty
            (r"", ""),
            # No named captures
            (r"(foo)bar", ""),
            (r"(foo)bar", "whatever"),
            # Named captures used
            (r"(?P<foo>foo)(?P<bar>bar)", "foo/{foo}/bar/{bar}"),
            # Named captures partially used
            (r"(?P<foo>foo)(?P<bar>bar)", "bar/{bar}"),
            (r"(?P<foo>foo)(?P<bar>bar)", "foo/{foo}"),
            # Named captures used more than once
            (r"(?P<foo>foo)(?P<bar>bar)", "bar/{bar}/{bar}"),
            # Named captures unused
            (r"(?P<foo>foo)(?P<bar>bar)", "nothing"),
        ],
    )
    def test_valid_pattern_path(self, pattern: str, path: str) -> None:
        # Sholdn't crash!
        Rule(
            rule_file=Path("example.toml"),
            name="my-rule",
            pattern=re.compile(pattern),
            path_templates=[path],
        )

    def test_too_many_auto_arguments(self) -> None:
        with pytest.raises(PathTemplateHasTooManyAutoFieldsError) as exc_info:
            Rule(
                rule_file=Path("example.toml"),
                name="my-rule",
                pattern=re.compile("(foo)"),
                path_templates=["{}oh{}no{}"],
            )

        assert (
            str(exc_info.value)
            == dedent(
                """
                    path '{}oh{}no{}' in example.toml:my-rule contains more automatic fields (e.g. '{}') than capture groups in match
                """
            ).strip()
        )

    @pytest.mark.parametrize(
        "path, unknown",
        [
            ("{foo}/{missing}", "missing"),
            ("{0}/{1}/{2}", "2"),
        ],
    )
    def test_unknown_fields(self, path: str, unknown: str) -> None:
        with pytest.raises(PathTemplateUnknownFieldError) as exc_info:
            Rule(
                rule_file=Path("example.toml"),
                name="my-rule",
                pattern=re.compile("(?P<foo>foo)"),
                path_templates=[path],
            )

        assert (
            str(exc_info.value)
            == dedent(
                f"""
                    path '{path}' in example.toml:my-rule references unknown field '{unknown}'
                    Hint: Available groups are: 0, 1, foo
                """
            ).strip()
        )

    def test_bad_path(self) -> None:
        with pytest.raises(InvalidPathError) as exc_info:
            Rule(
                rule_file=Path("example.toml"),
                name="my-rule",
                pattern=re.compile("(?P<foo>foo)"),
                path_templates=["{"],
            )

        assert (
            str(exc_info.value)
            == dedent(
                """
                    'path' syntax error in example.toml:my-rule (Single '{' encountered in format string)
                """
            ).strip()
        )

    def test_guess(self) -> None:
        rule = Rule(
            rule_file=Path("example.toml"),
            name="my-rule",
            pattern=re.compile("(?P<foo>fo+)"),
            path_templates=["foo/{foo}", "so/much/{foo}"],
        )

        # Non-matching
        assert list(rule.guess("nope")) == []
        assert list(rule.guess("xfoo")) == []
        assert list(rule.guess("foox")) == []

        # Matching
        assert list(rule.guess("fooo")) == ["foo/fooo", "so/much/fooo"]

    def test_guess_omits_path_with_missing_match(self) -> None:
        rule = Rule(
            rule_file=Path("example.toml"),
            name="my-rule",
            pattern=re.compile("(foo)|(bar)"),
            path_templates=["foo={1}", "bar={2}"],
        )

        # Non-matching
        assert list(rule.guess("foo")) == ["foo=foo"]
        assert list(rule.guess("bar")) == ["bar=bar"]


class TestParseRule:
    def test_no_name(self) -> None:
        with pytest.raises(UnnamedRuleError) as exc_info:
            parse_rule(Path("example.toml"), {})

        assert (
            str(exc_info.value)
            == dedent(
                """
                    rule missing 'name' field in example.toml
                """
            ).strip()
        )

    def test_no_match(self) -> None:
        with pytest.raises(MissingMatchError) as exc_info:
            parse_rule(Path("example.toml"), {"name": "foo"})

        assert (
            str(exc_info.value)
            == dedent(
                """
                    'match' not defined in example.toml:foo
                """
            ).strip()
        )

    def test_bad_match(self) -> None:
        with pytest.raises(InvalidMatchError) as exc_info:
            parse_rule(Path("example.toml"), {"name": "foo", "match": "["})

        assert (
            str(exc_info.value)
            == dedent(
                """
                    invalid match in example.toml:foo (unterminated character set at position 0)
                """
            ).strip()
        )

    def test_missing_path(self) -> None:
        with pytest.raises(MissingPathError) as exc_info:
            parse_rule(Path("example.toml"), {"name": "foo", "match": "."})

        assert (
            str(exc_info.value)
            == dedent(
                """
                    'path' not defined in example.toml:foo
                """
            ).strip()
        )

    def test_extra_options(self) -> None:
        with pytest.raises(UnknownRuleOptionsError) as exc_info:
            parse_rule(
                Path("example.toml"),
                {"name": "foo", "match": ".", "path": "x", "foo": "bar"},
            )

        assert (
            str(exc_info.value)
            == dedent(
                """
                    unknown option foo in example.toml:foo
                """
            ).strip()
        )

    def test_path_template_is_string(self) -> None:
        rule = parse_rule(
            Path("example.toml"),
            {"name": "foo", "match": ".", "path": "foo"},
        )
        assert rule.path_templates == ["foo"]

    def test_path_template_is_list(self) -> None:
        rule = parse_rule(
            Path("example.toml"),
            {"name": "foo", "match": ".", "path": ["foo", "bar"]},
        )
        assert rule.path_templates == ["foo", "bar"]

    def test_key_default(self) -> None:
        rule = parse_rule(
            Path("example.toml"),
            {"name": "foo", "match": ".", "path": "x"},
        )
        assert rule.keys == []

    def test_key_is_str(self) -> None:
        rule = parse_rule(
            Path("example.toml"),
            {"name": "foo", "match": ".", "path": "x", "key": "foo"},
        )
        assert rule.keys == ["foo"]

    def test_key_is_list(self) -> None:
        rule = parse_rule(
            Path("example.toml"),
            {"name": "foo", "match": ".", "path": "x", "key": ["foo", "bar"]},
        )
        assert rule.keys == ["foo", "bar"]

    def test_priority_default(self) -> None:
        rule = parse_rule(
            Path("example.toml"),
            {"name": "foo", "match": ".", "path": "x"},
        )
        assert rule.priority == 0

    def test_priority_set(self) -> None:
        rule = parse_rule(
            Path("example.toml"),
            {"name": "foo", "match": ".", "path": "x", "priority": 100},
        )
        assert rule.priority == 100


class TestParseRuleFile:
    def test_rules_is_dict(self, tmp_path: Path) -> None:
        rule_file = tmp_path / "rules.toml"
        rule_file.write_text("[rule]")

        with pytest.raises(RuleNotListError) as exc_info:
            parse_rule_file(rule_file)

        assert (
            str(exc_info.value)
            == dedent(
                f"""
                    'rule' is not a list in {rule_file}
                    Hint: use [[rule]], not [rule]
                """
            ).strip()
        )

    def test_rules_extra_vars(self, tmp_path: Path) -> None:
        rule_file = tmp_path / "rules.toml"
        rule_file.write_text("foo = 'oops'")

        with pytest.raises(UnknownOptionsError) as exc_info:
            parse_rule_file(rule_file)

        assert (
            str(exc_info.value)
            == dedent(
                f"""
                    invalid option foo in {rule_file}
                """
            ).strip()
        )

    def test_empty(self, tmp_path: Path) -> None:
        rule_file = tmp_path / "rules.toml"
        rule_file.write_text("")

        assert parse_rule_file(rule_file) == []

    def test_some_rules(self, tmp_path: Path) -> None:
        rule_file = tmp_path / "rules.toml"
        rule_file.write_text(
            dedent(
                """
                    [[rule]]
                    name = "foo"
                    match = "."
                    path = "x"

                    [[rule]]
                    name = "bar"
                    match = ".."
                    path = "xx"
                """
            )
        )

        assert [r.name for r in parse_rule_file(rule_file)] == ["foo", "bar"]


class TestLoadRules:
    def test_no_files(self, tmp_path: Path) -> None:
        with pytest.raises(NoRulesFilesError) as exc_info:
            load_rules(tmp_path)

        assert (
            str(exc_info.value)
            == dedent(
                f"""
                    no *.toml rule files found in {tmp_path}
                """
            ).strip()
        )

    def test_no_rules(self, tmp_path: Path) -> None:
        (tmp_path / "empty.toml").touch()

        with pytest.raises(NoRulesError) as exc_info:
            load_rules(tmp_path)

        assert (
            str(exc_info.value)
            == dedent(
                f"""
                    no rule definitions found inside any of the *.toml files in {tmp_path}
                """
            ).strip()
        )

    def test_ordering(self, tmp_path: Path) -> None:
        (tmp_path / "20.toml").write_text(
            dedent(
                """
                    # Higher priority file, trumped only by higher priority.

                    [[rule]]
                    name = "second"
                    match = "."
                    path = "."

                    [[rule]]
                    name = "third"
                    match = "."
                    path = "."
                """
            )
        )
        (tmp_path / "10.toml").write_text(
            dedent(
                """
                    # Lower priority file, unless priority set high, the rules
                    # here go last

                    [[rule]]
                    name = "first"
                    match = "."
                    path = "."
                    priority = 100

                    [[rule]]
                    name = "fourth"
                    match = "."
                    path = "."
                """
            )
        )

        rules = load_rules(tmp_path)

        assert [r.name for r in rules] == [
            "first",
            "second",
            "third",
            "fourth",
        ]


def test_guess(tmp_path: Path) -> None:
    (tmp_path / "example.toml").write_text(
        dedent(
            """
                [[rule]]
                name = "foo"
                match = "(?P<match>.)"
                path = ["foo", "foo/{match}"]
                key = "x"

                [[rule]]
                name = "bar"
                match = "(?P<match>.)"
                path = ["bar", "bar/{match}"]

                [[rule]]
                name = "baz"
                match = "(?P<match>..)"
                path = ["baz", "baz/{match}"]
            """
        )
    )

    assert list(guess(tmp_path, ["x", "xx"])) == [
        # First hint's results first
        ("foo", ["x"]),
        ("foo/x", ["x"]),
        ("bar", []),
        ("bar/x", []),
        # Then second hint
        ("baz", []),
        ("baz/xx", []),
    ]
