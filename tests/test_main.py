import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from paperless_pre_consume_ocr.cli import EXIT_IMAGE_CONVERTED, main


class TestMain:
    """Tests for the main entry point."""

    @patch("paperless_pre_consume_ocr.cli.load_environment")
    def test_unsupported_format_returns_ok(self, mock_load_env):
        """Unsupported file format should return EX_OK."""
        mock_env = MagicMock()
        mock_env.paths.working.suffix = ".xyz"
        mock_load_env.return_value = mock_env

        result = main()
        assert result == os.EX_OK

    @patch("paperless_pre_consume_ocr.cli.load_environment")
    def test_missing_working_path_returns_config_error(self, mock_load_env):
        """Missing DOCUMENT_WORKING_PATH should return EX_CONFIG."""
        mock_load_env.side_effect = ValueError("DOCUMENT_WORKING_PATH is required")

        result = main()
        assert result == os.EX_CONFIG

    @patch("paperless_pre_consume_ocr.cli.load_environment")
    def test_missing_file_returns_noinput(self, mock_load_env):
        """Non-existent file should return EX_NOINPUT."""
        mock_load_env.side_effect = FileNotFoundError("File not found")

        result = main()
        assert result == os.EX_NOINPUT

    @patch("paperless_pre_consume_ocr.cli.fetch_ocr_config")
    @patch("paperless_pre_consume_ocr.cli.load_database_config")
    @patch("paperless_pre_consume_ocr.cli.ocr")
    @patch("paperless_pre_consume_ocr.cli.load_environment")
    def test_pdf_triggers_ocr_processing(
        self,
        mock_load_env,
        mock_ocr,
        mock_load_db,
        mock_fetch_ocr,
    ):
        """PDF files should trigger OCR processing."""
        mock_env = MagicMock()
        mock_env.paths.working.suffix = ".pdf"
        mock_load_env.return_value = mock_env

        mock_load_db.return_value = MagicMock()
        mock_fetch_ocr.return_value = {"mode": "skip"}

        mock_ocr.SUPPORTED_FORMATS = frozenset({".pdf"})
        mock_ocr.run_ocr.return_value = Path("/tmp/test.pdf")

        result = main()
        assert result == 0
        mock_fetch_ocr.assert_called_once()
        mock_ocr.run_ocr.assert_called_once()

    @patch("paperless_pre_consume_ocr.cli.image_converter")
    @patch("paperless_pre_consume_ocr.cli.load_environment")
    def test_image_triggers_conversion(self, mock_load_env, mock_image_converter):
        """Image files should trigger conversion and return EXIT_IMAGE_CONVERTED."""
        mock_env = MagicMock()
        mock_env.paths.working.suffix = ".jpg"
        mock_load_env.return_value = mock_env

        mock_image_converter.SUPPORTED_FORMATS = frozenset(
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

        mock_pdf_path = MagicMock()
        mock_pdf_path.exists.return_value = True
        mock_image_converter.convert_image_to_pdf.return_value = mock_pdf_path

        result = main()
        assert result == EXIT_IMAGE_CONVERTED
        mock_image_converter.convert_image_to_pdf.assert_called_once()

    @patch("paperless_pre_consume_ocr.cli.load_environment")
    def test_unexpected_error_returns_3(self, mock_load_env):
        """Unexpected errors should return exit code 3."""
        mock_load_env.side_effect = RuntimeError("Something unexpected")

        result = main()
        assert result == 3
