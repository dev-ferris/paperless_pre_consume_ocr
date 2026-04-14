"""
Paperless OCR Pre-Processing Script.

Processes documents with OCR before Paperless-NGX consumption to ensure
original documents are searchable without requiring archive files.

Image files are first converted to PDF and placed in the consume folder.
The script then exits with a non-zero code to abort consumption of the
original image, so Paperless picks up the converted PDF instead.
"""

import os
from pathlib import Path

from . import image_converter, ocr
from .environment import Environment, fetch_ocr_config, load_database_config, load_environment
from .exceptions import DatabaseError, FileNotSupported, FileProcessingError
from .logger import get_logger, setup_logging

logger = get_logger(__name__)

# Non-zero exit code to abort consumption of the original image file.
# The converted PDF is placed in the consume folder for separate consumption.
EXIT_IMAGE_CONVERTED = 10


def main() -> int:
    """Main execution function."""
    setup_logging()
    logger.info("Paperless Pre-Consume: Starting OCR processing")

    try:
        env = load_environment()

        suffix = env.paths.working.suffix.lower()
        if suffix in image_converter.SUPPORTED_FORMATS:
            return _handle_image_conversion(env)
        elif suffix in ocr.SUPPORTED_FORMATS:
            return _handle_ocr_processing(env)
        else:
            raise FileNotSupported(f"Unsupported file format: {suffix}")

    except FileNotSupported as e:
        logger.warning(f"File format not supported: {e}")
        return os.EX_OK
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return os.EX_NOINPUT
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return os.EX_CONFIG
    except DatabaseError as e:
        logger.error(f"Database connection failed: {e}")
        return os.EX_CONFIG
    except FileProcessingError as e:
        logger.error(f"File processing failed: {e}")
        return 2
    except Exception:
        logger.exception("Unexpected error occurred")
        return 3


def _handle_image_conversion(env: Environment) -> int:
    """Handle image to PDF conversion phase."""
    logger.info("=== IMAGE CONVERSION PHASE ===")

    pdf_path = image_converter.convert_image_to_pdf(
        env.paths.working,
        env.paths.consume,
    )

    if not pdf_path or not pdf_path.exists():
        raise FileProcessingError(f"PDF conversion failed - output file not found: {pdf_path}")

    logger.info(f"Image successfully converted to PDF: {pdf_path}")

    # Remove the original image from the consume folder so it doesn't
    # keep retriggering the consumer after our non-zero abort.
    _remove_original_image(env.paths.source)

    logger.info("Exiting to allow Paperless to re-consume the PDF")
    return EXIT_IMAGE_CONVERTED


def _remove_original_image(source: Path | None) -> None:
    """
    Delete the original image from the consume folder.

    After image conversion we exit non-zero to abort Paperless's
    consumption of the original, which otherwise leaves the file in
    ``consume/`` forever. ``DOCUMENT_SOURCE_PATH`` is the only env var
    that points at that file (``DOCUMENT_WORKING_PATH`` is a scratch
    copy), so we skip cleanup if it isn't set. Failures are logged but
    never re-raised — the conversion already succeeded.
    """
    if source is None:
        logger.debug("DOCUMENT_SOURCE_PATH not set; skipping original image cleanup")
        return
    try:
        source.unlink(missing_ok=True)
        logger.info(f"Removed original image from consume folder: {source}")
    except OSError as e:
        logger.warning(f"Could not remove original image {source}: {e}")


def _handle_ocr_processing(env: Environment) -> int:
    """Handle OCR processing phase."""
    logger.info("=== OCR PROCESSING PHASE ===")

    db = load_database_config()
    ocr_config = fetch_ocr_config(db)

    logger.info(f"Processing file: {env.paths.working}")
    logger.debug(f"OCR configuration: {ocr_config}")

    result_path = ocr.run_ocr(env.paths.working, ocr_config)

    if not result_path:
        raise FileProcessingError("OCR processing returned no result")

    logger.info("OCR processing completed successfully")
    return 0
