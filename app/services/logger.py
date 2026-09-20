"""Application-wide logging configuration.

Logging is enabled by default at ``INFO``. Two environment variables control it:

- ``LOG_LEVEL``: one of ``DEBUG``, ``INFO``, ``WARNING`` or ``ERROR``
  (case-insensitive). An unrecognised value falls back to ``INFO`` and logs a
  warning saying so.
- ``LOGGING``: set to ``0``, ``false``, ``no`` or ``off`` (case-insensitive) to
  disable logging output entirely. Kept for backwards compatibility with the
  previous opt-in flag; any other value (or leaving it unset) enables logging.

Configuration happens at most once per process, on the first ``get_logger``
call.
"""

import logging
import os

_logging_configured = False

_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_DEFAULT_LEVEL = logging.INFO
_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}
_DISABLE_VALUES = frozenset({"0", "false", "no", "off"})


def _logging_disabled() -> bool:
    """Reports whether the ``LOGGING`` environment variable disables logging.

    Returns:
        bool: True when ``LOGGING`` is one of ``0``, ``false``, ``no`` or ``off``.
    """
    return os.getenv("LOGGING", "").strip().lower() in _DISABLE_VALUES


def _resolve_level() -> tuple[int, str | None]:
    """Resolves the log level requested through ``LOG_LEVEL``.

    Returns:
        tuple[int, str | None]: The logging level to use and, when the configured
        value was not recognised, the raw value so the caller can warn about it.
    """
    raw = os.getenv("LOG_LEVEL", "").strip()

    if not raw:
        return _DEFAULT_LEVEL, None

    level = _LEVELS.get(raw.upper())

    if level is None:
        return _DEFAULT_LEVEL, raw

    return level, None


def configure_logging() -> None:
    """Configures the root logger from the environment, at most once per process.

    When logging is disabled a ``NullHandler`` is attached to the root logger so
    that records are swallowed instead of reaching Python's last-resort stderr
    handler. Otherwise ``logging.basicConfig`` is called with the resolved level.
    ``basicConfig`` is a no-op when the root logger already has handlers (for
    example under a test runner), so the level is applied explicitly as well.
    """
    global _logging_configured

    if _logging_configured:
        return

    _logging_configured = True
    root = logging.getLogger()

    if _logging_disabled():
        if not root.handlers:
            root.addHandler(logging.NullHandler())
        return

    level, invalid_value = _resolve_level()

    logging.basicConfig(level=level, format=_LOG_FORMAT)
    root.setLevel(level)

    if invalid_value is not None:
        logging.getLogger(__name__).warning(
            "Invalid LOG_LEVEL %r; expected one of %s. Falling back to INFO.",
            invalid_value,
            ", ".join(_LEVELS),
        )


def get_logger(name: str) -> logging.Logger:
    """Returns a named logger, configuring logging on first use.

    Args:
        name (str): The logger name, conventionally ``__name__`` of the caller.

    Returns:
        logging.Logger: The requested logger.
    """
    configure_logging()
    return logging.getLogger(name)
