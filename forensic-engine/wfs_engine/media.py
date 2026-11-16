"""Media forensics: metadata, thumbnails, hashing, duplicates, libraries.

Embedded metadata is reported as found and explicitly described as untrusted:
consistent EXIF never proves an image is authentic.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config, db
from .hashing import sha256_file

try:  # optional dependency, graceful degradation
    from PIL import Image, ExifTags
    HAVE_PIL = True
except Exception:  # noqa: BLE001
    Image = None  # type: ignore[assignment]
    ExifTags = None  # type: ignore[assignment]
    HAVE_PIL = False

THUMB_SIZE = 480


@dataclass
class ToolAvailability:
    exiftool: str | None
    ffprobe: str | None
    ffmpeg: str | None


def tools() -> ToolAvailability:
    def which(*names: str) -> str | None:
        for name in names:
            found = shutil.which(name)
            if found:
                return found
        return None

    return ToolAvailability(which("exiftool"), which("ffprobe"), which("ffmpeg"))


def _safe_path(path_str: str | None) -> Path | None:
    if not path_str:
        return None
    p = Path(path_str)
    try:
        resolved = p.resolve()
        resolved.relative_to(config.data_dir().resolve())
    except (ValueError, OSError):
        return None
    return resolved if resolved.is_file() else None


def average_hash(path: Path) -> str | None:
    if not HAVE_PIL:
        return None
    try:
        with Image.open(path) as img:
            small = img.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
            pixels = list(small.getdata())
    except Exception:  # noqa: BLE001
        return None
    mean = sum(pixels) / len(pixels)
    bits = "".join("1" if px > mean else "0" for px in pixels)
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def _mp4_duration_ms(path: Path) -> int | None:
    """Minimal MVHD parse so video duration works without ffprobe."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(min(path.stat().st_size, 4 * 1024 * 1024))
    except OSError:
        return None
    idx = data.find(b"mvhd")
    if idx < 0:
        return None
    try:
        version = data[idx + 4]
        if version == 1:
            timescale = int.from_bytes(data[idx + 20:idx + 24], "big")
            duration = int.from_bytes(data[idx + 24:idx + 32], "big")
        else:
            timescale = int.from_bytes(data[idx + 12:idx + 16], "big")
            duration = int.from_bytes(data[idx + 16:idx + 20], "big")
        if timescale:
            return int(duration / timescale * 1000)
    except (IndexError, ZeroDivisionError):
        return None
    return None


