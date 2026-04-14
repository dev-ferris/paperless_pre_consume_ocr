import logging
import re
from pathlib import Path
from typing import Any

import ocrmypdf

from .exceptions import FileProcessingError
from .logger import get_logger
from .pdf import PDFProcessor

logger = get_logger(__name__)


class OCRProcessor:
    """Handle OCR processing with ocrmypdf."""

    SUPPORTED_FORMATS = {".pdf"}
    CONFIG_PARAMS = {
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
    MODE_MAPPING = {
        "force": "force_ocr",
        "skip": "skip_text",
        "skip_noarchive": "skip_text",
        "redo": "redo_ocr",
    }
    LOGGING_VERBOSITY_MAPPING = {
        logging.NOTSET: 0,
        logging.DEBUG: 1,
        logging.INFO: 0,
        logging.WARNING: -1,
        logging.ERROR: -1,
        logging.CRITICAL: -1,
    }

    def __init__(self, file_path: Path, config: dict[str, Any]):
        self.file_path = file_path
        self.config = config

    def _build_ocrmypdf_args(self) -> dict[str, Any]:
        """Build arguments for ocrmypdf based on configuration."""
        filtered_config = {k: v for k, v in self.config.items() if k in self.CONFIG_PARAMS}

        special_configs = {
            "pages": filtered_config.pop("pages", 0),
            "unpaper_clean": filtered_config.pop("unpaper_clean", None),
            "mode": filtered_config.pop("mode", None),
            "max_image_pixels": filtered_config.pop("max_image_pixels", 0),
            "user_args": filtered_config.pop("user_args", {}),
        }

        ocrmypdf_args = {
            "input_file": str(self.file_path),
            "output_file": str(self.file_path),
            "use_threads": True,
            "progress_bar": False,
        }

        ocrmypdf_args.update(filtered_config)
        self._apply_special_configs(ocrmypdf_args, special_configs)

        return {k: v for k, v in ocrmypdf_args.items() if v is not None and v != ""}

    def _apply_special_configs(self, args: dict[str, Any], configs: dict[str, Any]) -> None:
        """Apply special configuration settings to ocrmypdf arguments."""
        if configs["pages"] and configs["pages"] > 0:
            args["pages"] = configs["pages"]

        if configs["unpaper_clean"]:
            args[configs["unpaper_clean"]] = True

        if configs["mode"] and configs["mode"] in self.MODE_MAPPING:
            args[self.MODE_MAPPING[configs["mode"]]] = True

        # Convert max_image_pixels (px) to ocrmypdf's max_image_mpixels (Mpx).
        # Only forward when the requested limit is at least 1 Mpx; smaller
        # values would round down to 0 which ocrmypdf interprets as
        # "unlimited" — almost certainly not what the user meant. Below
        # 1 Mpx we fall back to ocrmypdf's own default by leaving the
        # argument unset.
        max_pixels = configs["max_image_pixels"]
        if max_pixels and max_pixels >= 1_000_000:
            args["max_image_mpixels"] = max(1, round(max_pixels / 1_000_000))

        if configs["user_args"] and isinstance(configs["user_args"], dict):
            args.update(configs["user_args"])

    def _should_perform_ocr(self) -> bool:
        """Determine if OCR processing is needed."""
        mode = self.config.get("mode")

        # Check force OCR setting first
        if mode == "force":
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
            return mode == "redo"

        # Check for scanned document indicators
        metadata = PDFProcessor.get_metadata(self.file_path)
        if metadata:
            scanner_patterns = [
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
            if not self._should_perform_ocr():
                logger.info("OCR processing not needed")
                return self.file_path

            ocrmypdf_args = self._build_ocrmypdf_args()

            # image_dpi is only relevant for image inputs, not PDFs
            ocrmypdf_args.pop("image_dpi", None)

            # ocrmypdf >= 16 renamed the first parameter to
            # `input_file_or_options` and accepts it positionally only.
            # Pop input/output file from kwargs and pass them positionally
            # so we stay compatible across ocrmypdf versions.
            input_file = ocrmypdf_args.pop("input_file")
            output_file = ocrmypdf_args.pop("output_file")

            logger.info("Starting OCR processing")
            logger.info(f"OCR parameters: {ocrmypdf_args}")

            # Configure ocrmypdf logging. configure_logging() expects an
            # ocrmypdf.Verbosity enum value, not a bare int.
            verbosity = self.LOGGING_VERBOSITY_MAPPING.get(logger.level, 0)
            ocrmypdf.configure_logging(
                verbosity=ocrmypdf.Verbosity(verbosity),
                manage_root_logger=False,
            )

            ocrmypdf.ocr(input_file, output_file, **ocrmypdf_args)

            logger.info("OCR processing completed successfully")

            if not self.file_path.exists() or self.file_path.stat().st_size == 0:
                raise FileProcessingError("OCR processing resulted in empty or missing file")

            return self.file_path

        except FileProcessingError:
            raise
        except Exception as e:
            logger.error(f"OCR processing failed: {e}")
            raise FileProcessingError(f"OCR processing failed: {e}") from e
