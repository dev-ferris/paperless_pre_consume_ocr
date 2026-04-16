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

The project is laid out as a regular Python package and installed via
`pip`. Once installed, the console script `paperless-pre-consume-ocr`
is on `PATH`.

```
src/paperless_pre_consume_ocr/
├── __init__.py
├── __main__.py             # `python -m paperless_pre_consume_ocr` entry point
├── cli.py                  # Console script (paperless-pre-consume-ocr)
├── environment.py          # Environment variables + DB config
├── image_converter.py      # Image → PDF conversion
├── image_ops.py            # Pure Pillow image transforms
├── ocr.py                  # OCR processing via ocrmypdf
├── pdf.py                  # PDF metadata & text extraction
├── exceptions.py           # Custom exceptions
└── logger.py               # Logging setup
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

### Install the package

From a clone of this repository:

```bash
pip install .
```

This installs the runtime dependencies and exposes the
`paperless-pre-consume-ocr` console script. It can also be invoked as a
module:

```bash
python -m paperless_pre_consume_ocr
```

For development (tests, lint, type-check):

```bash
pip install -e ".[dev]"
```

## Configuration

### Hooking the script into Paperless-NGX

Paperless-NGX runs a single executable referenced by the
`PAPERLESS_PRE_CONSUME_SCRIPT` environment variable before each document
is consumed. The steps below show how to wire this project into a
typical Docker Compose deployment.

#### 1. Build a custom Paperless image with the package installed

The cleanest approach is to extend the upstream Paperless-NGX image and
`pip install` this package into it. The package's runtime dependencies
(`img2pdf`, `psycopg`, `ocrmypdf`, `Pillow`, `pikepdf`, `pdfminer.six`)
are pulled in automatically.

```dockerfile
FROM ghcr.io/paperless-ngx/paperless-ngx:latest

COPY . /tmp/paperless_pre_consume_ocr
RUN pip install --no-cache-dir /tmp/paperless_pre_consume_ocr \
    && rm -rf /tmp/paperless_pre_consume_ocr
```

This installs the `paperless-pre-consume-ocr` console script at
`/usr/local/bin/paperless-pre-consume-ocr` inside the container.

> **Alternative: mount the source instead of building an image.** If
> you'd rather bind-mount the repository into a vanilla Paperless-NGX
> container, point `PAPERLESS_PRE_CONSUME_SCRIPT` at the package's
> `__main__.py` (e.g. `/usr/src/paperless_user_scripts/pre_consume_ocr/__main__.py`).
> The file ships with a shebang and is marked executable, and it adds
> its own parent directory to `sys.path`, so direct execution by
> Paperless works out of the box. You still need to install the runtime
> dependencies (`img2pdf`, `psycopg`, …) inside the container — the
> upstream image only ships with some of them.

#### 2. Point Paperless at the script

Add the following to the `environment:` block of the `webserver`
service in `docker-compose.yml`:

```yaml
    environment:
      # The console script installed by pip
      PAPERLESS_PRE_CONSUME_SCRIPT: /usr/local/bin/paperless-pre-consume-ocr

      # Skip writing the separate archive file — the original is now
      # already searchable, so the archive copy is redundant.
      PAPERLESS_OCR_SKIP_ARCHIVE_FILE: with_text

      # Optional: move image originals to Paperless's trash folder
      # instead of deleting them after conversion. If unset (or the
      # path does not exist), the originals are deleted. The same
      # folder is used by Paperless itself for trashed documents, so
      # mount it on a persistent volume if you want to be able to
      # recover files.
      PAPERLESS_EMPTY_TRASH_DIR: /usr/src/paperless/trash

      # Database access (used by the script to read the OCR settings
      # configured in the Paperless-NGX UI). These are normally already
      # present in your compose file for Paperless itself.
      PAPERLESS_DBHOST: db
      PAPERLESS_DBPORT: 5432
      PAPERLESS_DBNAME: paperless
      PAPERLESS_DBUSER: paperless
      PAPERLESS_DBPW: paperless

      # Optional: bump the script's log verbosity for debugging.
      # PAPERLESS_PRE_CONSUME_LOG_LEVEL: DEBUG
```

#### 3. Configure OCR settings in the Paperless-NGX UI

The script reads its OCR configuration at runtime from the Paperless
database — the same settings you see in the admin UI under
**Administration → Settings → General → OCR**. There is **no** separate
config file for this project: whatever you configure in the UI is what
`ocrmypdf` will be invoked with on the next consumed document.

The following UI fields are picked up (all optional — sensible
defaults from `DEFAULT_OCR_CONFIG` apply for any field left blank):

| UI field | DB column | Typical value | Notes |
|----------|-----------|---------------|-------|
| OCR language | `language` | `deu+eng` | Multiple languages joined with `+` |
| OCR mode | `mode` | `skip` | `skip` is recommended — see below |
| Image DPI | `image_dpi` | `300` | Only used for rasterised input |
| OCR output type | `output_type` | `pdf` | Use `pdf` unless you specifically want `pdfa` |
| Deskew | `deskew` | `true` | Straightens slightly rotated scans |
| Rotate pages | `rotate_pages` | `true` | Auto-rotates pages based on text orientation |
| Rotate pages threshold | `rotate_pages_threshold` | `8.0` | Confidence threshold for auto-rotation |
| Color conversion strategy | `color_conversion_strategy` | `LeaveColorUnchanged` | |
| Max image pixels | `max_image_pixels` | `178956970` | Protects against decompression bombs |

**Recommended OCR mode: `skip`.** With `skip`, the pre-consume script
only runs OCR on PDFs that do not already contain a text layer, and
leaves already-searchable PDFs untouched. This avoids re-OCR when a
scan has been processed before and also plays well with Paperless's
own OCR stage (which is set to skip by default), so nothing gets
OCR'd twice.

Use `force` or `redo` only if you specifically want the pre-consume
script to replace an existing text layer — for example when the
upstream OCR was low-quality.

> **Tip:** after changing the UI settings, the next document you drop
> into the consume folder immediately uses the new configuration; no
> Paperless restart is required.

#### 4. Restart and verify

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
| `DOCUMENT_WORKING_PATH` | Path to Paperless's scratch copy of the file being processed (required) |
| `DOCUMENT_SOURCE_PATH` | Path to the original file in the consume folder. Used to dispose of the original image after conversion so it does not keep re-triggering the consumer (optional but recommended) |
| `DOCUMENT_CONSUME_PATH` | Path to the consume folder (default: `/usr/src/paperless/consume`) |
| `TASK_ID` | ID of the processing task (optional) |
| `PAPERLESS_DBHOST` | Database host (required) |
| `PAPERLESS_DBPORT` | Database port (default: `5432`) |
| `PAPERLESS_DBNAME` | Database name (default: `paperless`) |
| `PAPERLESS_DBUSER` | Database user (default: `paperless`) |
| `PAPERLESS_DBPW` | Database password (default: `paperless`) |
| `PAPERLESS_EMPTY_TRASH_DIR` | If set and the directory exists, converted image originals are **moved** there instead of being deleted. Absolute paths are used as-is; relative paths are resolved first against the current working directory, then against the parent of `DOCUMENT_CONSUME_PATH`. Falls back to deletion if the path cannot be resolved. |
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
pytest tests/ --ignore=tests/integration
```

Integration tests (which exercise the real `ocrmypdf`/`tesseract`
pipeline) live under `tests/integration/` and are skipped automatically
when the binaries or native libraries are missing.

## License

See [LICENSE](LICENSE).
