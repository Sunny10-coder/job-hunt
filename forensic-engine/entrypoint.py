"""PyInstaller entry point for the frozen forensic engine sidecar.

The Tauri shell starts this binary with ``--host``/``--port`` arguments and a
``WFS_TOKEN`` environment variable; everything else is identical to
``python -m wfs_engine.cli``.
"""

from __future__ import annotations

import multiprocessing
import sys

from wfs_engine.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
