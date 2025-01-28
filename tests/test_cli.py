import pytest

from typing import Any, AsyncIterator, Union

import asyncio
from unittest.mock import Mock, AsyncMock
from textwrap import dedent
from contextlib import asynccontextmanager
from pathlib import Path
import stat

from hvac import Client
from hvac.api.secrets_engines.kv_v1 import KvV1
from hvac.api.secrets_engines.kv_v2 import KvV2

import pole
from pole import main
from pole import clipboard

from test_vault import vault

SecretsDict = dict[str, dict[str, str]]


@pytest.fixture
def secrets(vault: Client) -> SecretsDict:
    vault.sys.enable_secrets_engine(
        backend_type="kv",
        path="secret/",
        options={"version": "1"},
    )

    secrets = {
        "key_count/one": {"foo": "bar"},
        "key_count/two": {"foo": "bar", "qux": "quo"},
        "key_length/short": {"a": "b"},
        "key_length/long": {"a_long_key_name": "a_quite_long_value_too"},
        "top_level": {"top": "level"},
    }

    for key, values in secrets.items():
        vault.secrets.kv.v1.create_or_update_secret(key, values, mount_point="secret/")

    return secrets


class MockClipboard:

    history: list[Union[str, tuple[str, ...]]]

    def __init__(self) -> None:
        self.history = [("",)]

    async def copy(self, value: Union[str, tuple[str, ...]]) -> None:
        self.history.append(value)

    async def paste(self) -> tuple[str, ...]:
        value = self.history[-1]
        if isinstance(value, str):
            return (value,)
        else:
            return value

    @asynccontextmanager
    async def temporarily_copy(
        self, value: Union[str, tuple[str, ...]]
    ) -> AsyncIterator[tuple[str, ...]]:
        before = await self.paste()
        await self.copy(value)
        try:
            yield before
        finally:
            await self.copy(before)


@pytest.fixture
def mock_clipboard(monkeypatch: Any) -> MockClipboard:
    mc = MockClipboard()

    monkeypatch.setattr(clipboard, "copy", mc.copy)
    monkeypatch.setattr(clipboard, "paste", mc.paste)
    monkeypatch.setattr(clipboard, "temporarily_copy", mc.temporarily_copy)

    return mc


@pytest.fixture
def mock_countdown(monkeypatch: Any) -> AsyncMock:
    countdown = AsyncMock()
    monkeypatch.setattr(pole, "countdown", countdown)
    return countdown


@pytest.fixture
def mock_show_notification(monkeypatch: Any) -> Mock:
    show_notification = Mock()
    monkeypatch.setattr(pole, "show_notification", show_notification)
    return show_notification


class TestLs:
    def test_root(self, secrets: SecretsDict, capsys: Any) -> None:
        main(["ls"])

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                """
                    key_count/
                    key_length/
                    top_level
                """
            ).lstrip()
        )

    def test_subdir(self, secrets: SecretsDict, capsys: Any) -> None:
        main(["ls", "key_count"])

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                """
                    one
                    two
                """
            ).lstrip()
        )

    def test_recursive(self, secrets: SecretsDict, capsys: Any) -> None:
        main(["ls", "--recursive"])

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                """
                    key_count/one
                    key_count/two
                    key_length/long
                    key_length/short
                    top_level
                """
            ).lstrip()
        )


class TestTree:
    def test_root(self, secrets: SecretsDict, capsys: Any) -> None:
        main(["tree"])

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                """
                    /
                    ├── key_count/
                    │   ├── one
                    │   └── two
                    ├── key_length/
                    │   ├── long
                    │   └── short
                    └── top_level
                """
            ).lstrip()
        )

    def test_subdir(self, secrets: SecretsDict, capsys: Any) -> None:
        main(["tree", "key_count"])

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                """
                    key_count/
                    ├── one
                    └── two
                """
            ).lstrip()
        )