def inspect(conn, attachment_id: str, *, force: bool = False,
            thumbnail: bool = True) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM attachments WHERE id=?", (attachment_id,)).fetchone()
    if not row:
        raise KeyError("attachment not found")
    attachment = dict(row)
    path = _safe_path(attachment["stored_path"])
    meta: dict[str, Any] = db.json_load(attachment["meta_json"], {})
    if path is None:
        conn.execute("UPDATE attachments SET missing=1 WHERE id=?", (attachment_id,))
        return {**attachment, "missing": True, "meta": meta,
                "note": "File is not present in the case evidence directory."}
    if meta and not force:
        return {**attachment, "meta": meta}

    updates: dict[str, Any] = {}
    meta["inspected_at"] = db.now_utc()
    meta["tool_availability"] = {
        "exiftool": bool(tools().exiftool), "ffprobe": bool(tools().ffprobe)}
    updates["sha256"] = attachment["sha256"] or sha256_file(path)
    updates["size_bytes"] = path.stat().st_size

    media_type = attachment["media_type"]
    if media_type == "image" and HAVE_PIL:
        try:
            with Image.open(path) as img:
                updates["width"], updates["height"] = img.size
                meta["format"] = img.format
                meta["mode"] = img.mode
                exif = {}
                try:
                    raw = img.getexif()
                    for tag_id, value in raw.items():
                        name = ExifTags.TAGS.get(tag_id, str(tag_id))
                        if isinstance(value, bytes):
                            value = f"<{len(value)} bytes>"
                        exif[name] = str(value)[:400]
                except Exception:  # noqa: BLE001
                    exif = {}
                meta["exif"] = exif
                if thumbnail:
                    thumb_dir = config.data_dir() / "thumbnails"
                    thumb_dir.mkdir(parents=True, exist_ok=True)
                    target = thumb_dir / f"{attachment_id}.jpg"
                    img2 = img.copy()
                    img2.thumbnail((THUMB_SIZE, THUMB_SIZE))
                    img2.convert("RGB").save(target, "JPEG", quality=82)
                    updates["relative_path"] = str(target)
                    meta["thumbnail"] = str(target)
        except Exception as exc:  # noqa: BLE001
            meta["image_error"] = str(exc)
        phash = average_hash(path)
        if phash:
            updates["phash"] = phash
    elif media_type == "video":
        duration = _mp4_duration_ms(path)
        if duration:
            updates["duration_ms"] = duration
        meta["duration_source"] = "mvhd atom" if duration else "unavailable"
        thumb = _video_thumbnail(path, attachment_id)
        if thumb:
            meta["thumbnail"] = str(thumb)
            updates["relative_path"] = str(thumb)
    elif media_type == "audio":
        duration = _audio_duration_ms(path)
        if duration:
            updates["duration_ms"] = duration
        peaks = waveform_peaks(path, buckets=200)
        if peaks:
            meta["waveform"] = peaks

    if updates:
        sets = ", ".join(f"{k}=?" for k in updates)
        conn.execute(f"UPDATE attachments SET {sets}, meta_json=? WHERE id=?",
                     (*updates.values(), db.json_dump(meta), attachment_id))
    conn.execute("DELETE FROM media_metadata WHERE attachment_id=?", (attachment_id,))
    for key, value in meta.items():
        if isinstance(value, (str, int, float)):
            conn.execute(
                "INSERT INTO media_metadata(id, attachment_id, key, value) VALUES(?,?,?,?)",
                (db.new_id(), attachment_id, key, str(value)[:2000]))
    updated = conn.execute("SELECT * FROM attachments WHERE id=?", (attachment_id,)).fetchone()
    return {**dict(updated), "meta": meta}


