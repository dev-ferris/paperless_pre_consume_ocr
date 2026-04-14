import re
from pathlib import Path
from typing import Any

import pikepdf
from pdfminer.high_level import extract_text

from .logger import get_logger

logger = get_logger(__name__)


def has_text(file_path: Path, min_text_length: int = 1) -> bool:
    """Check if PDF contains extractable text."""
    try:
        text = extract_text(str(file_path), maxpages=3)
        if not text:
            return False

        cleaned_text = re.sub(r"\s+", " ", text.strip())
        if len(cleaned_text) < min_text_length:
            logger.debug(f"Text too short ({len(cleaned_text)} chars): {cleaned_text[:100]}...")
            return False

        printable_ratio = sum(1 for c in cleaned_text if c.isprintable()) / len(cleaned_text)
        if printable_ratio < 0.8:
            logger.debug(f"Text contains too many non-printable characters: {printable_ratio:.2%}")
            return False

        logger.debug(f"PDF contains {len(cleaned_text)} characters of meaningful text")
        return True

    except Exception as e:
        logger.warning(f"Could not extract text from {file_path}: {e}")
        return False


def get_metadata(file_path: Path) -> dict[str, Any] | None:
    """
    Extract metadata from a PDF file.

    Returns a dict mixing built-in keys (``page_count`` int,
    ``pdf_version`` str, ``encrypted`` bool, ``file_size`` int,
    ``modified_time`` float) with PDF docinfo entries (string keys
    and string values), or ``None`` if the file cannot be read.
    """
    if not file_path.exists():
        logger.error(f"File {file_path} does not exist")
        return None

    if file_path.suffix.lower() != ".pdf":
        logger.error(f"File {file_path} is not a PDF document")
        return None

    try:
        with pikepdf.Pdf.open(file_path) as doc:
            stat = file_path.stat()
            metadata: dict[str, Any] = {
                "page_count": len(doc.pages),
                "pdf_version": str(doc.pdf_version),
                "encrypted": doc.is_encrypted,
                "file_size": stat.st_size,
                "modified_time": stat.st_mtime,
            }

            if doc.docinfo:
                metadata.update({str(k): str(v) for k, v in doc.docinfo.items()})

            return metadata

    except Exception as e:
        logger.error(f"Could not read PDF metadata from {file_path}: {e}")
        return None


def check_metadata_pattern(file_path: Path, pattern: str) -> bool:
    """Check if PDF metadata contains a specific pattern."""
    metadata = get_metadata(file_path)
    if not metadata:
        return False

    for key, value in metadata.items():
        logger.debug(f"Metadata: {key} - {value}")
        if re.search(pattern, str(value), re.IGNORECASE):
            return True
    return False
