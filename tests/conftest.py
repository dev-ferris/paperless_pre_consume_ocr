import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure src/ is on the path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Heavy external dependencies that are required by the source modules.
# In a full CI environment (with system libraries like tesseract, ghostscript,
# qpdf, libcrypto, etc.), these import cleanly and the real implementations
# are used — required by the integration tests.
# In a lightweight environment where the native libraries are missing, we
# fall back to MagicMock stubs so the unit tests (which patch behaviour
# explicitly) can still run.
_OPTIONAL_MODULES = [
    "ocrmypdf",
    "pdfminer",
    "pdfminer.high_level",
    "pdfminer.layout",
    "pdfminer.pdfinterp",
    "pdfminer.pdfdevice",
    "pdfminer.pdfpage",
    "pdfminer.pdfdocument",
    "pdfminer.converter",
    "pdfminer.image",
    "pikepdf",
    "psycopg",
    "psycopg.rows",
]

for mod_name in _OPTIONAL_MODULES:
    if mod_name in sys.modules:
        continue
    try:
        __import__(mod_name)
    except BaseException:
        # Use BaseException to also catch native panics (e.g. pyo3
        # PanicException raised when cryptography's rust bindings fail
        # to load in lightweight environments).
        sys.modules[mod_name] = MagicMock()
