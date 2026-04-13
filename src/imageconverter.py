import shutil
import uuid
from pathlib import Path

import img2pdf
from PIL import Image, ImageEnhance, ImageOps

from exceptions import FileNotSupported, FileProcessingError
from logger import get_logger

logger = get_logger(__name__)


class ImageConverter:
    """Handle image to PDF conversion with optimized error handling and resource management."""

    SUPPORTED_FORMATS = {
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

    # Formats that should be saved as PNG to preserve lossless quality
    LOSSLESS_FORMATS = {
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

    QUALITY_SETTINGS = {
        "high": {"dpi": 1200, "quality": 100},
        "medium": {"dpi": 200, "quality": 85},
        "low": {"dpi": 150, "quality": 75},
    }

    def __init__(self, file_path: Path, destination_folder: Path, quality: str = "high"):
        self.file_path = Path(file_path)
        self.destination_folder = Path(destination_folder)
        self.quality = quality

        if not self.file_path.exists():
            raise FileNotFoundError(f"Source file does not exist: {self.file_path}")

        if self.file_path.suffix.lower() not in self.SUPPORTED_FORMATS:
            raise FileNotSupported(
                f"Unsupported image format for {self.file_path}: {self.file_path.suffix}"
            )

        if not self.destination_folder.exists():
            self.destination_folder.mkdir(parents=True, exist_ok=True)

    def _apply_orientation(self, img: Image.Image) -> Image.Image:
        """Apply orientation based on EXIF data if available."""
        try:
            return ImageOps.exif_transpose(img)
        except Exception as e:
            logger.warning(f"EXIF transpose failed, continuing without orientation correction: {e}")
            return img

    def _remove_alpha_channel(self, img: Image.Image) -> Image.Image:
        """Remove alpha channel from image if present."""
        try:
            if img.mode in ("RGBA", "LA"):
                logger.debug(f"Removing alpha channel from image with mode: {img.mode}")
                bg_mode = "RGB" if img.mode == "RGBA" else "L"
                bg_color = (255, 255, 255) if img.mode == "RGBA" else 255
                background = Image.new(bg_mode, img.size, bg_color)
                background.paste(img, mask=img.split()[-1])
                return background
            elif img.mode == "PA":
                return img.convert("RGBA").convert("RGB")
            return img
        except Exception as e:
            logger.error(f"Failed to remove alpha channel: {e}")
            return img

    def _convert_image_to_rgb(self, img: Image.Image) -> Image.Image:
        """Convert image to RGB mode if necessary."""
        try:
            if img.mode == "L":
                return img  # Grayscale is fine for OCR
            if img.mode != "RGB":
                logger.info(f"Converting {img.mode} image to RGB")
                return img.convert("RGB")
            return img
        except Exception as e:
            logger.error(f"Image conversion to RGB failed: {e}")
            return img

    def _resize_image(
        self, img: Image.Image, max_dimension: int = 4096, sharpness: float = 1.0
    ) -> Image.Image:
        """Resize image based on quality settings and max dimension."""
        try:
            quality_settings = self.QUALITY_SETTINGS.get(
                self.quality, self.QUALITY_SETTINGS["medium"]
            )
            target_dpi = quality_settings["dpi"]

            current_dpi = img.info.get("dpi", (72, 72))[0]
            scale_factor = target_dpi / current_dpi

            if abs(scale_factor - 1.0) > 0.1:
                new_size = tuple(x * scale_factor for x in img.size)
                if max(new_size) > max_dimension:
                    limit_scale = max_dimension / max(new_size)
                    new_size = tuple(int(x * limit_scale) for x in new_size)
                else:
                    new_size = tuple(int(x) for x in new_size)

                logger.info(f"Resizing image from {img.size} to {new_size}")
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                img = ImageEnhance.Sharpness(img).enhance(sharpness)

            return img
        except Exception as e:
            logger.error(f"Image resizing failed: {e}")
            return img

    def _get_save_format(self, image_path: Path) -> str:
        """Determine the save format based on the file extension to avoid format mismatch."""
        if image_path.suffix.lower() in self.LOSSLESS_FORMATS:
            return "PNG"
        return "JPEG"

    def _optimize_image(self, image_path: Path) -> Path:
        """Optimize image for better PDF conversion with single load/save cycle."""
        try:
            logger.info(f"Optimizing image for PDF conversion: {image_path}")

            with Image.open(image_path) as img:
                img = self._apply_orientation(img)
                img = self._remove_alpha_channel(img)
                img = self._resize_image(img)
                img = self._convert_image_to_rgb(img)

                quality_settings = self.QUALITY_SETTINGS.get(
                    self.quality, self.QUALITY_SETTINGS["medium"]
                )
                save_format = self._get_save_format(image_path)

                save_kwargs = {
                    "optimize": True,
                    "format": save_format,
                    "dpi": (quality_settings["dpi"], quality_settings["dpi"]),
                }

                if save_format == "JPEG":
                    save_kwargs["quality"] = quality_settings["quality"]

                optimized_img = img.copy()

            optimized_img.save(image_path, **save_kwargs)
            logger.info(f"Image optimization completed: {image_path}")
            return image_path

        except Exception as e:
            logger.error(f"Image optimization failed for {image_path}: {e}")
            return image_path  # Return original if optimization fails

    def convert_to_pdf(self) -> Path:
        """Convert image file to PDF with enhanced error handling and optimization."""
        temp_pdf_path = None

        try:
            logger.info(f"Converting image to PDF: {self.file_path}")

            # Optimize image for better PDF conversion (single load/save cycle)
            self._optimize_image(self.file_path)

            # Configure img2pdf conversion
            layout_fun = img2pdf.get_layout_fun(None)  # Auto-detect page size
            temp_pdf_path = self.file_path.parent / f".tmp_{uuid.uuid4().hex[:8]}.pdf"

            # Convert to PDF
            with open(temp_pdf_path, "wb") as pdf_file:
                pdf_bytes = img2pdf.convert(
                    str(self.file_path),
                    layout_fun=layout_fun,
                )
                pdf_file.write(pdf_bytes)

            # Move temp PDF to final location
            final_pdf_path = self.destination_folder / f"{self.file_path.stem}.pdf"

            if temp_pdf_path != final_pdf_path:
                shutil.move(str(temp_pdf_path), str(final_pdf_path))
                temp_pdf_path = None  # Prevent cleanup since file was moved
            else:
                final_pdf_path = temp_pdf_path
                temp_pdf_path = None

            # Verify conversion success
            if not final_pdf_path.exists() or final_pdf_path.stat().st_size == 0:
                raise FileProcessingError("PDF conversion resulted in empty or missing file")

            logger.info(f"Image successfully converted to PDF: {final_pdf_path}")
            return final_pdf_path

        except FileProcessingError:
            raise
        except Exception as e:
            logger.error(f"Image conversion failed for {self.file_path}: {e}")
            raise FileProcessingError(f"Could not convert image to PDF: {e}") from e
        finally:
            self._cleanup_temp_files(temp_pdf_path)

    def _cleanup_temp_files(self, temp_pdf_path: Path | None) -> None:
        """Clean up temporary files created during processing."""
        if temp_pdf_path and temp_pdf_path.exists():
            try:
                temp_pdf_path.unlink()
                logger.debug(f"Cleaned up temporary file: {temp_pdf_path}")
            except Exception as e:
                logger.warning(f"Could not clean up temporary file {temp_pdf_path}: {e}")
