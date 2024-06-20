import pytest

from typing import Callable, Iterator, Any

import pyperclip  # type: ignore

from pole.clipboard import (
    copy,
    paste,
    temporarily_copy,
)


class MockSingularClipboard:

    value: str

    def __init__(self) -> None:
        self.value = ""

    def determine_clipboard(self) -> tuple[Callable[[str], None], Callable[[], str]]:
        return (self.copy, self.paste)

    def copy(self, value: str) -> None:
        self.value = value

    def paste(self) -> str:
        return self.value


class MockDoubleClipboard:

    primary_value: str
    system_value: str

    def __init__(self) -> None:
        self.primary_value = ""
        self.system_value = ""

    def determine_clipboard(
        self,
    ) -> tuple[Callable[[str, bool], None], Callable[[bool], str]]:
        return (self.copy, self.paste)

    def copy(self, value: str, primary: bool = False) -> None:
        if primary:
            self.primary_value = value
        else:
            self.system_value = value

    def paste(self, primary: bool = False) -> str:
        if primary:
            return self.primary_value
        else:
            return self.system_value


@pytest.fixture
def mock_singular_clipboard(monkeypatch: Any) -> MockSingularClipboard:
    clipboard = MockSingularClipboard()
    monkeypatch.setattr(pyperclip, "determine_clipboard", clipboard.determine_clipboard)
    return clipboard


@pytest.fixture
def mock_double_clipboard(monkeypatch: Any) -> MockDoubleClipboard:
    clipboard = MockDoubleClipboard()
    monkeypatch.setattr(pyperclip, "determine_clipboard", clipboard.determine_clipboard)
    return clipboard


class TestCopy:
    async def test_singular(
        self, mock_singular_clipboard: MockSingularClipboard
    ) -> None:
        await copy("one")
        assert mock_singular_clipboard.value == "one"

        await copy(("two",))
        assert mock_singular_clipboard.value == "two"

        await copy(("three", "four"))
        assert mock_singular_clipboard.value == "three"

    async def test_double(self, mock_double_clipboard: MockDoubleClipboard) -> None:
        # Given one value should set both clipboards
        await copy("one")
        assert mock_double_clipboard.primary_value == "one"
        assert mock_double_clipboard.system_value == "one"

        await copy(("two",))
        assert mock_double_clipboard.primary_value == "two"
        assert mock_double_clipboard.system_value == "two"

        # Given two values, should set clipboards independently
        await copy(("three", "four"))
        assert mock_double_clipboard.primary_value == "three"
        assert mock_double_clipboard.system_value == "four"


class TestPaste:
    async def test_singular(
        self, mock_singular_clipboard: MockSingularClipboard
    ) -> None:
        mock_singular_clipboard.value = "foobar"
        assert await paste() == ("foobar",)

    async def test_double(self, mock_double_clipboard: MockDoubleClipboard) -> None:
        mock_double_clipboard.primary_value = "primary"
        mock_double_clipboard.system_value = "system"
        assert await paste() == ("primary", "system")


class TestTemporarilyCopy:
    async def test_singular(
        self, mock_singular_clipboard: MockSingularClipboard
    ) -> None:
        mock_singular_clipboard.value = "before"

        async with temporarily_copy("secret") as before:
            assert mock_singular_clipboard.value == "secret"
            assert before == ("before",)

        assert mock_singular_clipboard.value == "before"

    async def test_singular_changed(
        self, mock_singular_clipboard: MockSingularClipboard
    ) -> None:
        mock_singular_clipboard.value = "before"

        async with temporarily_copy("secret") as before:
            mock_singular_clipboard.value = "changed"

        assert mock_singular_clipboard.value == "changed"

    async def test_double(self, mock_double_clipboard: MockDoubleClipboard) -> None:
        mock_double_clipboard.primary_value = "primary"
        mock_double_clipboard.system_value = "system"

        async with temporarily_copy("secret") as before:
            assert mock_double_clipboard.primary_value == "secret"
            assert mock_double_clipboard.system_value == "secret"
            assert before == ("primary", "system")

        assert mock_double_clipboard.primary_value == "primary"
        assert mock_double_clipboard.system_value == "system"

    @pytest.mark.parametrize(
        "change_primary, change_system, exp_primary, exp_system",
        [
            (True, False, "PRIMARY", "system"),
            (False, True, "primary", "SYSTEM"),
            (True, True, "PRIMARY", "SYSTEM"),
        ],
    )
    async def test_double_changed(
        self,
        mock_double_clipboard: MockDoubleClipboard,
        change_primary: bool,
        change_system: bool,
        exp_primary: str,
        exp_system: str,
    ) -> None:
        mock_double_clipboard.primary_value = "primary"
        mock_double_clipboard.system_value = "system"

        async with temporarily_copy("secret") as before:
            if change_primary:
                mock_double_clipboard.primary_value = "PRIMARY"
            if change_system:
                mock_double_clipboard.system_value = "SYSTEM"

        assert mock_double_clipboard.primary_value == exp_primary
        assert mock_double_clipboard.system_value == exp_system
