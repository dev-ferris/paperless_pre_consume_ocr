from unittest.mock import patch

import pytest
from PIL import Image

from paperless_pre_consume_ocr import image_converter, image_ops
from paperless_pre_consume_ocr.exceptions import FileNotSupported, FileProcessingError


class TestConvertImageToPdfValidation:
    """Tests for up-front argument validation in convert_image_to_pdf."""

    def test_nonexistent_file_raises(self, tmp_path):
        """Should raise FileNotFoundError for non-existent source file."""
        with pytest.raises(FileNotFoundError):
            image_converter.convert_image_to_pdf(tmp_path / "nonexistent.jpg", tmp_path)

    def test_unsupported_format_raises(self, tmp_path):
        """Should raise FileNotSupported for non-image formats."""
        src = tmp_path / "test.pdf"
        src.touch()
        with pytest.raises(FileNotSupported, match="Unsupported image format"):
            image_converter.convert_image_to_pdf(src, tmp_path)

    def test_invalid_quality_raises(self, tmp_path):
        """Should raise ValueError for an unknown quality profile."""
        src = tmp_path / "test.jpg"
        img = Image.new("RGB", (10, 10))
        img.save(src, format="JPEG")
        with pytest.raises(ValueError, match="Invalid quality"):
            image_converter.convert_image_to_pdf(src, tmp_path, quality="ultra")

    def test_creates_destination_folder(self, tmp_path, monkeypatch):
        """Should create destination folder if it doesn't exist."""
        src = tmp_path / "test.jpg"
        img = Image.new("RGB", (10, 10))
        img.save(src, format="JPEG")
        dest = tmp_path / "output" / "subdir"

        # Stub img2pdf so we don't actually render a PDF.
        with patch("paperless_pre_consume_ocr.image_converter.img2pdf") as mock_img2pdf:
            mock_img2pdf.convert.return_value = b"%PDF-1.4 fake"
            mock_img2pdf.get_layout_fun.return_value = None
            image_converter.convert_image_to_pdf(src, dest, quality="medium")

        assert dest.exists()


class TestSaveFormatFor:
    """Tests for image_converter._save_format_for."""

    def test_png_stays_png(self, tmp_path):
        assert image_converter._save_format_for(tmp_path / "test.png") == "PNG"

    def test_jpg_saves_as_jpeg(self, tmp_path):
        assert image_converter._save_format_for(tmp_path / "test.jpg") == "JPEG"

    def test_tiff_saves_as_png(self, tmp_path):
        assert image_converter._save_format_for(tmp_path / "test.tiff") == "PNG"

    def test_bmp_saves_as_png(self, tmp_path):
        assert image_converter._save_format_for(tmp_path / "test.bmp") == "PNG"


class TestRemoveAlpha:
    """Tests for image_ops.remove_alpha."""

    def test_rgba_to_rgb(self):
        """RGBA images should be converted to RGB with white background."""
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        result = image_ops.remove_alpha(img)
        assert result.mode == "RGB"

    def test_la_to_l(self):
        """LA images should be converted to L (grayscale)."""
        img = Image.new("LA", (100, 100), (128, 128))
        result = image_ops.remove_alpha(img)
        assert result.mode == "L"

    def test_rgb_unchanged(self):
        """RGB images should be returned unchanged."""
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        result = image_ops.remove_alpha(img)
        assert result.mode == "RGB"

    def test_pa_to_rgb(self):
        """PA images should be converted to RGB."""
        img = Image.new("PA", (100, 100))
        result = image_ops.remove_alpha(img)
        assert result.mode == "RGB"


class TestToRgb:
    """Tests for image_ops.to_rgb."""

    def test_grayscale_stays(self):
        """Grayscale images should not be converted."""
        img = Image.new("L", (100, 100), 128)
        result = image_ops.to_rgb(img)
        assert result.mode == "L"

    def test_rgb_stays(self):
        """RGB images should not be converted."""
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        result = image_ops.to_rgb(img)
        assert result.mode == "RGB"

    def test_cmyk_to_rgb(self):
        """CMYK images should be converted to RGB."""
        img = Image.new("CMYK", (100, 100), (0, 0, 0, 0))
        result = image_ops.to_rgb(img)
        assert result.mode == "RGB"


class TestConvertImageToPdf:
    """Tests for image_converter.convert_image_to_pdf."""

    @patch("paperless_pre_consume_ocr.image_converter.img2pdf")
    def test_convert_jpg_to_pdf(self, mock_img2pdf, tmp_path):
        """Should convert a JPEG image to PDF."""
        src = tmp_path / "test.jpg"
        dest = tmp_path / "output"
        dest.mkdir()

        Image.new("RGB", (100, 100), (255, 0, 0)).save(src, format="JPEG")

        mock_img2pdf.convert.return_value = b"%PDF-1.4 fake pdf content"
        mock_img2pdf.get_layout_fun.return_value = None

        result = image_converter.convert_image_to_pdf(src, dest, quality="medium")

        assert result.exists()
        assert result.suffix == ".pdf"
        assert result.parent == dest
        assert result.stat().st_size > 0
        mock_img2pdf.convert.assert_called_once()

    @patch("paperless_pre_consume_ocr.image_converter.img2pdf")
    def test_convert_png_to_pdf(self, mock_img2pdf, tmp_path):
        """Should convert a PNG image to PDF."""
        src = tmp_path / "test.png"
        dest = tmp_path / "output"
        dest.mkdir()

        Image.new("RGB", (100, 100), (0, 255, 0)).save(src, format="PNG")

        mock_img2pdf.convert.return_value = b"%PDF-1.4 fake pdf content"
        mock_img2pdf.get_layout_fun.return_value = None

        result = image_converter.convert_image_to_pdf(src, dest, quality="medium")

        assert result.exists()
        assert result.suffix == ".pdf"
        assert result.stat().st_size > 0

    def test_temp_file_cleaned_up_on_error(self, tmp_path):
        """Temporary files should be cleaned up on conversion failure."""
        src = tmp_path / "test.jpg"
        src.write_bytes(b"not a valid image")

        with pytest.raises(FileProcessingError):
            image_converter.convert_image_to_pdf(src, tmp_path, quality="medium")

        temp_files = list(tmp_path.glob(".tmp_*.pdf"))
        assert len(temp_files) == 0
