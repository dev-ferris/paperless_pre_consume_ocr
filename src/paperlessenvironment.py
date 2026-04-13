import os
from functools import cached_property
from pathlib import Path
from typing import Any, Dict
import psycopg
from psycopg.rows import dict_row

from exceptions import DatabaseError
from logger import get_logger

logger = get_logger(__name__)


class PaperlessConfig:
    """Database configuration for retrieving OCR settings from Paperless-NGX."""

    __DEFAULT_OCR_CONFIG = {
        'language': 'deu+eng',
        'mode': 'skip',
        'image_dpi': 300,
        'output_type': 'pdf',
        'deskew': True,
        'rotate_pages': True,
        'rotate_pages_threshold': 8.0,
        'color_conversion_strategy': 'LeaveColorUnchanged',
        'max_image_pixels': 178956970,  # Default ocrmypdf limit
    }

    def __init__(self):
        self.host = os.environ.get("PAPERLESS_DBHOST")
        self.port = os.environ.get("PAPERLESS_DBPORT", "5432")
        self.name = os.environ.get("PAPERLESS_DBNAME", "paperless")
        self.user = os.environ.get("PAPERLESS_DBUSER", "paperless")
        self.password = os.environ.get("PAPERLESS_DBPW", "paperless")

        if not self.host:
            raise ValueError("PAPERLESS_DBHOST environment variable is required")

    def get_ocr_config(self) -> Dict[str, Any]:
        """
        Retrieve OCR configuration from the Paperless database, merged on
        top of the built-in defaults.

        Raises:
            DatabaseError: if the database cannot be reached or the query
                fails. Callers are expected to handle this — silently
                falling back to defaults would mask broken setups.
        """
        config: Dict[str, Any] = dict(self.__DEFAULT_OCR_CONFIG)

        conn_str = (
            f"host={self.host} port={self.port} dbname={self.name} "
            f"user={self.user} password={self.password} "
            f"connect_timeout=5"
        )

        logger.info(
            f"Connecting to database ({self.name}) at {self.host}:{self.port} as {self.user}"
        )

        try:
            with psycopg.connect(conn_str, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM paperless_applicationconfiguration WHERE id = %s;",
                        (1,),
                    )
                    result = cur.fetchone()
        except psycopg.Error as e:
            raise DatabaseError(
                f"Failed to read OCR configuration from Paperless database: {e}"
            ) from e

        if not result:
            logger.warning(
                "No OCR configuration row found in database, using defaults"
            )
            return config

        # Merge: defaults are the baseline, DB values override but NULLs
        # from the DB are ignored so they don't blank out a default.
        db_overrides = {k: v for k, v in dict(result).items() if v is not None}
        config.update(db_overrides)
        logger.info(
            f"OCR configuration loaded from database "
            f"({len(db_overrides)} fields override defaults)"
        )
        return config


class PaperlessPaths:
    """Resolve and validate Paperless document paths from environment variables."""

    def __init__(self):
        working_path = os.environ.get("DOCUMENT_WORKING_PATH")

        if not working_path:
            raise ValueError("DOCUMENT_WORKING_PATH environment variable is required")

        self.working = Path(working_path)

        source_path = os.environ.get("DOCUMENT_SOURCE_PATH")
        self.source = Path(source_path) if source_path else None

        self.consume = Path(
            os.environ.get("DOCUMENT_CONSUME_PATH", "/usr/src/paperless/consume")
        )

        if not self.working.exists():
            raise FileNotFoundError(
                f"Document file does not exist: {self.working}"
            )


class PaperlessEnvironment:
    """Class to manage Paperless environment configuration."""

    def __init__(self):
        """Extract and validate environment configuration."""
        self.task_id = os.environ.get("TASK_ID", "paperless")

    @cached_property
    def paths(self) -> PaperlessPaths:
        """Return paths configuration."""
        return PaperlessPaths()

    @cached_property
    def config(self) -> PaperlessConfig:
        """Return OCR/database configuration."""
        return PaperlessConfig()