class TestGet:
    def test_print_table(self, secrets: SecretsDict, capsys: Any) -> None:
        main(["get", "key_count/two"])

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                """
                    Key  Value
                    ===  =====
                    foo  bar
                    qux  quo
                """
            ).lstrip()
        )

    def test_print_table_single_value(self, secrets: SecretsDict, capsys: Any) -> None:
        main(["get", "key_count/two", "foo"])

        out, err = capsys.readouterr()
        assert err == ""
        assert out == "bar\n"

    def test_print_json(self, secrets: SecretsDict, capsys: Any) -> None:
        main(["get", "key_count/two", "--json"])

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                """
                    {
                      "foo": "bar",
                      "qux": "quo"
                    }
                """
            ).lstrip()
        )

    def test_print_json_single(self, secrets: SecretsDict, capsys: Any) -> None:
        main(["get", "key_count/two", "foo", "--json"])

        out, err = capsys.readouterr()
        assert err == ""
        assert out == '"bar"\n'

    def test_copy_default(
        self,
        secrets: SecretsDict,
        capsys: Any,
        mock_clipboard: MockClipboard,
        mock_countdown: AsyncMock,
    ) -> None:
        main(["get", "key_count/one", "--copy"])
        assert mock_clipboard.history == [("",), "bar", ("",)]

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                """
                    Copied foo value to clipboard!
                    Clipboard cleared.
                """
            ).lstrip()
        )

    def test_copy_specific(
        self,
        secrets: SecretsDict,
        capsys: Any,
        mock_clipboard: MockClipboard,
        mock_countdown: AsyncMock,
    ) -> None:
        main(["get", "key_count/two", "foo", "--copy"])
        assert mock_clipboard.history == [("",), "bar", ("",)]

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                """
                    Copied foo value to clipboard!
                    Clipboard cleared.
                """
            ).lstrip()
        )

    def test_copy_default_custom_timeout(
        self,
        secrets: SecretsDict,
        capsys: Any,
        mock_clipboard: MockClipboard,
        mock_countdown: AsyncMock,
    ) -> None:
        main(["get", "key_count/one", "--copy", "--clear-clipboard-delay", "123"])
        assert mock_countdown.call_args.args[1] == 123

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                """
                    Copied foo value to clipboard!
                    Clipboard cleared.
                """
            ).lstrip()
        )

    def test_copy_default_no_clear(
        self,
        secrets: SecretsDict,
        capsys: Any,
        mock_clipboard: MockClipboard,
        mock_countdown: AsyncMock,
    ) -> None:
        main(["get", "key_count/one", "--copy", "--clear-clipboard-delay", "0"])
        assert mock_clipboard.history == [("",), "bar"]
        assert not mock_countdown.called

        out, err = capsys.readouterr()
        assert err == ""
        assert out == "Copied foo value to clipboard!\n"

    def test_copy_notify(
        self,
        secrets: SecretsDict,
        mock_clipboard: MockClipboard,
        mock_countdown: AsyncMock,
        mock_show_notification: Mock,
    ) -> None:
        main(["get", "key_count/one", "--copy", "--notify"])
        assert [c.args for c in mock_show_notification.mock_calls] == [
            (
                "Secret copied",
                "foo from key_count/one\nClipboard will be cleared in 30 seconds.",
            ),
        ]

    def test_copy_on_ambiguous(
        self,
        secrets: SecretsDict,
        capsys: Any,
        mock_clipboard: MockClipboard,
        mock_countdown: AsyncMock,
        mock_show_notification: Mock,
    ) -> None:
        with pytest.raises(SystemExit):
            main(["get", "key_count/two", "--copy", "--notify"])

        out, err = capsys.readouterr()
        assert out == ""
        assert (
            err
            == dedent(
                """
                    Error: Secret has multiple keys (foo, qux). Pick one.
                """
            ).lstrip()
        )

        assert [c.args for c in mock_show_notification.mock_calls] == [
            (
                "Error: Ambiguous secret",
                "key_count/two has multiple keys",
            ),
        ]

    def test_copy_on_missing_key(
        self,
        secrets: SecretsDict,
        capsys: Any,
        mock_clipboard: MockClipboard,
        mock_countdown: AsyncMock,
        mock_show_notification: Mock,
    ) -> None:
        with pytest.raises(SystemExit):
            main(["get", "key_count/two", "nope", "--copy", "--notify"])

        out, err = capsys.readouterr()
        assert out == ""
        assert (
            err
            == dedent(
                """
                    Error: Unknown key nope, expected one of foo, qux
                """
            ).lstrip()
        )

        assert [c.args for c in mock_show_notification.mock_calls] == [
            (
                "Error: Invalid key",
                "key_count/two does not have key nope",
            ),
        ]

    def test_copy_on_missing_path(
        self,
        secrets: SecretsDict,
        capsys: Any,
        mock_clipboard: MockClipboard,
        mock_countdown: AsyncMock,
        mock_show_notification: Mock,
    ) -> None:
        with pytest.raises(SystemExit):
            main(["get", "nope", "--copy", "--notify"])

        out, err = capsys.readouterr()
        assert out == ""
        assert err.startswith("Error: Invalid path")

        assert [c.args for c in mock_show_notification.mock_calls] == [
            ("Error: Secret does not exist",),
        ]


