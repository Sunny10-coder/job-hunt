#!/usr/bin/env bash
# Package the Python forensic engine as a single-file sidecar binary.
#
#   ./scripts/build_sidecar.sh [target-triple]
#
# The engine is frozen with PyInstaller so end users never install Python.
# Tauri's externalBin convention requires the target triple in the file name:
#   src-tauri/binaries/wfs-engine-x86_64-pc-windows-msvc.exe
#
# Requires: python 3.12 with the requirements in forensic-engine/requirements.txt
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE="$ROOT/forensic-engine"
OUT="$ROOT/src-tauri/binaries"
TRIPLE="${1:-}"

if [[ -z "$TRIPLE" ]]; then
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) TRIPLE="x86_64-unknown-linux-gnu" ;;
    Darwin-arm64) TRIPLE="aarch64-apple-darwin" ;;
    Darwin-x86_64) TRIPLE="x86_64-apple-darwin" ;;
    MINGW64*|MSYS*|CYGWIN*) TRIPLE="x86_64-pc-windows-msvc" ;;
    *) echo "Unsupported host; pass the target triple explicitly." >&2; exit 1 ;;
  esac
fi

PYTHON="${PYTHON:-python3}"
mkdir -p "$OUT"
cd "$ENGINE"

# PyInstaller's --add-data separator differs between POSIX and Windows hosts.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) DATA_SEP=";" ;;
  *) DATA_SEP=":" ;;
esac

"$PYTHON" -m pip install --quiet --upgrade pyinstaller
"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name wfs-engine \
  --distpath "$ENGINE/dist" \
  --workpath "$ENGINE/build/pyinstaller" \
  --specpath "$ENGINE/build" \
  --paths "$ENGINE" \
  --hidden-import wfs_engine.api.server \
  --hidden-import wfs_engine.parsers.whatsapp_txt \
  --hidden-import wfs_engine.parsers.sqlite_wa \
  --hidden-import wfs_engine.reporting.render_pdf \
  --hidden-import wfs_engine.reporting.render_xlsx \
  --collect-submodules wfs_engine \
  --add-data "$ENGINE/wfs_engine/migrations${DATA_SEP}wfs_engine/migrations" \
  entrypoint.py

EXT=""
if [[ "$TRIPLE" == *windows* ]]; then EXT=".exe"; fi
cp "$ENGINE/dist/wfs-engine$EXT" "$OUT/wfs-engine-$TRIPLE$EXT"
echo "sidecar -> $OUT/wfs-engine-$TRIPLE$EXT"
