# paperless_pre_consume_ocr

OCR pre-processing script for [Paperless-NGX](https://github.com/paperless-ngx/paperless-ngx) that applies OCR to documents **before** they are consumed by Paperless.

## Motivation

By default, Paperless-NGX creates a separate archive file containing the searchable OCR text whenever a document is consumed. This leads to duplicate storage (original + archive).

This script solves that problem by:

1. Running OCR on the original document **before** it is consumed
2. Embedding the OCR text directly into the original PDF
3. Allowing Paperless to be configured to skip generating archive files

The result: only the **original + thumbnail** are stored, and the original is already searchable.

## Features

- **PDF processing**: Runs OCR using `ocrmypdf` with OCR settings read from the Paperless-NGX database
- **Image-to-PDF conversion**: Converts images (JPEG, PNG, TIFF, BMP, WebP, etc.) to PDFs that Paperless then consumes
- **Smart OCR detection**: Skips OCR on already-processed or text-based PDFs, detects scanner signatures in metadata
- **Image optimization**: DPI adjustment, alpha channel removal, EXIF orientation handling, resizing
- **Fully configurable** through the Paperless-NGX UI (OCR settings are read from the database)

## Architecture

```
src/
├── paperless_pre_consume_ocr.py  # Entry point
├── paperlessenvironment.py       # Environment variables + DB config
├── imageconverter.py             # Image → PDF conversion
├── ocrprocessor.py               # OCR processing via ocrmypdf
├── pdfprocessor.py               # PDF metadata & text extraction
├── exceptions.py                 # Custom exceptions
└── logger.py                     # Logging setup
```

### Processing flow

```
Document in consume/ folder
         │
         ▼
┌─────────────────────┐
│ Pre-Consume Script  │
└─────────────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌──────┐
│Image? │ │ PDF? │
└───────┘ └──────┘
    │         │
    ▼         ▼
Image→PDF  OCR via
Exit 10    ocrmypdf
    │         │
    │         ▼
    │    Paperless
    │    consumes
    │    the PDF
    │    (already OCR'd)
    │
    ▼
Paperless consumes
the converted PDF
(separate run)
```

Images are processed in two phases:
1. **Phase 1**: Image → PDF conversion, placed in the consume folder, exit code `10` (cancels consumption of the original)
2. **Phase 2**: Paperless picks up the converted PDF, and the script then runs OCR on it

## Installation

### Prerequisites

- Python ≥ 3.10
- Paperless-NGX
- System dependencies: `tesseract-ocr`, `ghostscript`, `qpdf`, `unpaper` (required by `ocrmypdf`)

### Python dependencies

```bash
pip install -e .
```

Or manually:

```bash
pip install ocrmypdf Pillow img2pdf pikepdf pdfminer.six "psycopg[binary]"
```

## Configuration

### Paperless-NGX environment variables

Add these variables to your `docker-compose.yml` or `paperless.conf`:

```yaml
environment:
  # Path to the pre-consume script
  PAPERLESS_PRE_CONSUME_SCRIPT: /usr/src/paperless/scripts/paperless_pre_consume_ocr.py

  # Database access (used by the script to read OCR settings)
  PAPERLESS_DBHOST: db
  PAPERLESS_DBPORT: 5432
  PAPERLESS_DBNAME: paperless
  PAPERLESS_DBUSER: paperless
  PAPERLESS_DBPW: paperless
```

Also disable archive file generation (optional, but recommended):

```yaml
environment:
  PAPERLESS_OCR_SKIP_ARCHIVE_FILE: with_text
```

### Environment variables used by the script

Paperless-NGX sets these automatically when invoking the pre-consume script:

| Variable | Description |
|----------|-------------|
| `DOCUMENT_WORKING_PATH` | Path to the file currently being processed (required) |
| `DOCUMENT_SOURCE_PATH` | Original path of the document (optional) |
| `DOCUMENT_CONSUME_PATH` | Path to the consume folder (default: `/usr/src/paperless/consume`) |
| `TASK_ID` | ID of the processing task (optional) |
| `PAPERLESS_DBHOST` | Database host (required) |
| `PAPERLESS_DBPORT` | Database port (default: `5432`) |
| `PAPERLESS_DBNAME` | Database name (default: `paperless`) |
| `PAPERLESS_DBUSER` | Database user (default: `paperless`) |
| `PAPERLESS_DBPW` | Database password (default: `paperless`) |

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success (OCR was performed or not needed) |
| `10` | Image was converted to PDF — original consumption is cancelled, the converted PDF is consumed separately |
| `2` | File processing error |
| `3` | Unexpected error |
| `os.EX_CONFIG` (`78`) | Configuration or database error |
| `os.EX_NOINPUT` (`66`) | File not found |

## Supported formats

**OCR processing**: `.pdf`

**Image conversion**: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`, `.tif`, `.webp`, `.gif`, `.ico`, `.pcx`, `.ppm`, `.pgm`, `.pbm`

## Tests

```bash
pip install -e ".[dev]"
pytest tests/
```

The test suite contains 70 unit tests and covers all modules.

## License

See [LICENSE](LICENSE).
