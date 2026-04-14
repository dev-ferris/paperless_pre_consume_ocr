"""
Environment loading and Paperless database configuration.

The public surface is procedural:

* :func:`load_environment` reads filesystem-level settings
  (``TASK_ID``, ``DOCUMENT_*``) and returns a frozen
  :class:`Environment` dataclass.
* :func:`load_database_config` reads ``PAPERLESS_DB*`` and returns a
  :class:`DatabaseConfig`.
* :func:`fetch_ocr_config` queries the Paperless database and merges
  the row over :data:`DEFAULT_OCR_CONFIG`.

Splitting filesystem and database loading lets the image-conversion
path run without ever touching the database — the same behaviour the
old cached-property design delivered, but without a class hierarchy.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import conninfo
from psycopg.rows import dict_row

from .exceptions import DatabaseError
from .logger import get_logger

logger = get_logger(__name__)


DEFAULT_OCR_CONFIG: dict[str, Any] = {
    "language": "deu+eng",
    "mode": "skip",
    "image_dpi": 300,
    "output_type": "pdf",
    "deskew": True,
    "rotate_pages": True,
    "rotate_pages_threshold": 8.0,
    "color_conversion_strategy": "LeaveColorUnchanged",
    "max_image_pixels": 178956970,  # Default ocrmypdf limit
}


@dataclass(frozen=True)
class DatabaseConfig:
    """Connection settings for the Paperless Postgres database."""

    host: str
    port: str = "5432"
    name: str = "paperless"
    user: str = "paperless"
    password: str = "paperless"


@dataclass(frozen=True)
class DocumentPaths:
    """Paths handed to us by Paperless for the current document."""

    working: Path
    consume: Path
    source: Path | None = None


@dataclass(frozen=True)
class Environment:
    """Filesystem-level environment for a single pre-consume run."""

    task_id: str
    paths: DocumentPaths


def load_environment() -> Environment:
    """
    Read filesystem and task settings from the environment.

    Raises:
        ValueError: if ``DOCUMENT_WORKING_PATH`` is missing.
        FileNotFoundError: if ``DOCUMENT_WORKING_PATH`` does not exist.
    """
    return Environment(
        task_id=os.environ.get("TASK_ID", "paperless"),
        paths=_load_document_paths(),
    )


def _load_document_paths() -> DocumentPaths:
    working_env = os.environ.get("DOCUMENT_WORKING_PATH")
    if not working_env:
        raise ValueError("DOCUMENT_WORKING_PATH environment variable is required")

    working = Path(working_env)
    if not working.exists():
        raise FileNotFoundError(f"Document file does not exist: {working}")

    source_env = os.environ.get("DOCUMENT_SOURCE_PATH")
    source = Path(source_env) if source_env else None

    consume = Path(os.environ.get("DOCUMENT_CONSUME_PATH", "/usr/src/paperless/consume"))

    return DocumentPaths(working=working, consume=consume, source=source)


def load_database_config() -> DatabaseConfig:
    """
    Build a :class:`DatabaseConfig` from ``PAPERLESS_DB*`` env vars.

    Raises:
        ValueError: if ``PAPERLESS_DBHOST`` is missing.
    """
    host = os.environ.get("PAPERLESS_DBHOST")
    if not host:
        raise ValueError("PAPERLESS_DBHOST environment variable is required")

    return DatabaseConfig(
        host=host,
        port=os.environ.get("PAPERLESS_DBPORT", "5432"),
        name=os.environ.get("PAPERLESS_DBNAME", "paperless"),
        user=os.environ.get("PAPERLESS_DBUSER", "paperless"),
        password=os.environ.get("PAPERLESS_DBPW", "paperless"),
    )


def fetch_ocr_config(db: DatabaseConfig) -> dict[str, Any]:
    """
    Retrieve OCR configuration from the Paperless database, merged on
    top of the built-in defaults.

    Raises:
        DatabaseError: if the database cannot be reached or the query
            fails. Callers are expected to handle this — silently
            falling back to defaults would mask broken setups.
    """
    config: dict[str, Any] = dict(DEFAULT_OCR_CONFIG)

    conn_str = conninfo.make_conninfo(
        host=db.host,
        port=db.port,
        dbname=db.name,
        user=db.user,
        password=db.password,
        connect_timeout=5,
    )

    logger.info(f"Connecting to database ({db.name}) at {db.host}:{db.port} as {db.user}")

    try:
        with psycopg.connect(conn_str, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM paperless_applicationconfiguration WHERE id = %s;",
                    (1,),
                )
                result = cur.fetchone()
    except psycopg.Error as e:
        raise DatabaseError(f"Failed to read OCR configuration from Paperless database: {e}") from e

    if not result:
        logger.warning("No OCR configuration row found in database, using defaults")
        return config

    # Merge: defaults are the baseline, DB values override but NULLs
    # from the DB are ignored so they don't blank out a default.
    db_overrides = {k: v for k, v in dict(result).items() if v is not None}
    config.update(db_overrides)
    logger.info(
        f"OCR configuration loaded from database ({len(db_overrides)} fields override defaults)"
    )
    return config
