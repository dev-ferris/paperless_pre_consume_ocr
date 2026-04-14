from pathlib import Path
from unittest.mock import patch

import pytest

from paperless_pre_consume_ocr import ocr
from paperless_pre_consume_ocr.exceptions import FileProcessingError


class TestBuildOcrmypdfArgs:
    """Tests for ocr.build_ocrmypdf_args."""

    def _build(self, config, file_path="/tmp/test.pdf"):
        return ocr.build_ocrmypdf_args(Path(file_path), config)

    def test_basic_args(self):
        """Should include base args with input/output file paths."""
        args = self._build({"language": "deu+eng", "output_type": "pdf"})

        assert args["input_file"] == "/tmp/test.pdf"
        assert args["output_file"] == "/tmp/test.pdf"
        assert args["use_threads"] is True
        assert args["progress_bar"] is False
        assert args["language"] == "deu+eng"
        assert args["output_type"] == "pdf"

    def test_mode_mapping_force(self):
        """mode='force' should map to force_ocr=True."""
        args = self._build({"mode": "force"})
        assert args.get("force_ocr") is True

    def test_mode_mapping_skip(self):
        """mode='skip' should map to skip_text=True."""
        args = self._build({"mode": "skip"})
        assert args.get("skip_text") is True

    def test_mode_mapping_redo(self):
        """mode='redo' should map to redo_ocr=True."""
        args = self._build({"mode": "redo"})
        assert args.get("redo_ocr") is True

    def test_max_image_pixels_conversion(self):
        """max_image_pixels should be rounded to megapixels."""
        args = self._build({"max_image_pixels": 178956970})
        assert args["max_image_mpixels"] == 179  # round(178.957) == 179

    def test_max_image_pixels_below_one_megapixel_omitted(self):
        """Sub-megapixel limits should be ignored, not rounded down to 0."""
        args = self._build({"max_image_pixels": 500_000})
        assert "max_image_mpixels" not in args

    def test_max_image_pixels_zero_omitted(self):
        """Zero/None limits should be ignored entirely."""
        args = self._build({"max_image_pixels": 0})
        assert "max_image_mpixels" not in args

    def test_pages_included_when_positive(self):
        """pages should be included when > 0."""
        args = self._build({"pages": 5})
        assert args["pages"] == 5

    def test_pages_excluded_when_zero(self):
        """pages should not be included when 0."""
        args = self._build({"pages": 0})
        assert "pages" not in args

    def test_user_args_merged(self):
        """user_args dict should be merged into args."""
        args = self._build({"user_args": {"custom_flag": True}})
        assert args["custom_flag"] is True

    def test_none_values_excluded(self):
        """None and empty string values should be filtered out."""
        args = self._build({"language": None, "output_type": ""})
        assert "language" not in args
        assert "output_type" not in args

    def test_irrelevant_config_keys_ignored(self):
        """Config keys not in CONFIG_PARAMS should be ignored."""
        args = self._build({"language": "deu", "irrelevant_key": "value"})
        assert "irrelevant_key" not in args
        assert args["language"] == "deu"


