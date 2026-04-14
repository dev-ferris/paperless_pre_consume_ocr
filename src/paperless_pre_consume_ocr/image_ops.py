"""
Pillow transform helpers.

These are pure image operations — they accept and return
``PIL.Image.Image`` objects and know nothing about file paths,
quality profiles or output formats. Keeping them free functions makes
them trivial to unit-test and compose.
"""

from PIL import Image, ImageOps

from .logger import get_logger

logger = get_logger(__name__)


def apply_orientation(img: Image.Image) -> Image.Image:
    """Apply orientation based on EXIF data if available."""
    return ImageOps.exif_transpose(img)


def remove_alpha(img: Image.Image) -> Image.Image:
    """Flatten any alpha channel onto an opaque white background."""
    if img.mode in ("RGBA", "LA"):
        logger.debug(f"Removing alpha channel from image with mode: {img.mode}")
        bg_mode = "RGB" if img.mode == "RGBA" else "L"
        bg_color = (255, 255, 255) if img.mode == "RGBA" else 255
        background = Image.new(bg_mode, img.size, bg_color)
        background.paste(img, mask=img.split()[-1])
        return background
    if img.mode == "PA":
        return img.convert("RGBA").convert("RGB")
    return img


def to_rgb(img: Image.Image) -> Image.Image:
    """Convert image to RGB mode unless it is already grayscale or RGB."""
    if img.mode == "L":
        return img  # Grayscale is fine for OCR
    if img.mode != "RGB":
        logger.info(f"Converting {img.mode} image to RGB")
        return img.convert("RGB")
    return img


def current_dpi(img: Image.Image) -> float:
    """Extract a single DPI value from Pillow's heterogeneous info dict."""
    dpi = img.info.get("dpi", 72)
    if isinstance(dpi, tuple):
        dpi = dpi[0] if dpi else 72
    return float(dpi) or 72.0


def resize_to_dpi(
    img: Image.Image,
    target_dpi: int,
    max_dimension: int = 4096,
) -> Image.Image:
    """
    Scale an image so its pixel density matches ``target_dpi``.

    The result is clamped so its longest edge does not exceed
    ``max_dimension`` pixels. If the existing DPI is within 10% of the
    target, the image is returned unchanged.
    """
    scale_factor = target_dpi / current_dpi(img)

    if abs(scale_factor - 1.0) <= 0.1:
        return img

    new_size = tuple(x * scale_factor for x in img.size)
    if max(new_size) > max_dimension:
        limit_scale = max_dimension / max(new_size)
        new_size = tuple(int(x * limit_scale) for x in new_size)
    else:
        new_size = tuple(int(x) for x in new_size)

    logger.info(f"Resizing image from {img.size} to {new_size}")
    return img.resize(new_size, Image.Resampling.LANCZOS)
