import os
from pathlib import Path
from typing import Any, Dict, Optional
import psycopg
from psycopg.rows import dict_row

# Setup logging
from logger import get_logger
logger = get_logger(__name__)


class PaperlessConfig:
    """Database configuration class."""

    __DEFAULT_OCR_CONFIG = {
            'language': 'deu+eng',
            'mode': 'skip',
            'image_dpi': 300,
            'output_type': 'pdf',
            'deskew': True,
            'rotate_pages': True,
            'rotate_pages_threshold': 8.0,
            'color_conversion_strategy': 'LeaveColorUnchanged',
            'max_image_pixels': 178956970  # Default ocrmypdf limit
        }

    def __init__(self):
        self.host = os.environ.get("PAPERLESS_DBHOST")
        self.port = os.environ.get("PAPERLESS_DBPORT", "5432")
        self.name = os.environ.get("PAPERLESS_DBNAME", "paperless")
        self.user = os.environ.get("PAPERLESS_DBUSER", "paperless")
        self.password = os.environ.get("PAPERLESS_DBPW", "paperless")
            
        # Validation
        if not self.host:
            raise ValueError("PAPERLESS_DBHOST environment variable is required")
        
    def get_ocr_config(self) -> Optional[Dict[str, Any]]:
        """Retrieve OCR configuration from database."""
        try:
            conn_str = (
                f"host={self.host} port={self.port} dbname={self.name}"
                f"user={self.user} password={self.password}"
            )
            
            logger.info(f"Connecting to database ({self.name}) at {self.host}:{self.port} as {self.user}")

            with psycopg.connect(conn_str, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM paperless_applicationconfiguration WHERE id = %s;", 
                        (1,)
                    )

                    result = cur.fetchone()
                    if result:
                        logger.info("OCR configuration loaded from database")
                        return dict(result)
                    else:
                        logger.warning("No OCR configuration found in database, using defaults")
                        return self.__DEFAULT_OCR_CONFIG

        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            logger.info("Using default OCR configuration")
            return self.__DEFAULT_OCR_CONFIG
        

class PaperlessPaths:
    """Environment variables configuration class."""
    
    def __init__(self):
        working_path = os.environ.get("DOCUMENT_WORKING_PATH")

        if not working_path:
            raise ValueError("DOCUMENT_WORKING_PATH environment variable is required")

        self.working = Path(working_path)
        self.source = Path(os.environ.get("DOCUMENT_SOURCE_PATH"))
        self.consume = Path(os.environ.get("DOCUMENT_CONSUME_PATH", "/usr/src/paperless/consume"))

        if not self.working.exists():
            raise FileNotFoundError(f"Document file does not exist: {self.working}")


class PaperlessEnvironment:
    """Class to manage Paperless environment configuration."""
    
    def __init__(self):
        """Extract and validate environment configuration."""
        self.task_id = os.environ.get("TASK_ID", "paperless")

    @property
    def paths(self) -> PaperlessPaths:
        """Return paths configuration."""
        if not hasattr(self, '_paths'):
            self._paths = PaperlessPaths()
        return self._paths
    
    @property
    def config(self) -> PaperlessConfig:
        """Return paths configuration."""
        if not hasattr(self, '_config'):
            self._config = PaperlessConfig()
        return self._config