def _video_thumbnail(path: Path, attachment_id: str) -> Path | None:
    ff = tools().ffmpeg
    if not ff:
        return None
    thumb_dir = config.data_dir() / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    target = thumb_dir / f"{attachment_id}.jpg"
    try:
        subprocess.run(
            [ff, "-y", "-ss", "1", "-i", str(path), "-frames:v", "1", "-vf",
             f"scale={THUMB_SIZE}:-2", str(target)],
            capture_output=True, timeout=45, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return target if target.is_file() else None


def _audio_duration_ms(path: Path) -> int | None:
    if path.suffix.lower() == ".wav":
        try:
            import wave

            with wave.open(str(path), "rb") as wav:
                return int(wav.getnframes() / wav.getframerate() * 1000)
        except Exception:  # noqa: BLE001
            return None
    ff = tools().ffprobe
    if not ff:
        return _mp4_duration_ms(path)
    try:
        out = subprocess.run(
            [ff, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30, check=False)
        return int(float(out.stdout.strip()) * 1000) if out.stdout.strip() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def waveform_peaks(path: Path, buckets: int = 200) -> list[float]:
    """Downsample a WAV into normalised peaks for the waveform viewer."""
    if path.suffix.lower() != ".wav":
        return []
    try:
        import array
        import wave

        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            raw = wav.readframes(frames)
            width = wav.getsampwidth()
            channels = wav.getnchannels()
    except Exception:  # noqa: BLE001
        return []
    if not raw:
        return []
    if width == 2:
        samples = array.array("h", raw)
    elif width == 4:
        samples = array.array("i", raw)
    else:
        samples = array.array("b", raw)
    if channels > 1:
        samples = samples[::channels]
    total = len(samples)
    if total == 0:
        return []
    step = max(1, total // buckets)
    peak = float(max(abs(min(samples)), abs(max(samples))) or 1)
    out = []
    for start in range(0, total, step):
        chunk = samples[start:start + step]
        if not chunk:
            break
        out.append(round(max(abs(v) for v in chunk) / peak, 3))
    return out[:buckets]


def list_media(conn, case_id: str, *, media_type: str | None = None,
               conversation_id: str | None = None, search: str | None = None,
               linked: bool | None = None, limit: int = 100,
               offset: int = 0) -> dict[str, Any]:
    clauses = ["a.case_id=?"]
    params: list[Any] = [case_id]
    if media_type and media_type != "all":
        clauses.append("a.media_type=?")
        params.append(media_type)
    if conversation_id:
        clauses.append("a.conversation_id=?")
        params.append(conversation_id)
    if search:
        clauses.append("a.file_name LIKE ?")
        params.append(f"%{search}%")
    if linked is not None:
        clauses.append("a.linked=?")
        params.append(1 if linked else 0)
    where = " AND ".join(clauses)
    total = conn.execute(f"SELECT COUNT(*) FROM attachments a WHERE {where}",
                         params).fetchone()[0]
    rows = conn.execute(
        f"SELECT a.*, m.sent_at_utc, m.sender_raw, c.title AS conversation"
        f" FROM attachments a LEFT JOIN messages m ON m.id=a.message_id"
        f" LEFT JOIN conversations c ON c.id=a.conversation_id"
        f" WHERE {where} ORDER BY a.created_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset)).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["meta"] = db.json_load(item.pop("meta_json"), {})
        items.append(item)
    return {"total": total, "items": items, "limit": limit, "offset": offset}


def duplicates(conn, case_id: str) -> dict[str, Any]:
    by_hash = db.rows_to_list(conn.execute(
        "SELECT sha256, COUNT(*) AS count, SUM(size_bytes) AS bytes,"
        " GROUP_CONCAT(file_name, ' | ') AS names FROM attachments"
        " WHERE case_id=? AND sha256 IS NOT NULL GROUP BY sha256 HAVING count>1"
        " ORDER BY count DESC", (case_id,)))
    by_phash = db.rows_to_list(conn.execute(
        "SELECT phash, COUNT(*) AS count, GROUP_CONCAT(file_name, ' | ') AS names"
        " FROM attachments WHERE case_id=? AND phash IS NOT NULL"
        " GROUP BY phash HAVING count>1 ORDER BY count DESC", (case_id,)))
    return {
        "exact_duplicates": by_hash,
        "perceptual_duplicates": by_phash,
        "method": ("Exact duplicates share a SHA-256. Perceptual groups share an 8x8 "
                   "average hash, which indicates visually similar but re-encoded "
                   "images - never proof of identical content."),
    }


def missing_media(conn, case_id: str) -> dict[str, Any]:
    rows = db.rows_to_list(conn.execute(
        "SELECT m.id, m.sent_at_utc, m.sender_raw, m.message_type, m.media_ref,"
        " c.title AS conversation FROM messages m JOIN conversations c"
        " ON c.id=m.conversation_id WHERE m.case_id=? AND m.has_media=1"
        " AND m.id NOT IN (SELECT COALESCE(message_id,'') FROM attachments)"
        " ORDER BY m.sent_at_utc DESC LIMIT 500", (case_id,)))
    unlinked = db.rows_to_list(conn.execute(
        "SELECT id, file_name, media_type, size_bytes, sha256 FROM attachments"
        " WHERE case_id=? AND linked=0 LIMIT 500", (case_id,)))
    return {"placeholders": rows, "unlinked_files": unlinked,
            "note": "A placeholder means the export references media that was not "
                    "included; it is not evidence the media never existed."}


def media_timeline(conn, case_id: str) -> list[dict[str, Any]]:
    return db.rows_to_list(conn.execute(
        "SELECT a.id, a.file_name, a.media_type, a.size_bytes, a.missing,"
        " m.sent_at_utc, m.sender_raw, c.title AS conversation FROM attachments a"
        " LEFT JOIN messages m ON m.id=a.message_id"
        " LEFT JOIN conversations c ON c.id=a.conversation_id"
        " WHERE a.case_id=? ORDER BY m.sent_at_utc", (case_id,)))


def serve_path(conn, attachment_id: str) -> Path | None:
    row = conn.execute("SELECT stored_path FROM attachments WHERE id=?",
                       (attachment_id,)).fetchone()
    return _safe_path(row["stored_path"]) if row else None
