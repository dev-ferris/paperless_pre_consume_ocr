import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure src/ is on the path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Mock heavy external dependencies that may not be fully available in test environments.
# These modules (ocrmypdf, pdfminer, pikepdf, psycopg) require native libraries
# (cryptography, cffi, etc.) that may not be present during CI or lightweight testing.
# The actual integration with these libraries is tested via integration tests.

_MOCK_MODULES = [
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

for mod_name in _MOCK_MODULES:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()