class TestShouldPerformOcr:
    """Tests for ocr.should_perform_ocr."""

    def test_force_mode_always_true(self):
        """Force mode should always return True."""
        assert ocr.should_perform_ocr(Path("/tmp/test.pdf"), {"mode": "force"}) is True

    @patch("paperless_pre_consume_ocr.ocr.pdf")
    def test_no_text_returns_true(self, mock_pdf):
        """Should return True when PDF has no text."""
        mock_pdf.has_text.return_value = False
        assert ocr.should_perform_ocr(Path("/tmp/test.pdf"), {"mode": "skip"}) is True

    @patch("paperless_pre_consume_ocr.ocr.pdf")
    def test_already_ocrd_skip_mode_returns_false(self, mock_pdf):
        """Should return False when already OCR'd and mode is skip."""
        mock_pdf.has_text.return_value = True
        mock_pdf.check_metadata_pattern.return_value = True
        assert ocr.should_perform_ocr(Path("/tmp/test.pdf"), {"mode": "skip"}) is False

    @patch("paperless_pre_consume_ocr.ocr.pdf")
    def test_already_ocrd_redo_mode_returns_true(self, mock_pdf):
        """Should return True when already OCR'd and mode is redo."""
        mock_pdf.has_text.return_value = True
        mock_pdf.check_metadata_pattern.return_value = True
        assert ocr.should_perform_ocr(Path("/tmp/test.pdf"), {"mode": "redo"}) is True

    @patch("paperless_pre_consume_ocr.ocr.pdf")
    def test_scanner_signature_returns_true(self, mock_pdf):
        """Should return True when scanner signature found in metadata."""
        mock_pdf.has_text.return_value = True
        mock_pdf.check_metadata_pattern.return_value = False
        mock_pdf.get_metadata.return_value = {"/Creator": "Canon Scanner v2.0"}
        assert ocr.should_perform_ocr(Path("/tmp/test.pdf"), {"mode": "skip"}) is True

    @patch("paperless_pre_consume_ocr.ocr.pdf")
    def test_text_pdf_no_scanner_returns_false(self, mock_pdf):
        """Should return False for a normal text PDF without scanner signatures."""
        mock_pdf.has_text.return_value = True
        mock_pdf.check_metadata_pattern.return_value = False
        mock_pdf.get_metadata.return_value = {
            "/Creator": "Microsoft Word",
            "/Producer": "macOS Quartz",
        }
        assert ocr.should_perform_ocr(Path("/tmp/test.pdf"), {"mode": "skip"}) is False


class TestRunOcr:
    """Tests for ocr.run_ocr."""

    @patch("paperless_pre_consume_ocr.ocr.pdf")
    def test_skips_when_not_needed(self, mock_pdf):
        """Should return file_path without OCR when not needed."""
        mock_pdf.has_text.return_value = True
        mock_pdf.check_metadata_pattern.return_value = True

        result = ocr.run_ocr(Path("/tmp/test.pdf"), {"mode": "skip"})
        assert result == Path("/tmp/test.pdf")

    @patch("paperless_pre_consume_ocr.ocr.ocrmypdf")
    @patch("paperless_pre_consume_ocr.ocr.pdf")
    def test_runs_ocr_when_needed(self, mock_pdf, mock_ocrmypdf, tmp_path):
        """Should call ocrmypdf.ocr when OCR is needed."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        mock_pdf.has_text.return_value = False

        result = ocr.run_ocr(test_file, {"mode": "skip", "language": "deu+eng"})

        mock_ocrmypdf.ocr.assert_called_once()
        assert result == test_file

    @patch("paperless_pre_consume_ocr.ocr.ocrmypdf")
    @patch("paperless_pre_consume_ocr.ocr.pdf")
    def test_removes_image_dpi_for_pdf(self, mock_pdf, mock_ocrmypdf, tmp_path):
        """Should not pass image_dpi to ocrmypdf for PDF files."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        mock_pdf.has_text.return_value = False

        ocr.run_ocr(test_file, {"mode": "skip", "image_dpi": 300})

        call_kwargs = mock_ocrmypdf.ocr.call_args[1]
        assert "image_dpi" not in call_kwargs

    @patch("paperless_pre_consume_ocr.ocr.ocrmypdf")
    @patch("paperless_pre_consume_ocr.ocr.pdf")
    def test_raises_on_empty_output(self, mock_pdf, mock_ocrmypdf, tmp_path):
        """Should raise FileProcessingError if output file is empty after OCR."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        mock_pdf.has_text.return_value = False

        # Simulate ocrmypdf emptying the file
        def mock_ocr(*args, **kwargs):
            test_file.write_bytes(b"")

        mock_ocrmypdf.ocr.side_effect = mock_ocr

        with pytest.raises(FileProcessingError, match="empty or missing"):
            ocr.run_ocr(test_file, {"mode": "skip"})
