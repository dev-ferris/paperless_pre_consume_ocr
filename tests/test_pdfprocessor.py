from pathlib import Path
from unittest.mock import MagicMock, patch

from pdfprocessor import PDFProcessor


class TestHasText:
    """Tests for PDFProcessor.has_text."""

    @patch("pdfprocessor.extract_text")
    def test_has_text_returns_true(self, mock_extract):
        """Should return True for PDF with meaningful text."""
        mock_extract.return_value = "This is a meaningful document with text content."
        assert PDFProcessor.has_text(Path("/tmp/test.pdf")) is True

    @patch("pdfprocessor.extract_text")
    def test_empty_text_returns_false(self, mock_extract):
        """Should return False for PDF with no text."""
        mock_extract.return_value = ""
        assert PDFProcessor.has_text(Path("/tmp/test.pdf")) is False

    @patch("pdfprocessor.extract_text")
    def test_none_text_returns_false(self, mock_extract):
        """Should return False when extract_text returns None."""
        mock_extract.return_value = None
        assert PDFProcessor.has_text(Path("/tmp/test.pdf")) is False

    @patch("pdfprocessor.extract_text")
    def test_whitespace_only_returns_false(self, mock_extract):
        """Should return False for whitespace-only text."""
        mock_extract.return_value = "   \n\t\n   "
        assert PDFProcessor.has_text(Path("/tmp/test.pdf")) is False

    @patch("pdfprocessor.extract_text")
    def test_non_printable_text_returns_false(self, mock_extract):
        """Should return False when text has too many non-printable characters."""
        # 90% non-printable
        mock_extract.return_value = "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0eab"
        assert PDFProcessor.has_text(Path("/tmp/test.pdf")) is False

    @patch("pdfprocessor.extract_text")
    def test_extraction_error_returns_false(self, mock_extract):
        """Should return False on extraction error."""
        mock_extract.side_effect = Exception("Corrupted PDF")
        assert PDFProcessor.has_text(Path("/tmp/test.pdf")) is False


class TestGetMetadata:
    """Tests for PDFProcessor.get_metadata."""

    def test_nonexistent_file_returns_none(self, tmp_path):
        """Should return None for non-existent file."""
        result = PDFProcessor.get_metadata(tmp_path / "nonexistent.pdf")
        assert result is None

    def test_non_pdf_file_returns_none(self, tmp_path):
        """Should return None for non-PDF file."""
        txt_file = tmp_path / "test.txt"
        txt_file.touch()
        result = PDFProcessor.get_metadata(txt_file)
        assert result is None

    @patch("pdfprocessor.pikepdf")
    def test_metadata_extracted(self, mock_pikepdf, tmp_path):
        """Should extract metadata from a valid PDF."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy")

        mock_doc = MagicMock()
        mock_doc.pages = [MagicMock(), MagicMock()]  # 2 pages
        mock_doc.pdf_version = "1.4"
        mock_doc.is_encrypted = False
        mock_doc.docinfo = {"/Creator": "TestApp", "/Producer": "TestLib"}
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)
        mock_pikepdf.Pdf.open.return_value = mock_doc

        result = PDFProcessor.get_metadata(pdf_file)

        assert result is not None
        assert result["page_count"] == 2
        assert result["pdf_version"] == "1.4"
        assert result["encrypted"] is False
        assert result["/Creator"] == "TestApp"


class TestCheckMetadataPattern:
    """Tests for PDFProcessor.check_metadata_pattern."""

    @patch.object(PDFProcessor, "get_metadata")
    def test_pattern_found(self, mock_get_metadata):
        """Should return True when pattern matches metadata."""
        mock_get_metadata.return_value = {
            "/Creator": "Tesseract OCR",
            "/Producer": "ocrmypdf",
        }
        assert (
            PDFProcessor.check_metadata_pattern(Path("/tmp/test.pdf"), r"Tesseract|ocrmypdf")
            is True
        )

    @patch.object(PDFProcessor, "get_metadata")
    def test_pattern_not_found(self, mock_get_metadata):
        """Should return False when pattern doesn't match metadata."""
        mock_get_metadata.return_value = {
            "/Creator": "Microsoft Word",
            "/Producer": "macOS Quartz",
        }
        assert (
            PDFProcessor.check_metadata_pattern(Path("/tmp/test.pdf"), r"Tesseract|ocrmypdf")
            is False
        )

    @patch.object(PDFProcessor, "get_metadata")
    def test_no_metadata_returns_false(self, mock_get_metadata):
        """Should return False when metadata is None."""
        mock_get_metadata.return_value = None
        assert PDFProcessor.check_metadata_pattern(Path("/tmp/test.pdf"), r"Tesseract") is False
