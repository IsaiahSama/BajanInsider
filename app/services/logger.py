import os
import logging

_logging_configured = False


def get_logger(name: str) -> logging.Logger:
    global _logging_configured
    logger = logging.getLogger(name)

    if os.getenv("LOGGING") and not _logging_configured:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        _logging_configured = True

    return logger
