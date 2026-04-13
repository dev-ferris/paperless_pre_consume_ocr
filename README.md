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

### Hooking the script into Paperless-NGX

Paperless-NGX runs a single executable file referenced by the
`PAPERLESS_PRE_CONSUME_SCRIPT` environment variable before each document
is consumed. The steps below show how to wire this project into a
typical Docker Compose deployment.

#### 1. Make the source available inside the container

Mount the `src/` directory of this repository into the Paperless
container, e.g. at `/usr/src/paperless/scripts`:

```yaml
services:
  webserver:
    image: ghcr.io/paperless-ngx/paperless-ngx:latest
    volumes:
      - ./paperless_pre_consume_ocr/src:/usr/src/paperless/scripts:ro
      - ./consume:/usr/src/paperless/consume
      - ./data:/usr/src/paperless/data
      - ./media:/usr/src/paperless/media
```

> The script imports its sibling modules (`ocrprocessor.py`,
> `imageconverter.py`, …) via relative imports, so the **whole `src/`
> folder** must be mounted — not just the entry-point file.

#### 2. Install the Python dependencies inside the container

Paperless-NGX already ships with `ocrmypdf`, `Pillow`, `pikepdf` and
`pdfminer.six`. The only extras the script needs are `img2pdf` and
`psycopg`. The cleanest way is a small custom image:

```dockerfile
FROM ghcr.io/paperless-ngx/paperless-ngx:latest

RUN pip install --no-cache-dir img2pdf "psycopg[binary]"
```

Alternatively you can install them at container start via a
`command:` override, but a dedicated image is more reliable.

#### 3. Point Paperless at the script

Add the following to the `environment:` block of the `webserver`
service in `docker-compose.yml`:

```yaml
    environment:
      # Path to the pre-consume script (inside the container)
      PAPERLESS_PRE_CONSUME_SCRIPT: /usr/src/paperless/scripts/paperless_pre_consume_ocr.py

      # Skip writing the separate archive file — the original is now
      # already searchable, so the archive copy is redundant.
      PAPERLESS_OCR_SKIP_ARCHIVE_FILE: with_text

      # Database access (used by the script to read the OCR settings
      # configured in the Paperless-NGX UI). These are normally already
      # present in your compose file for Paperless itself.
      PAPERLESS_DBHOST: db
      PAPERLESS_DBPORT: 5432
      PAPERLESS_DBNAME: paperless
      PAPERLESS_DBUSER: paperless
      PAPERLESS_DBPW: paperless
```

#### 4. Make the entry point executable

Paperless executes the script directly, so the entry-point file needs
the executable bit set on the host:

```bash
chmod +x paperless_pre_consume_ocr/src/paperless_pre_consume_ocr.py
```

The shebang at the top of the file (`#!/usr/bin/env python3`) ensures
it runs with the container's Python interpreter.

#### 5. Restart and verify

```bash
docker compose up -d --build
docker compose logs -f webserver | grep -i "pre.consume\|ocr"
```

Drop a scanned PDF or an image into the consume folder. The Paperless
log should now show the pre-consume script running and `ocrmypdf`
embedding the text layer **before** Paperless itself takes over.

> A ready-to-use `Dockerfile` and `docker-compose.example.yml` covering
> the steps above are provided in [`examples/docker/`](examples/docker/).

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
| `PAPERLESS_PRE_CONSUME_LOG_LEVEL` | Log level for the pre-consume script (default: `INFO`, e.g. `DEBUG`) |

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
