#!/usr/bin/env python3
"""
Entry point for ``python -m paperless_pre_consume_ocr`` and for direct
execution as a stand-alone script (e.g. when Paperless-NGX invokes the
file via ``PAPERLESS_PRE_CONSUME_SCRIPT`` with the source mounted into
the container).

Direct execution by Paperless uses ``subprocess.run`` which ``exec()``s
this file as a top-level script — there is no package context, so we
must:

* declare a shebang so the kernel knows how to run it,
* avoid relative imports (they don't work without a parent package),
* put the package's parent directory on ``sys.path`` so the package can
  be imported by its real on-disk name.

The package name is derived from the *actual directory name* of this
file — not hard-coded — so the script also works when the source is
mounted under a different name (e.g. ``…/pre_consume_ocr/`` instead of
``…/paperless_pre_consume_ocr/``).

When invoked via ``python -m paperless_pre_consume_ocr`` the ``sys.path``
insertion and dynamic import are harmless: ``sys.path`` already contains
the parent directory and the package is already imported, so
``import_module`` just returns the cached entry.
"""

import importlib
import os
import sys

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_PKG_PARENT = os.path.dirname(_PKG_DIR)
_PKG_NAME = os.path.basename(_PKG_DIR)

if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

_cli = importlib.import_module(f"{_PKG_NAME}.cli")
main = _cli.main

if __name__ == "__main__":
    sys.exit(main())
