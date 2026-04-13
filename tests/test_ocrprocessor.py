import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from ocrprocessor import OCRProcessor
from exceptions import FileProcessingError


class TestBuildOcrmypdfArgs:
    """Tests for OCRProcessor._build_ocrmypdf_args."""

    def _make_processor(self, config, file_path="/tmp/test.pdf"):
        return OCRProcessor(Path(file_path), config)

    def test_basic_args(self):
        """Should include base args with input/output file paths."""
        proc = self._make_processor({"language": "deu+eng", "output_type": "pdf"})
        args = proc._build_ocrmypdf_args()

        assert args["input_file"] == "/tmp/test.pdf"
        assert args["output_file"] == "/tmp/test.pdf"
        assert args["use_threads"] is True
        assert args["progress_bar"] is False
        assert args["language"] == "deu+eng"
        assert args["output_type"] == "pdf"

    def test_mode_mapping_force(self):
        """mode='force' should map to force_ocr=True."""
        proc = self._make_processor({"mode": "force"})
        args = proc._build_ocrmypdf_args()
        assert args.get("force_ocr") is True

    def test_mode_mapping_skip(self):
        """mode='skip' should map to skip_text=True."""
        proc = self._make_processor({"mode": "skip"})
        args = proc._build_ocrmypdf_args()
        assert args.get("skip_text") is True

    def test_mode_mapping_redo(self):
        """mode='redo' should map to redo_ocr=True."""
        proc = self._make_processor({"mode": "redo"})
        args = proc._build_ocrmypdf_args()
        assert args.get("redo_ocr") is True

    def test_max_image_pixels_conversion(self):
        """max_image_pixels should be converted to megapixels."""
        proc = self._make_processor({"max_image_pixels": 178956970})
        args = proc._build_ocrmypdf_args()
        assert args["max_image_mpixels"] == 178

    def test_pages_included_when_positive(self):
        """pages should be included when > 0."""
        proc = self._make_processor({"pages": 5})
        args = proc._build_ocrmypdf_args()
        assert args["pages"] == 5

    def test_pages_excluded_when_zero(self):
        """pages should not be included when 0."""
        proc = self._make_processor({"pages": 0})
        args = proc._build_ocrmypdf_args()
        assert "pages" not in args

    def test_user_args_merged(self):
        """user_args dict should be merged into args."""
        proc = self._make_processor({"user_args": {"custom_flag": True}})
        args = proc._build_ocrmypdf_args()
        assert args["custom_flag"] is True

    def test_none_values_excluded(self):
        """None and empty string values should be filtered out."""
        proc = self._make_processor({"language": None, "output_type": ""})
        args = proc._build_ocrmypdf_args()
        assert "language" not in args
        assert "output_type" not in args

    def test_irrelevant_config_keys_ignored(self):
        """Config keys not in CONFIG_PARAMS should be ignored."""
        proc = self._make_processor({"language": "deu", "irrelevant_key": "value"})
        args = proc._build_ocrmypdf_args()
        assert "irrelevant_key" not in args
        assert args["language"] == "deu"


