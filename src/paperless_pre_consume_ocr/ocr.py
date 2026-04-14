"""
OCR pipeline wrapping ocrmypdf.

The public surface is intentionally procedural — :func:`run_ocr` is
the entry point and :func:`should_perform_ocr` /
:func:`build_ocrmypdf_args` exist so callers (and tests) can inspect
the decisions independently without instantiating a throwaway class.
"""

import logging
import re
from pathlib import Path
from typing import Any

import ocrmypdf

from . import pdf
from .exceptions import FileProcessingError
from .logger import get_logger

logger = get_logger(__name__)

SUPPORTED_FORMATS: frozenset[str] = frozenset({".pdf"})

CONFIG_PARAMS: frozenset[str] = frozenset(
    {
        "output_type",
        "pages",
        "language",
        "mode",
        "image_dpi",
        "unpaper_clean",
        "deskew",
        "rotate_pages",
        "rotate_pages_threshold",
        "max_image_pixels",
        "color_conversion_strategy",
        "user_args",
    }
)

MODE_MAPPING: dict[str, str] = {
    "force": "force_ocr",
    "skip": "skip_text",
    "skip_noarchive": "skip_text",
    "redo": "redo_ocr",
}

LOGGING_VERBOSITY_MAPPING: dict[int, int] = {
    logging.NOTSET: 0,
    logging.DEBUG: 1,
    logging.INFO: 0,
    logging.WARNING: -1,
    logging.ERROR: -1,
    logging.CRITICAL: -1,
}

# Substrings that typically appear in the PDF producer/creator metadata
# of scanners or scanning software and indicate the document is an
# image-only scan that still needs a text layer.
SCANNER_PATTERNS: tuple[str, ...] = (
    r"scan",
    r"scanner",
    r"xerox",
    r"canon",
    r"hp",
    r"epson",
    r"brother",
    r"kyocera",
    r"ricoh",
    r"konica",
)


def _apply_special_configs(args: dict[str, Any], specials: dict[str, Any]) -> None:
    """Fold non-trivial config keys into the ocrmypdf kwargs dict."""
    if specials["pages"] and specials["pages"] > 0:
        args["pages"] = specials["pages"]

    if specials["unpaper_clean"]:
        args[specials["unpaper_clean"]] = True

    if specials["mode"] and specials["mode"] in MODE_MAPPING:
        args[MODE_MAPPING[specials["mode"]]] = True

    # Convert max_image_pixels (px) to ocrmypdf's max_image_mpixels (Mpx).
    # Only forward when the requested limit is at least 1 Mpx; smaller
    # values would round down to 0 which ocrmypdf interprets as
    # "unlimited" — almost certainly not what the user meant. Below
    # 1 Mpx we fall back to ocrmypdf's own default by leaving the
    # argument unset.
    max_pixels = specials["max_image_pixels"]
    if max_pixels and max_pixels >= 1_000_000:
        args["max_image_mpixels"] = max(1, round(max_pixels / 1_000_000))

    if specials["user_args"] and isinstance(specials["user_args"], dict):
        args.update(specials["user_args"])


def build_ocrmypdf_args(file_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Translate a Paperless-style config dict to ocrmypdf kwargs."""
    filtered_config = {k: v for k, v in config.items() if k in CONFIG_PARAMS}

    specials = {
        "pages": filtered_config.pop("pages", 0),
        "unpaper_clean": filtered_config.pop("unpaper_clean", None),
        "mode": filtered_config.pop("mode", None),
        "max_image_pixels": filtered_config.pop("max_image_pixels", 0),
        "user_args": filtered_config.pop("user_args", {}),
    }

    args: dict[str, Any] = {
        "input_file": str(file_path),
        "output_file": str(file_path),
        "use_threads": True,
        "progress_bar": False,
    }
    args.update(filtered_config)
    _apply_special_configs(args, specials)

    return {k: v for k, v in args.items() if v is not None and v != ""}


def _metadata_matches_scanner(metadata: dict[str, Any]) -> bool:
    """Return True if any metadata value contains a scanner signature."""
    for key, value in metadata.items():
        for pattern in SCANNER_PATTERNS:
            if re.search(pattern, str(value), re.IGNORECASE):
                logger.info(f"Scanner signature found in metadata: {key}={value}")
                return True
    return False


def should_perform_ocr(file_path: Path, config: dict[str, Any]) -> bool:
    """Decide whether ``file_path`` needs an OCR pass given ``config``."""
    mode = config.get("mode")

    if mode == "force":
        logger.info("Force OCR enabled in configuration")
        return True

    if not pdf.has_text(file_path):
        logger.info("PDF has no meaningful text, OCR needed")
        return True

    if pdf.check_metadata_pattern(file_path, r"Tesseract|ocrmypdf"):
        logger.info("Document already processed by OCR software")
        return mode == "redo"

    metadata = pdf.get_metadata(file_path)
    if metadata and _metadata_matches_scanner(metadata):
        return True

    logger.info("OCR not needed - PDF already contains text")
    return False


def _configure_ocrmypdf_logging() -> None:
    """Map the module logger's level onto ocrmypdf's Verbosity enum."""
    # ocrmypdf.configure_logging() expects an ocrmypdf.Verbosity enum
    # value, not a bare int.
    verbosity = LOGGING_VERBOSITY_MAPPING.get(logger.level, 0)
    ocrmypdf.configure_logging(
        verbosity=ocrmypdf.Verbosity(verbosity),
        manage_root_logger=False,
    )


def run_ocr(file_path: Path, config: dict[str, Any]) -> Path:
    """
    Run OCR on ``file_path`` in place if needed.

    Returns the path (same as input) and raises
    :class:`FileProcessingError` if ocrmypdf fails or produces an
    empty result.
    """
    try:
        if not should_perform_ocr(file_path, config):
            logger.info("OCR processing not needed")
            return file_path

        args = build_ocrmypdf_args(file_path, config)

        # image_dpi is only relevant for image inputs, not PDFs
        args.pop("image_dpi", None)

        # ocrmypdf >= 16 renamed the first parameter to
        # `input_file_or_options` and accepts it positionally only.
        # Pop input/output file from kwargs and pass them positionally
        # so we stay compatible across ocrmypdf versions.
        input_file = args.pop("input_file")
        output_file = args.pop("output_file")

        logger.info("Starting OCR processing")
        logger.info(f"OCR parameters: {args}")

        _configure_ocrmypdf_logging()
        ocrmypdf.ocr(input_file, output_file, **args)

        logger.info("OCR processing completed successfully")

        if not file_path.exists() or file_path.stat().st_size == 0:
            raise FileProcessingError("OCR processing resulted in empty or missing file")

        return file_path

    except FileProcessingError:
        raise
    except Exception as e:
        logger.error(f"OCR processing failed: {e}")
        raise FileProcessingError(f"OCR processing failed: {e}") from e
