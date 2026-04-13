"""Module entry point for `python -m paperless_pre_consume_ocr`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
