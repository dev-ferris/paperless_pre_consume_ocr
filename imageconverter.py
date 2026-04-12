from pathlib import Path
from typing import Any, Dict, Optional
from PIL import Image, ImageOps, ImageEnhance
import uuid
import img2pdf

from exceptions import FileProcessingError
from logger import get_logger

logger = get_logger(__name__)

class ImageConverter:
    """Handle image to PDF conversion with optimized error handling and resource management."""
    
    # Expanded supported formats
    SUPPORTED_FORMATS = {
        ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", 
        ".gif", ".ico", ".pcx", ".ppm", ".pgm", ".pbm"
    }
    
    # Image quality settings
    QUALITY_SETTINGS = {
        'high': {'dpi': 1200, 'quality': 100},
        'medium': {'dpi': 200, 'quality': 85},
        'low': {'dpi': 150, 'quality': 75}
    }

    # Mapping for EXIF orientation to rotation degrees
    ROTATE_DEGREES = {
        1: 0,   # Normal
        2: 0,   # Mirrored
        3: 180, # Upside down
        4: 0,   # Mirrored upside down
        5: 90,  # Mirrored and rotated right
        6: 270, # Rotated right
        7: 90,  # Mirrored and rotated left
        8: 270, # Rotated left
    }

    def __init__(self, file_path: Path, destination_folder: Path, quality: str = 'high'):
        self.file_path = Path(file_path)
        self.destination_folder = Path(destination_folder)
        self.quality = quality
        
        # Validate inputs
        if not self.file_path.exists():
            raise FileNotFoundError(f"Source file does not exist: {self.file_path}")
        
        if not self.destination_folder.exists():
            self.destination_folder.mkdir(parents=True, exist_ok=True)
            
        self.is_image = self.file_path.suffix.lower() in self.SUPPORTED_FORMATS

    def _apply_orientation(self, img):
        """Apply orientation based on EXIF data if available."""
        try:
            # Safe auto-orient based on EXIF data
            try:
                img = ImageOps.exif_transpose(img)
                logger.debug(f"Image after auto-orientation: {img.size}, mode: {img.mode}")
            except Exception as exif_error:
                logger.warning(f"EXIF transpose failed: {exif_error}")
                logger.debug("Continuing without EXIF orientation correction")
                
                # Optional: Try manual orientation check
                try:
                    # Check if image has EXIF orientation tag
                    exif_dict = img._getexif()
                    if exif_dict is not None:
                        orientation = exif_dict.get(0x0112, 1)  # Orientation tag
                        logger.info(f"Manual orientation applied: {orientation}")
                        img = img.rotate(self.ROTATE_DEGREES.get(orientation, 0), expand=True)
                                
                except Exception as manual_orient_error:
                    logger.warning(f"Manual orientation check also failed: {manual_orient_error}")
                    
            logger.info(f"Image after orientation: {img.size}, mode: {img.mode}")
            return img
        except Exception as e:
            logger.error(f"Image orientation failed: {e}")
            return img  # Return original if optimization fails

    def _remove_alpha_channel(self, img):
        """Remove alpha channel from image if present."""
        try:
            # Handle transparency/alpha channel
            if img.mode in ('RGBA', 'LA'):
                logger.debug(f"Removing alpha channel from image with mode: {img.mode}")
                IMAGE_SETTINGS = {
                    'RGBA': { 'mode':'RGB', 'size': img.size, 'color' : (255, 255, 255)},   # Convert RGBA to RGB
                    'LA':   { 'mode':'L'  , 'size': img.size, 'color' : 255},               # Convert LA to L (grayscale)
                    'PA':   { 'mode':'RGBA' }                                               # Convert PA to RGBA
                }
                kwargs = IMAGE_SETTINGS.get(img.mode, IMAGE_SETTINGS['RGBA'])
                background = Image.new( **kwargs)
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode == 'PA':
                # Convert palette+alpha to RGB
                img = img.convert('RGBA').convert('RGB')
                    
            logger.info(f"Alpha channel removed from image")
            return img
        except Exception as e:
            logger.error(f"Failed to remove alpha channel: {e}")
            return img

    def _convert_image_to_rgb(self, img):
        """Convert image to RGB mode if necessary."""
        try:
            logger.info(f"Converting image to RGB")
            # Optimize based on content
            if img.mode == 'L': 
                return img  # Grayscale is fine for OCR
            if img.mode != 'RGB':
                logger.info(f"Converting {img.mode} image to RGB")
                img = img.convert('RGB')
            return img
        except Exception as e:
            logger.error(f"Image conversion to RGB failed: {e}")
            return img
        
    def _resize_image(self, img, max_dimension: int = 4096, sharpness: float = 1.0):
        """Resize image based on quality settings and max dimension."""
        try:
            # Apply DPI settings
            logger.info(f"Applying DPI settings for quality: {self.quality}")
            quality_settings = self.QUALITY_SETTINGS.get(self.quality, self.QUALITY_SETTINGS['medium'])
            target_dpi = quality_settings['dpi']
            
            # Resize if image is too large or too small
            current_dpi = img.info.get('dpi', (72, 72))[0]
            # Calculate new size based on target DPI
            scale_factor = target_dpi / current_dpi
            # Only resize if change is significant
            if abs(scale_factor - 1.0) > 0.1:
                new_size =  tuple(x * scale_factor for x in img.size)
                limit_scale = max_dimension / max(new_size) if max(new_size) > max_dimension else 1.0
                new_size = tuple(int(x * limit_scale) for x in new_size)

                logger.info(f"Resizing image from {img.size} to {new_size}")
                img = img.resize(new_size, Image.Resampling.LANCZOS)

                # Enhance sharpness if upscaling
                img = ImageEnhance.Sharpness(img).enhance(sharpness)
                
            return img
        except Exception as e:
            logger.error(f"Image resizing failed: {e}")
            return img  # Return original if optimization fails

    def _optimize_image(self, image_path: Path) -> Path:
        """Optimize image for better PDF conversion with single load/save cycle."""
        try:
            logger.info(f"Optimizing image for PDF conversion: {image_path}")
            
            # Load image once
            with Image.open(image_path) as img:
                # Apply all optimizations in sequence
                img = self._apply_orientation(img)
                img = self._remove_alpha_channel(img)
                img = self._resize_image(img)
                img = self._convert_image_to_rgb(img)
                
                # Prepare save parameters
                save_kwargs = {'optimize': True}
                quality_settings = self.QUALITY_SETTINGS.get(self.quality, self.QUALITY_SETTINGS['medium'])
                
                # Set format and quality based on image mode
                if img.mode == 'RGB':
                    save_kwargs['format'] = 'JPEG'
                    save_kwargs['quality'] = quality_settings['quality']
                else:
                    save_kwargs['format'] = 'PNG'
                
                # Set DPI
                dpi = quality_settings['dpi']
                save_kwargs['dpi'] = (dpi, dpi)
                
                # Create a copy to save (avoids issues with file handles)
                optimized_img = img.copy()
            
            # Save optimized image
            optimized_img.save(image_path, **save_kwargs)
            logger.info(f"Image optimization completed: {image_path}")
            return image_path

        except Exception as e:
            logger.error(f"Image optimization failed for {image_path}: {e}")
            return image_path  # Return original if optimization fails

    def convert_to_pdf(self):
        """Convert image file to PDF with enhanced error handling and optimization."""
        if not self.is_image:
            logger.info(f"File is not a supported image format: {self.file_path}")
            return self.file_path
        
        temp_pdf_path = None
        
        try:
            # Import img2pdf here to catch import errors early
            logger.info(f"Converting image to PDF: {self.file_path}")
            
            # Optimize image for better PDF conversion (single load/save cycle)
            self._optimize_image(self.file_path)
            
            # Configure img2pdf conversion
            layout_fun = img2pdf.get_layout_fun(None)  # Auto-detect page size
            temp_pdf_path = self.file_path.with_suffix(f".temp_{uuid.uuid4().hex[:8]}.pdf")

            # Convert to PDF
            with open(temp_pdf_path, "wb") as pdf_file:
                pdf_bytes = img2pdf.convert(
                    str(self.file_path),
                    layout_fun=layout_fun,
                    with_pdfrw=False  # Use pure Python implementation for better compatibility
                )
                pdf_file.write(pdf_bytes)
            
            # Create final PDF path
            final_pdf_path = self.destination_folder / f"{self.file_path.stem}.pdf"
            
            # Move temp PDF to final location
            if temp_pdf_path != final_pdf_path:
                import shutil
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

        except Exception as e:
            logger.error(f"Image conversion failed for {self.file_path}: {e}")
            raise FileProcessingError(f"Could not convert image to PDF: {e}")
        finally:
            # Cleanup temporary files
            self._cleanup_temp_files(temp_pdf_path)
    
    def _cleanup_temp_files(self, temp_pdf_path: Optional[Path]):
        """Clean up temporary files created during processing."""
        if temp_pdf_path and temp_pdf_path.exists():
            try:
                temp_pdf_path.unlink()
                logger.debug(f"Cleaned up temporary file: {temp_pdf_path}")
            except Exception as e:
                logger.warning(f"Could not clean up temporary file {temp_pdf_path}: {e}")