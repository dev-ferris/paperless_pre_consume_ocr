from unittest.mock import patch

import pytest
from PIL import Image

from exceptions import FileNotSupported, FileProcessingError
from imageconverter import ImageConverter


class TestImageConverterInit:
    """Tests for ImageConverter initialization."""

    def test_nonexistent_file_raises(self, tmp_path):
        """Should raise FileNotFoundError for non-existent source file."""
        with pytest.raises(FileNotFoundError):
            ImageConverter(tmp_path / "nonexistent.jpg", tmp_path)

    def test_creates_destination_folder(self, tmp_path):
        """Should create destination folder if it doesn't exist."""
        src = tmp_path / "test.jpg"
        src.touch()
        dest = tmp_path / "output" / "subdir"

        ImageConverter(src, dest)
        assert dest.exists()

    def test_supported_formats_construct(self, tmp_path):
        """Construction should succeed for every supported image format."""
        for ext in [".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".webp"]:
            src = tmp_path / f"test{ext}"
            src.touch()
            # Should not raise
            ImageConverter(src, tmp_path)

    def test_unsupported_format_raises(self, tmp_path):
        """Construction should raise FileNotSupported for non-image formats."""
        src = tmp_path / "test.pdf"
        src.touch()
        with pytest.raises(FileNotSupported, match="Unsupported image format"):
            ImageConverter(src, tmp_path)


class TestGetSaveFormat:
    """Tests for ImageConverter._get_save_format."""

    def test_png_stays_png(self, tmp_path):
        """PNG files should be saved as PNG."""
        src = tmp_path / "test.png"
        src.touch()
        converter = ImageConverter(src, tmp_path)
        assert converter._get_save_format(src) == "PNG"

    def test_jpg_saves_as_jpeg(self, tmp_path):
        """JPEG files should be saved as JPEG."""
        src = tmp_path / "test.jpg"
        src.touch()
        converter = ImageConverter(src, tmp_path)
        assert converter._get_save_format(src) == "JPEG"

    def test_tiff_saves_as_png(self, tmp_path):
        """TIFF files should be saved as PNG (lossless)."""
        src = tmp_path / "test.tiff"
        src.touch()
        converter = ImageConverter(src, tmp_path)
        assert converter._get_save_format(src) == "PNG"

    def test_bmp_saves_as_png(self, tmp_path):
        """BMP files should be saved as PNG (lossless)."""
        src = tmp_path / "test.bmp"
        src.touch()
        converter = ImageConverter(src, tmp_path)
        assert converter._get_save_format(src) == "PNG"


class TestRemoveAlphaChannel:
    """Tests for ImageConverter._remove_alpha_channel."""

    def _make_converter(self, tmp_path):
        src = tmp_path / "test.png"
        src.touch()
        return ImageConverter(src, tmp_path)

    def test_rgba_to_rgb(self, tmp_path):
        """RGBA images should be converted to RGB with white background."""
        converter = self._make_converter(tmp_path)
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        result = converter._remove_alpha_channel(img)
        assert result.mode == "RGB"

    def test_la_to_l(self, tmp_path):
        """LA images should be converted to L (grayscale)."""
        converter = self._make_converter(tmp_path)
        img = Image.new("LA", (100, 100), (128, 128))
        result = converter._remove_alpha_channel(img)
        assert result.mode == "L"

    def test_rgb_unchanged(self, tmp_path):
        """RGB images should be returned unchanged."""
        converter = self._make_converter(tmp_path)
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        result = converter._remove_alpha_channel(img)
        assert result.mode == "RGB"

    def test_pa_to_rgb(self, tmp_path):
        """PA images should be converted to RGB."""
        converter = self._make_converter(tmp_path)
        img = Image.new("PA", (100, 100))
        result = converter._remove_alpha_channel(img)
        assert result.mode == "RGB"


class TestConvertToRgb:
    """Tests for ImageConverter._convert_image_to_rgb."""

    def _make_converter(self, tmp_path):
        src = tmp_path / "test.png"
        src.touch()
        return ImageConverter(src, tmp_path)

    def test_grayscale_stays(self, tmp_path):
        """Grayscale images should not be converted."""
        converter = self._make_converter(tmp_path)
        img = Image.new("L", (100, 100), 128)
        result = converter._convert_image_to_rgb(img)
        assert result.mode == "L"

    def test_rgb_stays(self, tmp_path):
        """RGB images should not be converted."""
        converter = self._make_converter(tmp_path)
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        result = converter._convert_image_to_rgb(img)
        assert result.mode == "RGB"

    def test_cmyk_to_rgb(self, tmp_path):
        """CMYK images should be converted to RGB."""
        converter = self._make_converter(tmp_path)
        img = Image.new("CMYK", (100, 100), (0, 0, 0, 0))
        result = converter._convert_image_to_rgb(img)
        assert result.mode == "RGB"


class TestConvertToPdf:
    """Tests for ImageConverter.convert_to_pdf."""

    @patch("imageconverter.img2pdf")
    def test_convert_jpg_to_pdf(self, mock_img2pdf, tmp_path):
        """Should convert a JPEG image to PDF."""
        src = tmp_path / "test.jpg"
        dest = tmp_path / "output"
        dest.mkdir()

        # Create a real JPEG image
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        img.save(src, format="JPEG")

        # Mock img2pdf to return fake PDF bytes
        mock_img2pdf.convert.return_value = b"%PDF-1.4 fake pdf content"
        mock_img2pdf.get_layout_fun.return_value = None

        converter = ImageConverter(src, dest, quality="medium")
        result = converter.convert_to_pdf()

        assert result.exists()
        assert result.suffix == ".pdf"
        assert result.parent == dest
        assert result.stat().st_size > 0
        mock_img2pdf.convert.assert_called_once()

    @patch("imageconverter.img2pdf")
    def test_convert_png_to_pdf(self, mock_img2pdf, tmp_path):
        """Should convert a PNG image to PDF."""
        src = tmp_path / "test.png"
        dest = tmp_path / "output"
        dest.mkdir()

        img = Image.new("RGB", (100, 100), (0, 255, 0))
        img.save(src, format="PNG")

        mock_img2pdf.convert.return_value = b"%PDF-1.4 fake pdf content"
        mock_img2pdf.get_layout_fun.return_value = None

        converter = ImageConverter(src, dest, quality="medium")
        result = converter.convert_to_pdf()

        assert result.exists()
        assert result.suffix == ".pdf"
        assert result.stat().st_size > 0

    def test_temp_file_cleaned_up_on_error(self, tmp_path):
        """Temporary files should be cleaned up on conversion failure."""
        src = tmp_path / "test.jpg"

        # Create invalid JPEG (just some bytes)
        src.write_bytes(b"not a valid image")

        converter = ImageConverter(src, tmp_path, quality="medium")

        with pytest.raises(FileProcessingError):
            converter.convert_to_pdf()

        # Check no temp files remain
        temp_files = list(tmp_path.glob(".tmp_*.pdf"))
        assert len(temp_files) == 0
