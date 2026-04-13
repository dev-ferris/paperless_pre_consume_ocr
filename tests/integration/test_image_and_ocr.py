"""
Integration tests that exercise the real image-to-PDF and OCR pipeline.

These tests cover both supported input types end-to-end:
  * **Image input**: a synthetic PNG/JPG with rendered text is converted
    to a PDF via ImageConverter, then OCR'd via OCRProcessor.
  * **Native PDF input**: a fresh image-only PDF (no text layer) is
    built directly with img2pdf — independently of ImageConverter — and
    handed straight to OCRProcessor / PDFProcessor.
"""

import os
from pathlib import Path

import img2pdf
import pytest
from PIL import Image, ImageDraw, ImageFont

from exceptions import FileNotSupported
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


@pytest.fixture
def scan_pdf(tmp_path: Path) -> Path:
    """
    Build a native image-only PDF (no text layer) directly with img2pdf,
    independently of ImageConverter. Simulates a freshly scanned document.
    """
    img_path = _create_text_image(tmp_path / "_scan_source.png")
    pdf_path = tmp_path / "scan.pdf"
    with open(pdf_path, "wb") as fh:
        fh.write(img2pdf.convert(str(img_path)))
    img_path.unlink()
    return pdf_path


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

    def test_unsupported_format_raises(self, tmp_path: Path, consume_dir: Path):
        weird = tmp_path / "note.txt"
        weird.write_text("not an image")
        with pytest.raises(FileNotSupported):
            ImageConverter(weird, consume_dir)


class TestOCRIntegration:
    """Real OCR runs through ocrmypdf on a generated text PDF."""

    def test_ocr_extracts_text_from_image_pdf(self, text_png: Path, consume_dir: Path):
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


class TestNativePDFInput:
    """OCR and text detection on a real PDF input (not produced by ImageConverter)."""

    def test_scan_pdf_has_no_text_initially(self, scan_pdf: Path):
        """A freshly scanned image-only PDF must not be reported as text-bearing."""
        assert scan_pdf.exists()
        assert scan_pdf.read_bytes()[:5] == b"%PDF-"
        assert PDFProcessor.has_text(scan_pdf) is False

    def test_ocr_processes_native_scan_pdf(self, scan_pdf: Path):
        """OCRProcessor should add a text layer to a native scan PDF."""
        size_before = scan_pdf.stat().st_size

        processor = OCRProcessor(
            scan_pdf,
            {
                "mode": "force",
                "language": "eng",
                "output_type": "pdf",
            },
        )
        result = processor.process()

        assert result == scan_pdf  # processed in place
        assert result.exists()
        assert result.stat().st_size >= size_before

        # Text layer is now present
        assert PDFProcessor.has_text(result) is True

        from pdfminer.high_level import extract_text

        extracted = extract_text(str(result)).upper()
        assert "HELLO" in extracted or "PAPERLESS" in extracted

    def test_ocr_skipped_on_native_pdf_already_processed(self, scan_pdf: Path):
        """Running OCRProcessor twice with mode=skip must not re-OCR."""
        # First pass: add text layer
        OCRProcessor(
            scan_pdf,
            {"mode": "skip", "language": "eng", "output_type": "pdf"},
        ).process()
        assert PDFProcessor.has_text(scan_pdf) is True

        # ocrmypdf metadata signature must be present after processing
        assert PDFProcessor.check_metadata_pattern(scan_pdf, r"Tesseract|ocrmypdf") is True

        # Second pass: should be a no-op
        size_after_first = scan_pdf.stat().st_size
        OCRProcessor(
            scan_pdf,
            {"mode": "skip", "language": "eng", "output_type": "pdf"},
        ).process()
        assert scan_pdf.exists()
        # File should be unchanged (skip path returns early)
        assert scan_pdf.stat().st_size == size_after_first

    def test_pdfprocessor_metadata_on_native_pdf(self, scan_pdf: Path):
        """PDFProcessor.get_metadata should return real metadata for a native PDF."""
        meta = PDFProcessor.get_metadata(scan_pdf)
        assert meta is not None
        assert meta["page_count"] == 1
        assert meta["pdf_version"]
        assert meta["encrypted"] is False


class TestEndToEndPipeline:
    """Full pipeline: image dropped into consume → OCR'd PDF."""

    def test_pipeline_image_to_searchable_pdf(self, text_png: Path, consume_dir: Path):
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
