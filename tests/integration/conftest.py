"""
Conftest for integration tests.

Integration tests require the real ocrmypdf / pikepdf / pdfminer / psycopg
modules — not the MagicMock fallbacks installed by the parent conftest.
If a real module cannot be imported, all integration tests are skipped
at collection time.
"""

import shutil
import sys
from unittest.mock import MagicMock

import pytest

_REQUIRED_MODULES = [
    "ocrmypdf",
    "pikepdf",
    "pdfminer.high_level",
    "img2pdf",
    "PIL",
]

_missing = []
for mod_name in _REQUIRED_MODULES:
    mod = sys.modules.get(mod_name)
    if isinstance(mod, MagicMock):
        _missing.append(mod_name)
        continue
    try:
        __import__(mod_name)
    except Exception as exc:
        _missing.append(f"{mod_name} ({exc})")

if _missing:
    pytest.skip(
        f"Integration tests require real modules: {', '.join(_missing)}",
        allow_module_level=True,
    )

if shutil.which("tesseract") is None:
    pytest.skip(
        "Integration tests require the `tesseract` binary on PATH",
        allow_module_level=True,
    )
