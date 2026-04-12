#!/usr/bin/env python3
"""
Paperless OCR Pre-Processing Script
Optimized version with improved error handling, logging, and code structure.
"""
import os
import sys
from exceptions import ConfigurationError, DatabaseError, FileProcessingError, FileNotSupported
from imageconverter import ImageConverter
from ocrprocessor import OCRProcessor
from paperlessenvironment import PaperlessEnvironment

# Setup logging
from logger import get_logger
logger = get_logger(__name__)

EXIT_IMAGE_CONVERTED = 10

def main() -> int:
    """Main execution function with improved error handling and logging."""
    logger.info("Paperless Pre-Consume: Starting OCR processing")
    
    try:
        # Get configuration from environment
        paperless_env = PaperlessEnvironment()

        # Determine processing phase based on file type
        suffix = paperless_env.paths.working.suffix.lower()
        if suffix in ImageConverter.SUPPORTED_FORMATS:
            return _handle_image_conversion( paperless_env )
        elif suffix in OCRProcessor.SUPPORTED_FORMATS:
            return _handle_ocr_processing( paperless_env )
        else:
            raise FileNotSupported(f"Unsupported file format: {suffix}")
            
    except FileNotSupported as e:
        logger.warning(f"File format not supported: {e}")
        return os.EX_OK
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return os.EX_NOINPUT
    except (ValueError, ConfigurationError) as e:
        logger.error(f"Configuration error: {e}")
        return os.EX_CONFIG
    except DatabaseError as e:
        logger.error(f"Database connection failed: {e}")
        return os.EX_CONFIG
    except FileProcessingError as e:
        logger.error(f"File processing failed: {e}")
        return 2
    except Exception as e:
        logger.exception("Unexpected error occurred")
        return 3
    
def _handle_image_conversion(env: PaperlessEnvironment) -> int:
    """Handle image to PDF conversion phase."""
    logger.info("=== IMAGE CONVERSION PHASE ===")
    
    try:
        converter = ImageConverter(env.paths.working, env.paths.consume)
        pdf_path = converter.convert_to_pdf()
        
        if not pdf_path or not pdf_path.exists():
            logger.error(f"PDF conversion failed - output file not found: {pdf_path}")
            return 2
            
        logger.info(f"Image successfully converted to PDF: {pdf_path}")
        logger.info("Exiting to allow Paperless to re-consume the PDF")
        return EXIT_IMAGE_CONVERTED
        
    except Exception as e:
        logger.error(f"Image conversion failed: {e}")
        raise FileProcessingError(f"Image conversion failed: {e}")


def _handle_ocr_processing(env: PaperlessEnvironment) -> int:
    """Handle OCR processing phase."""
    logger.info("=== OCR PROCESSING PHASE ===")
    
    try:
        # Get OCR configuration from database
        ocr_config = env.config.get_ocr_config()
        
        logger.info(f"Processing file: {env.paths.working}")
        logger.debug(f"OCR configuration: {ocr_config}")
        
        # Process the file
        processor = OCRProcessor(env.paths.working, ocr_config)
        result_path = processor.process()
        
        if result_path:
            logger.info("OCR processing completed successfully")
            return 0
        else:
            logger.error("OCR processing returned no result")
            return 2
            
    except Exception as e:
        logger.error(f"OCR processing failed: {e}")
        raise FileProcessingError(f"OCR processing failed: {e}")


if __name__ == "__main__":
    sys.exit(main())