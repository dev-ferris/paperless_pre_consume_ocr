"""
Image-to-PDF conversion pipeline.

The public entry point is :func:`convert_image_to_pdf`. Image transforms
live in :mod:`image_ops`; this module handles file-format concerns
(which formats we accept, lossless vs. lossy save format, quality
profiles) and the img2pdf wrapping step.
"""

import shutil
import uuid
from pathlib import Path
from typing import Any

import img2pdf
from PIL import Image, UnidentifiedImageError

from . import image_ops
from .exceptions import FileNotSupported, FileProcessingError
from .logger import get_logger

logger = get_logger(__name__)


SUPPORTED_FORMATS: frozenset[str] = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tiff",
        ".tif",
        ".webp",
        ".gif",
        ".ico",
        ".pcx",
        ".ppm",
        ".pgm",
        ".pbm",
    }
)

# Formats saved as PNG to preserve lossless quality.
LOSSLESS_FORMATS: frozenset[str] = frozenset(
    {
        ".png",
        ".bmp",
        ".tiff",
        ".tif",
        ".gif",
        ".ico",
        ".pcx",
        ".ppm",
        ".pgm",
        ".pbm",
    }
)

QUALITY_SETTINGS: dict[str, dict[str, int]] = {
    "high": {"dpi": 1200, "quality": 100},
    "medium": {"dpi": 200, "quality": 85},
    "low": {"dpi": 150, "quality": 75},
}


def _save_format_for(image_path: Path) -> str:
    """Return the Pillow save format matching the source file extension."""
    if image_path.suffix.lower() in LOSSLESS_FORMATS:
        return "PNG"
    return "JPEG"


def _optimize_image(image_path: Path, quality: str) -> None:
    """
    Normalise an image in place for downstream OCR.

    Raises:
        FileProcessingError: if the image cannot be opened, transformed
            or saved. Silently returning the unoptimized source would
            mask pipeline bugs that hurt OCR quality downstream.
    """
    logger.info(f"Optimizing image for PDF conversion: {image_path}")

    quality_settings = QUALITY_SETTINGS[quality]
    save_format = _save_format_for(image_path)

    try:
        with Image.open(image_path) as src_img:
            img: Image.Image = image_ops.apply_orientation(src_img)
            img = image_ops.remove_alpha(img)
            img = image_ops.resize_to_dpi(img, target_dpi=quality_settings["dpi"])
            img = image_ops.to_rgb(img)

            save_kwargs: dict[str, Any] = {
                "optimize": True,
                "format": save_format,
                "dpi": (quality_settings["dpi"], quality_settings["dpi"]),
            }
            if save_format == "JPEG":
                save_kwargs["quality"] = quality_settings["quality"]

            optimized_img = img.copy()

        optimized_img.save(image_path, **save_kwargs)
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise FileProcessingError(f"Image optimization failed for {image_path}: {e}") from e

    logger.info(f"Image optimization completed: {image_path}")


def _validate_source(source: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Source file does not exist: {source}")

    if source.suffix.lower() not in SUPPORTED_FORMATS:
        raise FileNotSupported(f"Unsupported image format for {source}: {source.suffix}")


def convert_image_to_pdf(
    source: Path,
    destination_folder: Path,
    quality: str = "high",
) -> Path:
    """
    Convert an image file to a PDF placed in ``destination_folder``.

    Args:
        source: path to an image file whose extension is in
            :data:`SUPPORTED_FORMATS`.
        destination_folder: directory to write the resulting PDF into;
            created if it does not exist.
        quality: one of the keys in :data:`QUALITY_SETTINGS`.

    Returns:
        The path to the generated PDF.

    Raises:
        FileNotFoundError: if the source file does not exist.
        FileNotSupported: if the source suffix is not supported.
        ValueError: if ``quality`` is unknown.
        FileProcessingError: if image optimization or PDF rendering
            fails, or if the resulting PDF is empty.
    """
    if quality not in QUALITY_SETTINGS:
        raise ValueError(f"Invalid quality {quality!r}; expected one of {sorted(QUALITY_SETTINGS)}")

    source = Path(source)
    destination_folder = Path(destination_folder)

    _validate_source(source)
    destination_folder.mkdir(parents=True, exist_ok=True)

    temp_pdf_path: Path | None = None
    try:
        logger.info(f"Converting image to PDF: {source}")

        _optimize_image(source, quality)

        layout_fun = img2pdf.get_layout_fun(None)  # Auto-detect page size
        temp_pdf_path = source.parent / f".tmp_{uuid.uuid4().hex[:8]}.pdf"

        with open(temp_pdf_path, "wb") as pdf_file:
            pdf_bytes = img2pdf.convert(str(source), layout_fun=layout_fun)
            pdf_file.write(pdf_bytes)

        final_pdf_path = destination_folder / f"{source.stem}.pdf"
        if temp_pdf_path != final_pdf_path:
            shutil.move(str(temp_pdf_path), str(final_pdf_path))
            temp_pdf_path = None  # moved, no cleanup needed
        else:
            temp_pdf_path = None

        if not final_pdf_path.exists() or final_pdf_path.stat().st_size == 0:
            raise FileProcessingError("PDF conversion resulted in empty or missing file")

        logger.info(f"Image successfully converted to PDF: {final_pdf_path}")
        return final_pdf_path

    except FileProcessingError:
        raise
    except Exception as e:
        logger.error(f"Image conversion failed for {source}: {e}")
        raise FileProcessingError(f"Could not convert image to PDF: {e}") from e
    finally:
        _cleanup_temp(temp_pdf_path)


def _cleanup_temp(temp_pdf_path: Path | None) -> None:
    """Clean up a temp PDF if it still exists."""
    if temp_pdf_path and temp_pdf_path.exists():
        try:
            temp_pdf_path.unlink()
            logger.debug(f"Cleaned up temporary file: {temp_pdf_path}")
        except Exception as e:
            logger.warning(f"Could not clean up temporary file {temp_pdf_path}: {e}")
