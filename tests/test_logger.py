"""Tests for ``app.services.logger``: level selection, disabling and idempotency.

``logging.basicConfig`` is replaced with a mock in every test. Under pytest the
root logger already carries the capture handlers, which makes the real
``basicConfig`` a silent no-op; the mock lets the tests assert on how it was
called instead.
"""

import logging
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from app.services import logger as logger_module


@pytest.fixture(autouse=True)
def clean_logging(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    """Resets the module flag, clears the env vars and mocks ``basicConfig``.

    The root logger's level is restored afterwards, as are any ``NullHandler``
    instances the code under test added.
    """
    monkeypatch.delenv("LOGGING", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setattr(logger_module, "_logging_configured", False)

    basic_config = MagicMock(name="basicConfig")
    monkeypatch.setattr(logging, "basicConfig", basic_config)

    root = logging.getLogger()
    saved_level = root.level
    saved_handlers = list(root.handlers)

    yield basic_config

    root.setLevel(saved_level)
    for handler in list(root.handlers):
        if handler not in saved_handlers and isinstance(handler, logging.NullHandler):
            root.removeHandler(handler)


def test_get_logger_returns_named_logger() -> None:
    logger = logger_module.get_logger("bajaninsider.test")

    assert isinstance(logger, logging.Logger)
    assert logger is logging.getLogger("bajaninsider.test")


def test_defaults_to_info_when_log_level_unset(clean_logging: MagicMock) -> None:
    logger_module.get_logger(__name__)

    clean_logging.assert_called_once()
    assert clean_logging.call_args.kwargs["level"] == logging.INFO
    assert logging.getLogger().level == logging.INFO


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("debug", logging.DEBUG),
        ("Info", logging.INFO),
        ("WARNING", logging.WARNING),
        ("error", logging.ERROR),
        ("  Warning  ", logging.WARNING),
    ],
)
def test_level_comes_from_log_level_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
    clean_logging: MagicMock,
    value: str,
    expected: int,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", value)

    logger_module.get_logger(__name__)

    clean_logging.assert_called_once()
    assert clean_logging.call_args.kwargs["level"] == expected
    assert logging.getLogger().level == expected


def test_invalid_log_level_falls_back_to_info_with_warning(
    monkeypatch: pytest.MonkeyPatch,
    clean_logging: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "verbose")

    # No ``caplog.at_level`` here: it would restore the root level on exit and
    # mask the level the code under test sets.
    logger_module.get_logger(__name__)

    assert clean_logging.call_args.kwargs["level"] == logging.INFO
    assert logging.getLogger().level == logging.INFO
    assert "Invalid LOG_LEVEL 'verbose'" in caplog.text


@pytest.mark.parametrize("value", ["0", "false", "False", "no", "OFF", " off "])
def test_logging_env_var_disables_configuration(
    monkeypatch: pytest.MonkeyPatch, clean_logging: MagicMock, value: str
) -> None:
    monkeypatch.setenv("LOGGING", value)
    root_level_before = logging.getLogger().level

    logger = logger_module.get_logger(__name__)

    clean_logging.assert_not_called()
    assert logging.getLogger().level == root_level_before
    assert isinstance(logger, logging.Logger)


def test_disabled_logging_installs_null_handler_on_bare_root(
    monkeypatch: pytest.MonkeyPatch, clean_logging: MagicMock
) -> None:
    """Outside pytest the root logger has no handlers; disabling must not leave
    Python's last-resort stderr handler in charge."""
    monkeypatch.setenv("LOGGING", "false")
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])

    logger_module.get_logger(__name__)

    clean_logging.assert_not_called()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], logging.NullHandler)


@pytest.mark.parametrize("value", ["true", "1", "yes", "anything"])
def test_other_logging_values_keep_logging_enabled(
    monkeypatch: pytest.MonkeyPatch, clean_logging: MagicMock, value: str
) -> None:
    monkeypatch.setenv("LOGGING", value)

    logger_module.get_logger(__name__)

    clean_logging.assert_called_once()


def test_configuration_happens_only_once(
    monkeypatch: pytest.MonkeyPatch, clean_logging: MagicMock
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")
    logger_module.get_logger("first")

    monkeypatch.setenv("LOG_LEVEL", "error")
    logger_module.get_logger("second")
    logger_module.configure_logging()

    clean_logging.assert_called_once()
    assert clean_logging.call_args.kwargs["level"] == logging.DEBUG
    assert logging.getLogger().level == logging.DEBUG
