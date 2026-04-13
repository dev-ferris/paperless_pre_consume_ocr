import logging
import os

_DEFAULT_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"


def setup_logging(level: str | int | None = None) -> None:
    """
    Configure root logging for the script.

    Should be called once from the program entry point — never as an
    import side effect, so importing this module does not silently
    overwrite a host application's logging setup.

    Args:
        level: Optional log level override. If omitted, the
            ``PAPERLESS_PRE_CONSUME_LOG_LEVEL`` environment variable is
            consulted, defaulting to ``INFO``.
    """
    if level is None:
        level = os.environ.get("PAPERLESS_PRE_CONSUME_LOG_LEVEL", "INFO")

    if isinstance(level, str):
        level = level.upper()

    logging.basicConfig(level=level, format=_DEFAULT_FORMAT)
    # If basicConfig was already called by another component, force the
    # root logger to honour the requested level anyway.
    logging.getLogger().setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger."""
    return logging.getLogger(name)
