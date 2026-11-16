"""Hardened archive extraction.

WhatsApp "export chat with media" produces a ZIP containing one text export and
the media files. Extraction must never escape the destination, never follow
symlinks, and never let a decompression bomb fill the disk.
"""
from __future__ import annotations

import os
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .. import config


class UnsafeArchiveError(Exception):
    pass


@dataclass
class ExtractedFile:
    entry_name: str
    path: Path
    size: int


@dataclass
class ExtractionReport:
    files: list[ExtractedFile] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    total_bytes: int = 0
    entry_count: int = 0


def _safe_name(name: str) -> str:
    """Flatten to a single safe path component."""
    # Normalise unicode and strip path separators / control characters.
    cleaned = unicodedata.normalize("NFC", name).replace("\\", "/")
    cleaned = cleaned.split("/")[-1]
    cleaned = "".join(ch for ch in cleaned if ch.isprintable() and ch not in '<>:"|?*')
    cleaned = cleaned.strip(" .")
    if not cleaned or cleaned in {".", ".."}:
        cleaned = "unnamed"
    return cleaned[:180]


def inspect_archive(path: Path) -> tuple[bool, list[str]]:
    """Pre-flight validation before any byte is written to disk."""
    problems: list[str] = []
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        if len(infos) > config.MAX_ARCHIVE_ENTRIES:
            problems.append(f"archive has {len(infos)} entries (limit {config.MAX_ARCHIVE_ENTRIES})")
        total = sum(i.file_size for i in infos)
        compressed = max(1, sum(i.compress_size for i in infos))
        if total > config.MAX_ARCHIVE_TOTAL_BYTES:
            problems.append("uncompressed size exceeds limit")
        if total / compressed > config.MAX_ARCHIVE_RATIO:
            problems.append("suspicious compression ratio (possible decompression bomb)")
        for info in infos:
            name = info.filename
            if name.endswith("/"):
                continue
            if name.startswith(("/", "\\")) or ":" in name.split("/")[0]:
                problems.append(f"absolute path entry: {name}")
            if ".." in Path(name).parts:
                problems.append(f"path traversal entry: {name}")
            if "\x00" in name:
                problems.append("NUL byte in entry name")
            mode = info.external_attr >> 16
            if mode and (mode & 0o170000) == 0o120000:
                problems.append(f"symlink entry: {name}")
    return (not problems, problems)


def extract(path: Path, dest: Path, *, max_files: int | None = None) -> ExtractionReport:
    dest.mkdir(parents=True, exist_ok=True)
    ok, problems = inspect_archive(path)
    if not ok:
        raise UnsafeArchiveError("; ".join(problems[:6]))

    report = ExtractionReport()
    used: set[str] = set()
    with zipfile.ZipFile(path) as zf:
        infos = [i for i in zf.infolist() if not i.filename.endswith("/")]
        report.entry_count = len(infos)
        if max_files is not None:
            infos = infos[:max_files]
        for info in infos:
            name = _safe_name(info.filename)
            if name in used:
                stem, suffix = os.path.splitext(name)
                counter = 1
                while f"{stem}_{counter}{suffix}" in used:
                    counter += 1
                name = f"{stem}_{counter}{suffix}"
            used.add(name)
            target = (dest / name).resolve()
            if dest.resolve() not in target.parents and target.parent != dest.resolve():
                report.skipped.append((info.filename, "escaped destination"))
                continue
            try:
                with zf.open(info) as src, open(target, "wb") as out:
                    copied = 0
                    while True:
                        chunk = src.read(1024 * 256)
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > config.MAX_FILE_BYTES:
                            raise UnsafeArchiveError("entry exceeds size limit")
                        out.write(chunk)
            except (zipfile.BadZipFile, RuntimeError, OSError, UnsafeArchiveError) as exc:
                report.skipped.append((info.filename, str(exc)))
                target.unlink(missing_ok=True)
                continue
            report.files.append(ExtractedFile(info.filename, target, target.stat().st_size))
            report.total_bytes += report.files[-1].size
    return report
