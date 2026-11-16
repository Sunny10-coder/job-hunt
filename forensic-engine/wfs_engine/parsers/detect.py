"""Source type detection from signatures, not just file extensions."""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .. import config

TEXT_EXTS = {".txt", ".text", ".log"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic"}
VIDEO_EXTS = {".mp4", ".mov", ".3gp", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_EXTS = {".opus", ".ogg", ".mp3", ".m4a", ".aac", ".wav", ".flac", ".amr"}
DOC_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
            ".vcf", ".zip", ".txt", ".apk"}


@dataclass
class SniffResult:
    source_type: str            # whatsapp_txt | whatsapp_zip | sqlite | image | video | audio | document | case_package | unknown
    media_type: str | None = None
    detail: str = ""
    warnings: list[str] = field(default_factory=list)


def read_head(path: Path, n: int = 4096) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(n)


def sniff(path: Path | str) -> SniffResult:
    p = Path(path)
    if not p.is_file():
        return SniffResult("unknown", detail="not a regular file")
    size = p.stat().st_size
    if size > config.MAX_FILE_BYTES:
        return SniffResult("unknown", detail=f"file exceeds {config.MAX_FILE_BYTES} byte limit")
    ext = p.suffix.lower()
    head = read_head(p, 64)

    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        if ext == ".wfszip":
            return SniffResult("case_package", detail="encrypted case package")
        try:
            with zipfile.ZipFile(p) as zf:
                names = zf.namelist()[:500]
        except zipfile.BadZipFile as exc:
            return SniffResult("unknown", detail=f"corrupt zip: {exc}")
        if any(n.endswith("manifest.json") for n in names):
            return SniffResult("case_package", detail="case package (manifest.json present)")
        txt = [n for n in names if n.lower().endswith((".txt", ".text"))]
        media = [n for n in names if Path(n).suffix.lower() in
                 IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS]
        if txt:
            return SniffResult(
                "whatsapp_zip",
                detail=f"{len(names)} entries, {len(txt)} text, {len(media)} media",
            )
        if media:
            return SniffResult("whatsapp_zip", detail=f"{len(media)} media entries, no text export")
        return SniffResult("document", "document", "zip archive without chat export")

    if head.startswith(b"SQLite format 3\x00"):
        return SniffResult("sqlite", detail="SQLite database")

    if head.startswith(b"\xff\xd8\xff"):
        return SniffResult("image", "image", "JPEG")
    if head.startswith(b"89504e470d0a1a0a"):
        return SniffResult("image", "image", "PNG")
    if head.startswith(b"GIF8"):
        return SniffResult("image", "image", "GIF")
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return SniffResult("image", "image", "WebP")
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return SniffResult("audio", "audio", "WAV")
    if head.startswith(b"RIFF") and head[8:12] == b"AVI ":
        return SniffResult("video", "video", "AVI")
    if head[4:8] == b"ftyp":
        brand = head[8:12].decode("ascii", "replace")
        if brand in {"heic", "heix", "mif1", "msf1"} or ext == ".heic":
            return SniffResult("image", "image", f"HEIF/{brand}")
        if brand in {"M4A ", "M4B "} or ext == ".m4a":
            return SniffResult("audio", "audio", f"M4A/{brand}")
        if brand in {"qt  "} or ext in {".mov", ".m4v"}:
            return SniffResult("video", "video", f"QuickTime/{brand}")
        return SniffResult("video", "video", f"ISO-BMFF/{brand}")
    if head.startswith(b"\x1aE\xdf\xa3"):
        return SniffResult("video", "video", "Matroska/WebM")
    if head.startswith(b"OggS"):
        return SniffResult("audio", "audio", "Ogg/Opus")
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return SniffResult("audio", "audio", "MPEG audio")
    if head.startswith(b"fLaC"):
        return SniffResult("audio", "audio", "FLAC")
    if head.startswith(b"%PDF"):
        return SniffResult("document", "document", "PDF")
    if head.startswith(b"\x00\x00\x00\x18ftyp"):
        return SniffResult("video", "video", "MP4")

    if ext in TEXT_EXTS or _looks_like_text(head):
        return SniffResult("whatsapp_txt", detail="text export")

    if ext in IMAGE_EXTS:
        return SniffResult("image", "image", f"by extension {ext}")
    if ext in VIDEO_EXTS:
        return SniffResult("video", "video", f"by extension {ext}")
    if ext in AUDIO_EXTS:
        return SniffResult("audio", "audio", f"by extension {ext}")
    if ext in DOC_EXTS:
        return SniffResult("document", "document", f"by extension {ext}")
    return SniffResult("unknown", detail=f"unrecognised signature ({head[:8]!r})")


def _looks_like_text(head: bytes) -> bool:
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False
