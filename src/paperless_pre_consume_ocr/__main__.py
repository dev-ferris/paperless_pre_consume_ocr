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
* put the package's parent directory on ``sys.path`` so the absolute
  import below resolves.

When invoked via ``python -m paperless_pre_consume_ocr`` the
``sys.path`` insertion is a harmless no-op — the package is already
importable.
"""

import os
import sys

_PKG_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from paperless_pre_consume_ocr.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
