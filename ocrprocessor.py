import logging
import re
from pathlib import Path
from typing import Any, Dict
from pdfprocessor import PDFProcessor
from imageconverter import ImageConverter
from exceptions import FileProcessingError

from logger import get_logger
logger = get_logger(__name__)


class OCRProcessor:
    """Handle OCR processing with ocrmypdf."""
    
    SUPPORTED_FORMATS = {".pdf"}
    CONFIG_PARAMS = {
        'output_type', 'pages', 'language', 'mode', 'image_dpi', 
        'unpaper_clean', 'deskew', 'rotate_pages', 'rotate_pages_threshold', 
        'max_image_pixels', 'color_conversion_strategy', 'user_args'
    }
    MODE_MAPPING = {
        "force": "force_ocr",
        "skip": "skip_text",
        "skip_noarchive": "skip_text",
        "redo": "redo_ocr"
    }   
    LOGGING_VERBOSITY_MAPPING = {
        logging.NOTSET : -1,
        logging.INFO : 0, 
        logging.DEBUG : 1,
        logging.WARNING: 1,
        logging.ERROR : 2,
        logging.CRITICAL : 2
    }

    def __init__(self, file_path: Path, config: Dict[str, Any]):
        self.file_path = file_path
        self.config = config
        self.is_image = file_path.suffix.lower() not in self.SUPPORTED_FORMATS
    
    def _build_ocrmypdf_args(self) -> Dict[str, Any]:
        """Build arguments for ocrmypdf based on configuration."""
        # Filter relevant config parameters
        filtered_config = {
            k: v for k, v in self.config.items() if k in self.CONFIG_PARAMS
        }
        
        # Extract special configurations
        special_configs = {
            'pages': filtered_config.pop('pages', 0),
            'unpaper_clean': filtered_config.pop('unpaper_clean', None),
            'mode': filtered_config.pop('mode', None),
            'max_image_pixels': filtered_config.pop('max_image_pixels', 0),
            'user_args': filtered_config.pop('user_args', {})
        }
        
        # Base ocrmypdf arguments
        ocrmypdf_args = {
            "input_file": str(self.file_path),
            "output_file": str(self.file_path),
            "use_threads": True,
            "progress_bar": False,
        }
        
        # Add filtered config
        ocrmypdf_args.update(filtered_config)
        
        # Apply special configurations
        self._apply_special_configs(ocrmypdf_args, special_configs)
        
        # Remove None values and empty strings
        return {k: v for k, v in ocrmypdf_args.items() if v is not None and v != ""}
    
    def _apply_special_configs(self, args: Dict[str, Any], configs: Dict[str, Any]) -> None:
        """Apply special configuration settings to ocrmypdf arguments."""
        # Pages
        if configs['pages'] and configs['pages'] > 0:
            args['pages'] = configs['pages']
        
        # Unpaper clean
        if configs['unpaper_clean']:
            args[configs['unpaper_clean']] = True
        
        # Mode
        if configs['mode'] and configs['mode'] in self.MODE_MAPPING:
            args[self.MODE_MAPPING[configs['mode']]] = True
        
        # Max image pixels
        if configs['max_image_pixels'] and configs['max_image_pixels'] > 0:
            args['max_image_mpixels'] = int(configs['max_image_pixels'] / 1_000_000.0)
        
        # User args
        if configs['user_args'] and isinstance(configs['user_args'], dict):
            args.update(configs['user_args'])
    
    def _should_perform_ocr(self) -> bool:
        """Determine if OCR processing is needed."""
        # Always OCR images (after conversion to PDF)
        if self.is_image:
            logger.info("Image file detected, OCR will be performed")
            return True
        
        # Check force OCR setting first
        ocrmypdf_args = self._build_ocrmypdf_args()
        if ocrmypdf_args.get('force_ocr', False):
            logger.info("Force OCR enabled in configuration")
            return True
        
        # Check if PDF has text
        has_text = PDFProcessor.has_text(self.file_path)
        if not has_text:
            logger.info("PDF has no meaningful text, OCR needed")
            return True
        
        # Check if already processed by Tesseract
        if PDFProcessor.check_metadata_pattern(self.file_path, r"Tesseract|ocrmypdf"):
            logger.info("Document already processed by OCR software")
            return ocrmypdf_args.get('redo_ocr', False)
        
        # Check for scanned document indicators
        metadata = PDFProcessor.get_metadata(self.file_path)
        
        # Look for scanner signatures
        scanner_patterns = [
            r"scan", r"scanner", r"xerox", r"canon", r"hp", r"epson", 
            r"brother", r"kyocera", r"ricoh", r"konica"
        ]
        
        for key, value in metadata.items():
            for pattern in scanner_patterns:
                if re.search(pattern, str(value), re.IGNORECASE):
                    logger.info(f"Scanner signature found in metadata: {key}={value}")
                    return True

        logger.info("OCR not needed - PDF already contains text")
        return False
    
    def process(self) -> Path:
        """Process the file with OCR if needed."""
        try:
            # Convert image to PDF if necessary
            if self.is_image:
                logger.info(f"Converting image to PDF: {self.file_path}")
                image = ImageConverter(self.file_path,self.file_path.parent)
                self.file_path = image.convert_to_pdf()
            
            # Check if OCR is needed
            if not self._should_perform_ocr():
                logger.info("OCR processing not needed")
                return self.file_path
            
            # Prepare OCR arguments
            ocrmypdf_args = self._build_ocrmypdf_args()
            
            # Remove image_dpi for PDF files
            if not self.is_image and 'image_dpi' in ocrmypdf_args:
                ocrmypdf_args.pop('image_dpi')
            
            # Perform OCR
            logger.info("Starting OCR processing")
            logger.info(f"OCR parameters: {ocrmypdf_args}")
            
            import ocrmypdf
            # Configure ocrmypdf logging
            verbosity = self.LOGGING_VERBOSITY_MAPPING.get(logger.level, 0)
            ocrmypdf.configure_logging(
                verbosity=verbosity,
                manage_root_logger=False
            )

            # Execute OCR
            ocrmypdf.ocr(**ocrmypdf_args)
            
            logger.info("OCR processing completed successfully")
            
            # Verify output
            if not self.file_path.exists() or self.file_path.stat().st_size == 0:
                raise FileProcessingError("OCR processing resulted in empty or missing file")
            
            return self.file_path
            
        except Exception as e:
            logger.error(f"OCR processing failed: {e}")
            raise FileProcessingError(f"OCR processing failed: {e}")