class TestFzf:
    def test_value_selected(
        self,
        secrets: SecretsDict,
        capsys: Any,
        monkeypatch: Any,
        tmp_path: Path,
    ) -> None:
        # Mock out fzf
        fzf = tmp_path / "fzf"
        fzf.write_text(
            dedent(
                f"""
                    #!/bin/sh
                    while read line; do
                        echo "$line" >> "{tmp_path}/lines"
                    done
                    echo "key_count/two"
                """
            ).lstrip()
        )
        fzf.chmod(fzf.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", str(tmp_path), prepend=":")

        main(["fzf"])

        assert (tmp_path / "lines").read_text().splitlines() == [
            "key_count/one",
            "key_count/two",
            "key_length/long",
            "key_length/short",
            "top_level",
        ]

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                """
                    Selected key_count/two
                    Key  Value
                    ===  =====
                    foo  bar
                    qux  quo
                """
            ).lstrip()
        )

    def test_custom_command(
        self,
        secrets: SecretsDict,
        capsys: Any,
        monkeypatch: Any,
        tmp_path: Path,
    ) -> None:
        cmd = tmp_path / "foobar"
        cmd.write_text(
            dedent(
                f"""
                    #!/bin/sh
                    while read line; do
                        echo "$line" >> "{tmp_path}/lines"
                    done
                    echo "$1" >> "{tmp_path}/search"
                    echo "key_count/two"
                """
            ).lstrip()
        )
        cmd.chmod(cmd.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", str(tmp_path), prepend=":")

        main(
            [
                "fzf",
                "--filter-command",
                "foobar",
                "--filter-command",
                "{search}",
                "foobar",
            ]
        )

        assert (tmp_path / "lines").read_text().splitlines() == [
            "key_count/one",
            "key_count/two",
            "key_length/long",
            "key_length/short",
            "top_level",
        ]
        assert (tmp_path / "search").read_text() == "foobar\n"

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                """
                    Selected key_count/two
                    Key  Value
                    ===  =====
                    foo  bar
                    qux  quo
                """
            ).lstrip()
        )

    def test_value_not_selected(
        self,
        secrets: SecretsDict,
        capsys: Any,
        monkeypatch: Any,
        tmp_path: Path,
    ) -> None:
        # Mock out fzf
        fzf = tmp_path / "fzf"
        fzf.write_text(
            dedent(
                f"""
                    #!/bin/sh
                    exit 1
                """
            ).lstrip()
        )
        fzf.chmod(fzf.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", str(tmp_path), prepend=":")

        with pytest.raises(SystemExit):
            main(["fzf"])

        out, err = capsys.readouterr()
        assert out == ""
        assert (
            err
            == dedent(
                """
                    Error: No secret selected.
                """
            ).lstrip()
        )

    def test_not_installed(
        self,
        secrets: SecretsDict,
        capsys: Any,
        monkeypatch: Any,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("PATH", str(tmp_path))

        with pytest.raises(SystemExit):
            main(["fzf"])

        out, err = capsys.readouterr()
        assert out == ""
        assert (
            err
            == dedent(
                """
                    Error: 'fzf' must be installed to use this feature.
                """
            ).lstrip()
        )


class TestGuess:
    def test_no_rules(
        self,
        secrets: SecretsDict,
        capsys: Any,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(SystemExit):
            main(["guess", "--rules", str(tmp_path), "foobar"])

        out, err = capsys.readouterr()
        assert out == ""
        assert err == f"Error: no *.toml rule files found in {tmp_path}\n"

    @pytest.fixture
    def example_rules(self, tmp_path: Path) -> None:
        rules = tmp_path / "example.toml"
        rules.write_text(
            dedent(
                """
                    [[rule]]
                    name = "Example"
                    match = "example-one"
                    path = ["nope", "key_count/one"]

                    [[rule]]
                    name = "Example, disambiguation"
                    match = "example-two"
                    path = "key_count/two"
                    key = ["nope", "qux"]

                    [[rule]]
                    name = "Example, no disambiguation"
                    match = "no-disambiguation"
                    path = "key_count/two"

                    [[rule]]
                    name = "Example, no disambiguation"
                    match = "no-secret"
                    path = "nope"
                """
            )
        )

    def test_no_matching_rule(
        self,
        secrets: SecretsDict,
        capsys: Any,
        tmp_path: Path,
        mock_show_notification: Mock,
        example_rules: None,
    ) -> None:
        with pytest.raises(SystemExit):
            main(["guess", "--rules", str(tmp_path), "--notify", "foobar"])

        out, err = capsys.readouterr()
        assert out == ""
        assert err == "Error: No rules matched.\n"

        assert [c.args for c in mock_show_notification.mock_calls] == [
            ("Error: No rules matched",),
        ]

    def test_matching_rule(
        self,
        secrets: SecretsDict,
        capsys: Any,
        tmp_path: Path,
        mock_clipboard: MockClipboard,
        mock_countdown: AsyncMock,
        example_rules: None,
    ) -> None:
        main(["guess", "--rules", str(tmp_path), "--notify", "example-one"])

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                f"""
                    Guessed key_count/one
                    Key  Value
                    ===  =====
                    foo  bar
                """
            ).lstrip()
        )

    def test_matching_rule_disamiguated(
        self,
        secrets: SecretsDict,
        capsys: Any,
        tmp_path: Path,
        mock_clipboard: MockClipboard,
        mock_countdown: AsyncMock,
        mock_show_notification: Mock,
        example_rules: None,
    ) -> None:
        main(["guess", "--copy", "--rules", str(tmp_path), "--notify", "example-two"])
        assert mock_clipboard.history[-2] == "quo"

        out, err = capsys.readouterr()
        assert err == ""
        assert (
            out
            == dedent(
                f"""
                    Guessed key_count/two
                    Copied qux value to clipboard!
                    Clipboard cleared.
                """
            ).lstrip()
        )

        assert [c.args for c in mock_show_notification.mock_calls] == [
            (
                "Secret copied",
                "qux from key_count/two\nClipboard will be cleared in 30 seconds.",
            ),
        ]

    def test_matching_rule_missing_disambiguation(
        self,
        secrets: SecretsDict,
        capsys: Any,
        tmp_path: Path,
        mock_clipboard: MockClipboard,
        mock_countdown: AsyncMock,
        mock_show_notification: Mock,
        example_rules: None,
    ) -> None:
        with pytest.raises(SystemExit):
            main(
                [
                    "guess",
                    "--copy",
                    "--rules",
                    str(tmp_path),
                    "--notify",
                    "no-disambiguation",
                ]
            )

        out, err = capsys.readouterr()
        assert out == "Guessed key_count/two\n"
        assert err == "Error: Secret has multiple keys (foo, qux). Pick one.\n"

        assert [c.args for c in mock_show_notification.mock_calls] == [
            ("Error: Ambiguous secret", "key_count/two has multiple keys"),
        ]

    def test_matching_rule_manual_disambiguation(
        self,
        secrets: SecretsDict,
        capsys: Any,
        tmp_path: Path,
        mock_clipboard: MockClipboard,
        mock_countdown: AsyncMock,
        mock_show_notification: Mock,
        example_rules: None,
    ) -> None:
        main(
            [
                "guess",
                "--copy",
                "--rules",
                str(tmp_path),
                "--notify",
                "no-disambiguation",
                "qux",
            ]
        )
        assert mock_clipboard.history[-2] == "quo"

        assert [c.args for c in mock_show_notification.mock_calls] == [
            (
                "Secret copied",
                "qux from key_count/two\nClipboard will be cleared in 30 seconds.",
            ),
        ]

    def test_matching_rule_bad_manual_disambiguation(
        self,
        secrets: SecretsDict,
        capsys: Any,
        tmp_path: Path,
        mock_clipboard: MockClipboard,
        mock_countdown: AsyncMock,
        mock_show_notification: Mock,
        example_rules: None,
    ) -> None:
        with pytest.raises(SystemExit):
            main(
                [
                    "guess",
                    "--copy",
                    "--rules",
                    str(tmp_path),
                    "--notify",
                    "no-disambiguation",
                    "nope",
                ]
            )

        out, err = capsys.readouterr()
        assert out == "Guessed key_count/two\n"
        assert err == "Error: Unknown key nope, expected one of foo, qux\n"

        assert [c.args for c in mock_show_notification.mock_calls] == [
            ("Error: Invalid key", "key_count/two does not have key nope"),
        ]
