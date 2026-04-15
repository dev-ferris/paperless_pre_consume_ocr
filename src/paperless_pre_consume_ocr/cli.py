"""
Paperless OCR Pre-Processing Script.

Processes documents with OCR before Paperless-NGX consumption to ensure
original documents are searchable without requiring archive files.

Image files are first converted to PDF and placed in the consume folder.
The script then exits with a non-zero code to abort consumption of the
original image, so Paperless picks up the converted PDF instead.
"""

import os
import shutil
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

    # Dispose of the original image from the consume folder so it
    # doesn't keep retriggering the consumer after our non-zero abort.
    _dispose_original_image(env.paths.source, env.paths.consume)

    logger.info("Exiting to allow Paperless to re-consume the PDF")
    return EXIT_IMAGE_CONVERTED


def _dispose_original_image(source: Path | None, consume: Path) -> None:
    """
    Dispose of the original image from the consume folder.

    After image conversion we exit non-zero to abort Paperless's
    consumption of the original, which otherwise leaves the file in
    ``consume/`` forever. ``DOCUMENT_SOURCE_PATH`` is the only env var
    that points at that file (``DOCUMENT_WORKING_PATH`` is a scratch
    copy), so we skip disposal if it isn't set.

    Behaviour:

    * If ``PAPERLESS_EMPTY_TRASH_DIR`` is set and resolves to an
      existing directory, move the image there.
    * Otherwise (unset, or the configured path doesn't exist), delete
      the image.

    Failures are logged but never re-raised — the conversion already
    succeeded and the PDF is already in the consume folder.
    """
    if source is None:
        logger.debug("DOCUMENT_SOURCE_PATH not set; skipping original image disposal")
        return

    trash_dir = _resolve_trash_dir(consume)

    if trash_dir is not None:
        try:
            destination = _unique_destination(trash_dir, source.name)
            shutil.move(str(source), str(destination))
            logger.info(f"Moved original image to trash: {destination}")
            return
        except OSError as e:
            logger.warning(
                f"Could not move original image {source} to {trash_dir} ({e}); "
                f"falling back to deletion"
            )

    try:
        source.unlink(missing_ok=True)
        logger.info(f"Removed original image from consume folder: {source}")
    except OSError as e:
        logger.warning(f"Could not remove original image {source}: {e}")


def _resolve_trash_dir(consume: Path) -> Path | None:
    """
    Resolve ``PAPERLESS_EMPTY_TRASH_DIR`` to an existing directory.

    Absolute paths are used as-is. Relative paths are resolved first
    against the current working directory (matching Paperless's own
    ``Path.resolve()`` behaviour for this setting), and then, as a
    fallback, against the parent of ``DOCUMENT_CONSUME_PATH`` — which
    is the Paperless base directory in the default layout.

    Returns ``None`` if the env var is unset or no candidate resolves
    to an existing directory.
    """
    raw = os.environ.get("PAPERLESS_EMPTY_TRASH_DIR")
    if not raw:
        return None

    configured = Path(raw)

    if configured.is_absolute():
        candidates = [configured]
    else:
        candidates = [
            configured.resolve(),  # against CWD — matches Paperless's native resolution
            (consume.parent / configured).resolve(),  # against Paperless base dir
        ]

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    tried = ", ".join(str(c) for c in candidates)
    logger.warning(
        f"PAPERLESS_EMPTY_TRASH_DIR={raw!r} does not resolve to an existing "
        f"directory (tried: {tried}); falling back to deletion"
    )
    return None


def _unique_destination(trash_dir: Path, name: str) -> Path:
    """
    Return a destination in ``trash_dir`` that does not already exist.

    If ``trash_dir / name`` is free, it is used directly. Otherwise a
    numeric suffix (``_1``, ``_2``, …) is appended before the file
    extension until a free name is found. After 1000 collisions the
    caller will overwrite the last candidate — at that point something
    is very wrong with the trash folder anyway.
    """
    dest = trash_dir / name
    if not dest.exists():
        return dest
    stem, suffix = Path(name).stem, Path(name).suffix
    for i in range(1, 1000):
        candidate = trash_dir / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    return dest


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
