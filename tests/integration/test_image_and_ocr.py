"""
Integration tests that exercise the real image-to-PDF and OCR pipeline.

These tests:
  * Generate a synthetic image containing rendered text via Pillow.
  * Convert it to a PDF using ImageConverter (real img2pdf).
  * Run OCR on the resulting PDF using OCRProcessor (real ocrmypdf).
  * Verify that the output PDF contains the expected text via PDFProcessor
    (real pdfminer.six).
"""
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from imageconverter import ImageConverter
from ocrprocessor import OCRProcessor
from pdfprocessor import PDFProcessor


SAMPLE_TEXT = "HELLO PAPERLESS"


def _load_font(size: int = 96) -> ImageFont.ImageFont:
    """Load a TrueType font, falling back to PIL's default."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _create_text_image(path: Path, text: str = SAMPLE_TEXT) -> Path:
    """Create a high-DPI PNG image with rendered text suitable for OCR."""
    width, height = 1600, 500
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)
    font = _load_font()
    draw.text((80, 160), text, fill="black", font=font)
    img.save(path, dpi=(300, 300))
    return path


@pytest.fixture
def consume_dir(tmp_path: Path) -> Path:
    """A directory simulating the Paperless consume folder."""
    d = tmp_path / "consume"
    d.mkdir()
    return d


@pytest.fixture
def text_png(tmp_path: Path) -> Path:
    return _create_text_image(tmp_path / "sample.png")


@pytest.fixture
def text_jpg(tmp_path: Path) -> Path:
    src = _create_text_image(tmp_path / "_tmp.png")
    jpg_path = tmp_path / "sample.jpg"
    with Image.open(src) as img:
        img.convert("RGB").save(jpg_path, "JPEG", quality=95, dpi=(300, 300))
    src.unlink()
    return jpg_path


class TestImageConversionIntegration:
    """Real image → PDF conversion using img2pdf and Pillow."""

    def test_png_converts_to_pdf(self, text_png: Path, consume_dir: Path):
        converter = ImageConverter(text_png, consume_dir)
        pdf = converter.convert_to_pdf()

        assert pdf.exists()
        assert pdf.suffix == ".pdf"
        assert pdf.stat().st_size > 0
        assert pdf.parent == consume_dir
        # img2pdf writes the standard PDF header
        assert pdf.read_bytes()[:5] == b"%PDF-"

    def test_jpg_converts_to_pdf(self, text_jpg: Path, consume_dir: Path):
        converter = ImageConverter(text_jpg, consume_dir)
        pdf = converter.convert_to_pdf()

        assert pdf.exists()
        assert pdf.stat().st_size > 0
        assert pdf.read_bytes()[:5] == b"%PDF-"

    def test_unsupported_format_returns_original(self, tmp_path: Path, consume_dir: Path):
        weird = tmp_path / "note.txt"
        weird.write_text("not an image")
        converter = ImageConverter(weird, consume_dir)
        result = converter.convert_to_pdf()
        assert result == weird


class TestOCRIntegration:
    """Real OCR runs through ocrmypdf on a generated text PDF."""

    def test_ocr_extracts_text_from_image_pdf(
        self, text_png: Path, consume_dir: Path
    ):
        # Step 1: image → PDF
        converter = ImageConverter(text_png, consume_dir)
        pdf = converter.convert_to_pdf()

        # The freshly-converted PDF has no embedded text yet
        assert PDFProcessor.has_text(pdf) is False

        # Step 2: OCR the PDF
        processor = OCRProcessor(
            pdf,
            {
                "mode": "force",
                "language": "eng",
                "output_type": "pdf",
            },
        )
        result = processor.process()

        assert result.exists()
        assert result.stat().st_size > 0

        # Step 3: verify embedded text is present and readable
        assert PDFProcessor.has_text(result) is True

        from pdfminer.high_level import extract_text

        extracted = extract_text(str(result)).upper()
        # OCR is fuzzy; require at least one of the words to round-trip
        assert "HELLO" in extracted or "PAPERLESS" in extracted

    def test_ocr_skipped_for_text_pdf(self, text_png: Path, consume_dir: Path):
        # Generate a PDF with text and OCR it once
        converter = ImageConverter(text_png, consume_dir)
        pdf = converter.convert_to_pdf()

        first = OCRProcessor(
            pdf,
            {"mode": "skip", "language": "eng", "output_type": "pdf"},
        )
        first.process()

        # Second pass on a PDF that already contains an OCR layer:
        # should be a no-op when mode == "skip" and ocrmypdf metadata is
        # detected. We rely on _should_perform_ocr returning False here.
        second = OCRProcessor(
            pdf,
            {"mode": "skip", "language": "eng", "output_type": "pdf"},
        )
        result = second.process()
        assert result.exists()


class TestEndToEndPipeline:
    """Full pipeline: image dropped into consume → OCR'd PDF."""

    def test_pipeline_image_to_searchable_pdf(
        self, text_png: Path, consume_dir: Path
    ):
        # Phase 1: image → PDF in consume folder
        pdf = ImageConverter(text_png, consume_dir).convert_to_pdf()
        assert pdf.exists()
        assert pdf.parent == consume_dir

        # Phase 2: OCR the converted PDF (Paperless's second pass)
        OCRProcessor(
            pdf,
            {"mode": "force", "language": "eng", "output_type": "pdf"},
        ).process()

        # Final artifact is searchable
        assert PDFProcessor.has_text(pdf) is True
