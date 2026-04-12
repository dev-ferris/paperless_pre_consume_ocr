# paperless_pre_consume_ocr

OCR-Vorverarbeitungs-Skript für [Paperless-NGX](https://github.com/paperless-ngx/paperless-ngx), das Dokumente bereits **vor dem Konsum** durch Paperless mit OCR versieht.

## Motivation

Standardmäßig erzeugt Paperless-NGX beim Konsum eines Dokuments zusätzlich eine separate Archiv-Datei mit dem durchsuchbaren OCR-Text. Das führt zu doppeltem Speicherverbrauch (Original + Archiv).

Dieses Skript löst das Problem, indem es:

1. Das Originaldokument **vor dem Konsum** mit OCR versieht
2. Den OCR-Text direkt in das Original-PDF einbettet
3. Paperless so konfiguriert werden kann, dass keine Archiv-Dateien mehr erzeugt werden

Das Ergebnis: Nur **Original + Thumbnail** werden gespeichert, und das Original ist bereits durchsuchbar.

## Features

- **PDF-Verarbeitung**: Führt OCR mit `ocrmypdf` durch und nutzt die OCR-Einstellungen aus der Paperless-NGX-Datenbank
- **Bild-zu-PDF-Konvertierung**: Wandelt Bilder (JPEG, PNG, TIFF, BMP, WebP, etc.) in PDFs um, die Paperless dann konsumieren kann
- **Intelligente OCR-Erkennung**: Überspringt OCR bei bereits verarbeiteten oder textbasierten PDFs, erkennt Scanner-Signaturen in den Metadaten
- **Bildoptimierung**: DPI-Anpassung, Alpha-Kanal-Entfernung, EXIF-Orientierung, Größenanpassung
- **Vollständig konfigurierbar** über die Paperless-NGX-UI (OCR-Einstellungen werden aus der Datenbank gelesen)

## Architektur

```
src/
├── paperless_pre_consume_ocr.py  # Einstiegspunkt
├── paperlessenvironment.py       # Umgebungsvariablen + DB-Config
├── imageconverter.py             # Bild → PDF Konvertierung
├── ocrprocessor.py               # OCR-Verarbeitung via ocrmypdf
├── pdfprocessor.py               # PDF-Metadaten & Text-Extraktion
├── exceptions.py                 # Custom Exceptions
└── logger.py                     # Logging-Setup
```

### Verarbeitungsablauf

```
Dokument im consume/ Ordner
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
│ Bild? │ │ PDF? │
└───────┘ └──────┘
    │         │
    ▼         ▼
Bild→PDF  OCR mit
Exit 10   ocrmypdf
    │         │
    │         ▼
    │    Paperless
    │    konsumiert
    │    das PDF
    │    (bereits OCR)
    │
    ▼
Paperless konsumiert
das konvertierte PDF
(separater Durchlauf)
```

Bilder werden in zwei Phasen verarbeitet:
1. **Phase 1**: Bild → PDF-Konvertierung, Platzierung im Consume-Ordner, Exit-Code `10` (bricht den Konsum des Originals ab)
2. **Phase 2**: Paperless greift das konvertierte PDF auf, das Skript führt dann OCR darauf aus

## Installation

### Voraussetzungen

- Python ≥ 3.10
- Paperless-NGX
- Systemabhängigkeiten: `tesseract-ocr`, `ghostscript`, `qpdf`, `unpaper` (werden von `ocrmypdf` benötigt)

### Python-Abhängigkeiten

```bash
pip install -e .
```

Oder manuell:

```bash
pip install ocrmypdf Pillow img2pdf pikepdf pdfminer.six "psycopg[binary]"
```

## Konfiguration

### Paperless-NGX Umgebungsvariablen

Füge diese Variablen zu deinem `docker-compose.yml` oder deiner `paperless.conf` hinzu:

```yaml
environment:
  # Pfad zum Pre-Consume-Skript
  PAPERLESS_PRE_CONSUME_SCRIPT: /usr/src/paperless/scripts/paperless_pre_consume_ocr.py

  # Datenbank-Zugang (wird vom Skript verwendet, um OCR-Einstellungen zu lesen)
  PAPERLESS_DBHOST: db
  PAPERLESS_DBPORT: 5432
  PAPERLESS_DBNAME: paperless
  PAPERLESS_DBUSER: paperless
  PAPERLESS_DBPW: paperless
```

Zusätzlich die Archiv-Datei-Erzeugung deaktivieren (optional, aber empfohlen):

```yaml
environment:
  PAPERLESS_OCR_SKIP_ARCHIVE_FILE: with_text
```

### Vom Skript verwendete Umgebungsvariablen

Paperless-NGX setzt diese automatisch beim Aufruf des Pre-Consume-Skripts:

| Variable | Beschreibung |
|----------|--------------|
| `DOCUMENT_WORKING_PATH` | Pfad zur aktuell verarbeiteten Datei (erforderlich) |
| `DOCUMENT_SOURCE_PATH` | Originalpfad des Dokuments (optional) |
| `DOCUMENT_CONSUME_PATH` | Pfad zum Consume-Ordner (Default: `/usr/src/paperless/consume`) |
| `TASK_ID` | ID des Verarbeitungs-Tasks (optional) |
| `PAPERLESS_DBHOST` | Datenbank-Host (erforderlich) |
| `PAPERLESS_DBPORT` | Datenbank-Port (Default: `5432`) |
| `PAPERLESS_DBNAME` | Datenbank-Name (Default: `paperless`) |
| `PAPERLESS_DBUSER` | Datenbank-Benutzer (Default: `paperless`) |
| `PAPERLESS_DBPW` | Datenbank-Passwort (Default: `paperless`) |

## Exit-Codes

| Code | Bedeutung |
|------|-----------|
| `0` | Erfolg (OCR wurde durchgeführt oder war nicht nötig) |
| `10` | Bild wurde zu PDF konvertiert — Original-Konsum wird abgebrochen, konvertiertes PDF wird separat konsumiert |
| `2` | Fehler bei der Dateiverarbeitung |
| `3` | Unerwarteter Fehler |
| `os.EX_CONFIG` (`78`) | Konfigurations- oder Datenbankfehler |
| `os.EX_NOINPUT` (`66`) | Datei nicht gefunden |

## Unterstützte Formate

**OCR-Verarbeitung**: `.pdf`

**Bild-Konvertierung**: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`, `.tif`, `.webp`, `.gif`, `.ico`, `.pcx`, `.ppm`, `.pgm`, `.pbm`

## Tests

```bash
pip install -e ".[dev]"
pytest tests/
```

Die Testsuite umfasst 70 Unit-Tests und deckt alle Module ab.

## Lizenz

Siehe [LICENSE](LICENSE).
