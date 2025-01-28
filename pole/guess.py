"""
Logic for guessing secrets from hints using user-defined rules.
"""

from typing import Iterator, Any, Iterable, Optional, Union

import sys
import re
import string
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class GuessError(Exception):
    """Base for all guess-related errors."""


@dataclass
class UnnamedRuleError(GuessError):
    rule_file: Path

    def __str__(self) -> str:
        return f"rule missing 'name' field in {self.rule_file}"


@dataclass
class NoRulesFilesError(GuessError):
    rule_directory: Path

    def __str__(self) -> str:
        return f"no *.toml rule files found in {self.rule_directory}"


@dataclass
class NoRulesError(GuessError):
    rule_directory: Path

    def __str__(self) -> str:
        return f"no rule definitions found inside any of the *.toml files in {self.rule_directory}"


@dataclass
class RuleNotListError(GuessError):
    rule_file: Path

    def __str__(self) -> str:
        return (
            f"'rule' is not a list in {self.rule_file}\n"
            f"Hint: use [[rule]], not [rule]"
        )


@dataclass
class UnknownOptionsError(GuessError):
    rule_file: Path
    options: list[str]

    def __str__(self) -> str:
        return f"invalid option {' and '.join(self.options)} in {self.rule_file}"


@dataclass
class RuleError(GuessError):
    rule_file: Path
    name: str

    def __str__(self) -> str:
        return f"{self.rule_file}:{self.name}"


@dataclass
class PathTemplateHasTooManyAutoFieldsError(RuleError):
    path_template: str

    def __str__(self) -> str:
        source = super().__str__()
        return f"path '{self.path_template}' in {source} contains more automatic fields (e.g. '{{}}') than capture groups in match"


@dataclass
class PathTemplateUnknownFieldError(RuleError):
    rule_file: Path
    name: str
    path_template: str
    field_name: str
    named_groups: set[str]

    def __str__(self) -> str:
        source = super().__str__()
        return (
            f"path '{self.path_template}' in {source} references unknown field '{self.field_name}'\n"
            f"Hint: Available groups are: {', '.join(sorted(self.named_groups))}"
        )


@dataclass
class MissingMatchError(RuleError):
    def __str__(self) -> str:
        source = super().__str__()
        return f"'match' not defined in {source}"


@dataclass
class MissingPathError(RuleError):
    def __str__(self) -> str:
        source = super().__str__()
        return f"'path' not defined in {source}"


@dataclass
class InvalidPathError(RuleError):
    message: str

    def __str__(self) -> str:
        source = super().__str__()
        return f"'path' syntax error in {source} ({self.message})"


@dataclass
class InvalidMatchError(RuleError):
    message: str

    def __str__(self) -> str:
        source = super().__str__()
        return f"invalid match in {source} ({self.message})"


@dataclass
class UnknownRuleOptionsError(RuleError):
    options: list[str]

    def __str__(self) -> str:
        source = super().__str__()
        return f"unknown option {' and '.join(self.options)} in {source}"


def format_string_uses_none(
    format_string: str, *numbered: Optional[str], **named: Optional[str]
) -> bool:
    """
    Given a format string and the associated positional and named format
    values, test whether it references any numbered or named components which
    are defined as None.

    Note: Silently ignores references to non-existant numbered/named fields.
    (It is assumed this check has been done elsewhere).
    """
    # Enumerate numbers/names which are None
    named_none = {name for name, value in named.items() if value is None}
    numbered_none = {
        str(number) for number, value in enumerate(numbered) if value is None
    }
    all_none = named_none | numbered_none

    # Scan for any uses of those
    auto_number = 0
    for _, field_name, _, _ in string.Formatter().parse(format_string):
        if field_name == "":
            if str(auto_number) in all_none:
                return True
            auto_number += 1
        elif field_name is not None and field_name in all_none:
            return True

    return False