class TestShouldPerformOcr:
    """Tests for OCRProcessor._should_perform_ocr."""

    def _make_processor(self, config):
        return OCRProcessor(Path("/tmp/test.pdf"), config)

    def test_force_mode_always_true(self):
        """Force mode should always return True."""
        proc = self._make_processor({"mode": "force"})
        assert proc._should_perform_ocr() is True

    @patch("ocrprocessor.PDFProcessor")
    def test_no_text_returns_true(self, mock_pdf):
        """Should return True when PDF has no text."""
        mock_pdf.has_text.return_value = False
        proc = self._make_processor({"mode": "skip"})
        assert proc._should_perform_ocr() is True

    @patch("ocrprocessor.PDFProcessor")
    def test_already_ocrd_skip_mode_returns_false(self, mock_pdf):
        """Should return False when already OCR'd and mode is skip."""
        mock_pdf.has_text.return_value = True
        mock_pdf.check_metadata_pattern.return_value = True
        proc = self._make_processor({"mode": "skip"})
        assert proc._should_perform_ocr() is False

    @patch("ocrprocessor.PDFProcessor")
    def test_already_ocrd_redo_mode_returns_true(self, mock_pdf):
        """Should return True when already OCR'd and mode is redo."""
        mock_pdf.has_text.return_value = True
        mock_pdf.check_metadata_pattern.return_value = True
        proc = self._make_processor({"mode": "redo"})
        assert proc._should_perform_ocr() is True

    @patch("ocrprocessor.PDFProcessor")
    def test_scanner_signature_returns_true(self, mock_pdf):
        """Should return True when scanner signature found in metadata."""
        mock_pdf.has_text.return_value = True
        mock_pdf.check_metadata_pattern.return_value = False
        mock_pdf.get_metadata.return_value = {
            "/Creator": "Canon Scanner v2.0"
        }
        proc = self._make_processor({"mode": "skip"})
        assert proc._should_perform_ocr() is True

    @patch("ocrprocessor.PDFProcessor")
    def test_text_pdf_no_scanner_returns_false(self, mock_pdf):
        """Should return False for a normal text PDF without scanner signatures."""
        mock_pdf.has_text.return_value = True
        mock_pdf.check_metadata_pattern.return_value = False
        mock_pdf.get_metadata.return_value = {
            "/Creator": "Microsoft Word",
            "/Producer": "macOS Quartz",
        }
        proc = self._make_processor({"mode": "skip"})
        assert proc._should_perform_ocr() is False


class TestProcess:
    """Tests for OCRProcessor.process."""

    @patch("ocrprocessor.PDFProcessor")
    def test_process_skips_when_not_needed(self, mock_pdf):
        """Should return file_path without OCR when not needed."""
        mock_pdf.has_text.return_value = True
        mock_pdf.check_metadata_pattern.return_value = True

        proc = OCRProcessor(Path("/tmp/test.pdf"), {"mode": "skip"})
        result = proc.process()
        assert result == Path("/tmp/test.pdf")

    @patch("ocrprocessor.ocrmypdf")
    @patch("ocrprocessor.PDFProcessor")
    def test_process_runs_ocr_when_needed(self, mock_pdf, mock_ocrmypdf, tmp_path):
        """Should call ocrmypdf.ocr when OCR is needed."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        mock_pdf.has_text.return_value = False

        proc = OCRProcessor(test_file, {"mode": "skip", "language": "deu+eng"})
        result = proc.process()

        mock_ocrmypdf.ocr.assert_called_once()
        assert result == test_file

    @patch("ocrprocessor.ocrmypdf")
    @patch("ocrprocessor.PDFProcessor")
    def test_process_removes_image_dpi_for_pdf(self, mock_pdf, mock_ocrmypdf, tmp_path):
        """Should not pass image_dpi to ocrmypdf for PDF files."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        mock_pdf.has_text.return_value = False

        proc = OCRProcessor(test_file, {"mode": "skip", "image_dpi": 300})
        proc.process()

        call_kwargs = mock_ocrmypdf.ocr.call_args[1]
        assert "image_dpi" not in call_kwargs

    @patch("ocrprocessor.ocrmypdf")
    @patch("ocrprocessor.PDFProcessor")
    def test_process_raises_on_empty_output(self, mock_pdf, mock_ocrmypdf, tmp_path):
        """Should raise FileProcessingError if output file is empty after OCR."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        mock_pdf.has_text.return_value = False

        # Simulate ocrmypdf emptying the file
        def mock_ocr(*args, **kwargs):
            test_file.write_bytes(b"")

        mock_ocrmypdf.ocr.side_effect = mock_ocr

        proc = OCRProcessor(test_file, {"mode": "skip"})
        with pytest.raises(FileProcessingError, match="empty or missing"):
            proc.process()
