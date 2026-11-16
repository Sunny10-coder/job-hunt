"""Local speech-to-text for voice notes.

Engines, in priority order: an explicitly configured whisper.cpp binary, a
``whisper``/``whisper-cli`` binary on PATH, or the optional ``faster-whisper``
Python package. Nothing here calls a network service.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from . import db, media


class TranscriptionUnavailable(RuntimeError):
    pass


def engine_status() -> dict[str, Any]:
    binary = os.environ.get("WFS_WHISPER_BIN") or shutil.which("whisper-cli") \
        or shutil.which("whisper") or shutil.which("whisper.cpp")
    try:
        import faster_whisper  # noqa: F401
        have_faster = True
    except Exception:  # noqa: BLE001
        have_faster = False
    model_path = os.environ.get("WFS_WHISPER_MODEL") or ""
    return {
        "whisper_cpp": binary or None,
        "faster_whisper": have_faster,
        "model_path": model_path,
        "available": bool(binary or have_faster),
        "hint": ("Install whisper.cpp and set WFS_WHISPER_BIN + WFS_WHISPER_MODEL, or "
                 "pip install faster-whisper. Models are stored locally; no audio "
                 "leaves the machine."),
    }


def transcribe(conn, attachment_id: str, *, model: str | None = None,
               language: str | None = None, force: bool = False) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM attachments WHERE id=?", (attachment_id,)).fetchone()
    if not row:
        raise KeyError("attachment not found")
    attachment = dict(row)
    if attachment["media_type"] != "audio":
        raise ValueError("attachment is not audio")
    existing = conn.execute(
        "SELECT * FROM audio_transcripts WHERE attachment_id=? ORDER BY created_at DESC LIMIT 1",
        (attachment_id,)).fetchone()
    if existing and not force:
        return dict(existing)

    path = media.serve_path(conn, attachment_id)
    if path is None:
        raise ValueError("audio file is not available in the case evidence directory")

    status = engine_status()
    text: str | None = None
    detected_language = language
    confidence: float | None = None
    raw: dict[str, Any] = {}
    used_model = model or os.path.basename(status["model_path"] or "") or "whisper"

    if status["whisper_cpp"] and status["model_path"]:
        with tempfile.TemporaryDirectory() as tmp:
            cmd = [str(status["whisper_cpp"]), "-m", status["model_path"], "-f", str(path),
                   "-oj", "-of", str(Path(tmp) / "out")]
            if language:
                cmd += ["-l", language]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800,
                                  check=False)
            if proc.returncode != 0:
                raise TranscriptionUnavailable(
                    f"whisper.cpp failed: {proc.stderr.strip()[:400]}")
            out_file = Path(tmp) / "out.json"
            if out_file.is_file():
                data = json.loads(out_file.read_text(encoding="utf-8"))
                raw = data
                segments = data.get("transcription") or []
                text = (data.get("text") or "".join(s.get("text", "")
                                                    for s in segments)).strip()
                detected_language = detected_language or data.get("result", {}).get("language")
    elif status["faster_whisper"]:
        from faster_whisper import WhisperModel  # type: ignore

        whisper = WhisperModel(model or "base", device="cpu", compute_type="int8")
        segments, info = whisper.transcribe(str(path), language=language, vad_filter=True)
        collected = []
        for seg in segments:
            collected.append({"start": seg.start, "end": seg.end, "text": seg.text,
                              "avg_logprob": getattr(seg, "avg_logprob", None)})
        text = " ".join(s["text"].strip() for s in collected).strip()
        detected_language = detected_language or getattr(info, "language", None)
        raw = {"segments": collected}
        logs = [s["avg_logprob"] for s in collected if s.get("avg_logprob") is not None]
        if logs:
            confidence = round(sum(logs) / len(logs), 3)
    else:
        raise TranscriptionUnavailable(status["hint"])

    transcript_id = db.new_id()
    conn.execute(
        "INSERT INTO audio_transcripts(id, attachment_id, model, language, text, json,"
        " confidence, created_at, edited) VALUES(?,?,?,?,?,?,?,?,0)",
        (transcript_id, attachment_id, used_model, detected_language, text or "", 
         db.json_dump(raw), confidence, db.now_utc()))
    db.audit(conn, "audio.transcribe", None, "user", {
        "attachment_id": attachment_id, "model": used_model,
        "chars": len(text or "")})
    return dict(conn.execute("SELECT * FROM audio_transcripts WHERE id=?",
                             (transcript_id,)).fetchone())


def list_transcripts(conn, case_id: str) -> list[dict[str, Any]]:
    return db.rows_to_list(conn.execute(
        "SELECT t.*, a.file_name, a.duration_ms, a.id AS attachment_id,"
        " m.sent_at_utc, m.sender_raw, c.title AS conversation FROM audio_transcripts t"
        " JOIN attachments a ON a.id=t.attachment_id"
        " LEFT JOIN messages m ON m.id=a.message_id"
        " LEFT JOIN conversations c ON c.id=a.conversation_id"
        " WHERE a.case_id=? ORDER BY t.created_at DESC", (case_id,)))


def update_transcript(conn, transcript_id: str, text: str, language: str | None = None) -> dict:
    conn.execute(
        "UPDATE audio_transcripts SET text=?, language=COALESCE(?, language), edited=1"
        " WHERE id=?", (text, language, transcript_id))
    return dict(conn.execute("SELECT * FROM audio_transcripts WHERE id=?",
                             (transcript_id,)).fetchone())


def search_transcripts(conn, case_id: str, query: str) -> list[dict[str, Any]]:
    return db.rows_to_list(conn.execute(
        "SELECT t.id, t.text, t.language, a.file_name, a.id AS attachment_id,"
        " m.sent_at_utc FROM audio_transcripts t JOIN attachments a ON a.id=t.attachment_id"
        " LEFT JOIN messages m ON m.id=a.message_id"
        " WHERE a.case_id=? AND t.text LIKE ? LIMIT 100", (case_id, f"%{query}%")))