@dataclass
class Rule:
    """A rule definition."""

    rule_file: Path
    """File this rule was defined in."""

    name: str
    """Name given to this rule."""

    pattern: re.Pattern
    """The regex which must fully match a hint."""

    path_templates: list[str]
    """
    A (non-empty) series of PEP 3101 (``.format()``) compatible secret path
    templates. These are tried in the provided order until a matching secret is
    found.
    
    These templates have substituted into them the match groups of the
    pattern (given by index or by name). If a path attempts to substitute a
    match group which did not match, it will be skipped.
    """

    keys: list[str] = field(default_factory=list)
    """
    If a secret has more than one key, the first key which appears in this list
    will be picked as the value to copy to the clipboard.
    """

    priority: int = 0
    """The priority score for this rule. Higher numbers mean higher priority."""

    def __post_init__(self):
        # Verify that the path_templates only references groups actually
        # present in the pattern.
        named_groups = set(self.pattern.groupindex)
        # NB: pattern.groups does not count group 0!
        numbered_groups = {str(n) for n in range(self.pattern.groups + 1)}
        all_groups = named_groups | numbered_groups
        for path_template in self.path_templates:
            try:
                num_auto_numbered = 0
                for _, field_name, _, _ in string.Formatter().parse(path_template):
                    # Check there are not too many automatically numbered
                    # fields (e.g. '{}').
                    if field_name == "":
                        num_auto_numbered += 1
                        # NB: pattern.groups does not count group 0!
                        if num_auto_numbered > self.pattern.groups + 1:
                            raise PathTemplateHasTooManyAutoFieldsError(
                                self.rule_file,
                                self.name,
                                path_template,
                            )
                    # Check that all numbered ('{0}') or named ('{foo}') fields
                    # correspond with capture groups
                    elif field_name is not None and field_name not in all_groups:
                        raise PathTemplateUnknownFieldError(
                            self.rule_file,
                            self.name,
                            path_template,
                            field_name,
                            all_groups,
                        )
            except ValueError as exc:
                raise InvalidPathError(self.rule_file, self.name, str(exc))

    def guess(self, hint: str) -> Iterator[str]:
        """
        Return all secret paths guessed by this rule (if any).
        """
        match = self.pattern.fullmatch(hint)
        if match is not None:
            for path_template in self.path_templates:
                if not format_string_uses_none(
                    path_template, match.group(0), *match.groups(), **match.groupdict()
                ):
                    yield path_template.format(
                        match.group(0), *match.groups(), **match.groupdict()
                    )


def parse_rule(rule_file: Path, rule: dict[str, Any]) -> Rule:
    """
    Parse a rule dictionary loaded from a rules file into a Rule.
    """
    rule = rule.copy()

    # Lookup name
    try:
        name = rule.pop("name")
    except KeyError:
        raise UnnamedRuleError(rule_file)

    # Parse match regex
    try:
        pattern = re.compile(rule.pop("match"))
    except KeyError:
        raise MissingMatchError(rule_file, name)
    except re.error as exc:
        raise InvalidMatchError(rule_file, name, str(exc))

    # Get path template(s)
    try:
        path_templates: Union[str, list[str]] = rule.pop("path")
        if isinstance(path_templates, str):
            path_templates = [path_templates]
    except KeyError:
        raise MissingPathError(rule_file, name)

    # Get secret keys
    keys: Union[str, list[str]] = rule.pop("key", [])
    if isinstance(keys, str):
        keys = [keys]

    # Get priority
    priority = int(rule.pop("priority", "0"))

    # Complain about any unrecognised options
    extra_keys = sorted(rule.keys())
    if extra_keys:
        raise UnknownRuleOptionsError(rule_file, name, extra_keys)

    return Rule(
        rule_file=rule_file,
        name=name,
        pattern=pattern,
        path_templates=path_templates,
        keys=keys,
        priority=priority,
    )


def parse_rule_file(rule_file: Path) -> list[Rule]:
    """
    Parse a set of rules from a TOML file
    """
    root = tomllib.load(rule_file.open("rb"))

    # Easy mistake: check rule is a list, not a dict!
    rule_specs = root.pop("rule", [])
    if isinstance(rule_specs, dict):
        raise RuleNotListError(rule_file)

    # Complain about any unrecognised options
    extra_keys = sorted(root.keys())
    if extra_keys:
        raise UnknownOptionsError(rule_file, extra_keys)

    return [parse_rule(rule_file, rule_spec) for rule_spec in rule_specs]


def load_rules(rule_directory: Path) -> list[Rule]:
    """
    Loads all rules from a directory of *.toml files. Returns the rules in
    descending order of priority.

    Priority is based on annotated priority and ties are broken by rule file
    filenames (e.g. to allow `50-foo.toml` style filenames) followed by the
    order in which the rules were listed in the file.
    """
    rules_files = list(rule_directory.glob("*.toml"))
    if not rules_files:
        raise NoRulesFilesError(rule_directory)

    rules = sorted(
        (r for f in rules_files for r in parse_rule_file(f)),
        key=lambda rule: (rule.priority, rule.rule_file),
        reverse=True,
    )

    if not rules:
        raise NoRulesError(rule_directory)

    return rules


def guess(
    rule_directory: Path, hints: Iterable[str]
) -> Iterator[tuple[str, list[str]]]:
    """
    Given one or more hints (in decending order of priority), produce a series
    of sugested secret and key-list pairs, highest priority first.
    """
    rules = load_rules(rule_directory)

    for hint in hints:
        for rule in rules:
            for path in rule.guess(hint):
                yield (path, rule.keys)
