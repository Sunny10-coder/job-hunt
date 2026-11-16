"""WhatsApp text export parser.

The parser is a streaming state machine: any line that does not start a new
timestamped block is appended to the previous message body (multiline
messages), and lines that cannot be attributed are recorded as unresolved
records instead of being dropped.

Supported shapes (all seen in real exports):
  12/31/23, 11:59 PM - Alice: hello              (Android, 12h)
  31/12/2023, 23:59 - Alice: hello               (Android, 24h)
  [12/31/23, 11:59:59 PM] Alice: hello           (iOS)
  2023-12-31, 23:59 - Alice: hello               (ISO-ish)
  31.12.2023 23:59 - Alice: hello                (dot separators)
  12/31/23, 11:59 PM - Messages are end-to-end encrypted...
"""
from __future__ import annotations

import codecs
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .. import config, textutil
from ..hashing import message_fingerprint
from . import dates

BRACKET_LINE_RE = re.compile(
    r"^\[(?P<date>\d{1,4}[./-]\d{1,2}[./-]\d{1,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap]\.?[Mm]\.?)?)\]\s*(?P<rest>.*)$"
)
DASH_LINE_RE = re.compile(
    r"^(?P<date>\d{1,4}[./-]\d{1,2}[./-]\d{1,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap]\.?[Mm]\.?)?)"
    r"\s+[-\u2013\u2014]\s?(?P<rest>.*)$"
)
SENDER_SPLIT_RE = re.compile(r"^(?P<sender>[^:]{1,80}?):\s*(?P<body>.*)$", re.S)

MAX_SENDER_LEN = 80


@dataclass
class ParseIssue:
    code: str
    message: str
    line_no: int | None = None
    raw: str | None = None
    severity: str = "warning"


@dataclass
class ParsedMessage:
    sender_raw: str
    original_timestamp: str
    sent_at_local: str
    sent_at_utc: str
    tz_offset_min: int
    tz_ambiguous: bool
    raw_text: str
    body: str
    message_type: str
    is_system: bool
    is_deleted: bool
    is_edited: bool
    is_forwarded: bool
    has_media: bool
    media_ref: str | None
    source_ref: str
    parse_confidence: float
    content_hash: str
    session_id: str | None
    word_count: int
    char_count: int
    emojis: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    group_event: tuple[str, str | None, str | None] | None = None


@dataclass
class ParseStats:
    messages: int = 0
    system_messages: int = 0
    media_messages: int = 0
    deleted_messages: int = 0
    edited_messages: int = 0
    forwarded_messages: int = 0
    multiline_messages: int = 0
    unresolved_lines: int = 0
    date_order: str = "mdy"
    date_order_confidence: float = 0.0
    timezone: str = "UTC"
    ambiguous_timestamps: int = 0
    encoding: str = "utf-8"
    participants: int = 0
    language: str = "unknown"
    issues: list[ParseIssue] = field(default_factory=list)
    conversation_title: str = ""
    is_group: bool = False


def decode_text(raw: bytes) -> tuple[str, str]:
    """Decode an export with BOM awareness, never raising on bad bytes."""
    for bom, encoding in (
        (codecs.BOM_UTF8, "utf-8-sig"),
        (codecs.BOM_UTF32_LE, "utf-32-le"),
        (codecs.BOM_UTF32_BE, "utf-32-be"),
        (codecs.BOM_UTF16_LE, "utf-16-le"),
        (codecs.BOM_UTF16_BE, "utf-16-be"),
    ):
        if raw.startswith(bom):
            try:
                return raw.decode(encoding), encoding
            except UnicodeDecodeError:
                break
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace"), "utf-8-replace"


class WhatsAppTxtParser:
    def __init__(self, timezone_name: str = "UTC", date_order: str = "auto",
                 session_gap_minutes: int = config.SESSION_GAP_MINUTES,
                 sender_self_names: tuple[str, ...] = ("You",)):
        self.tz = timezone_name
        self.date_order_pref = date_order
        self.session_gap_minutes = session_gap_minutes
        self.sender_self_names = sender_self_names
        self.stats = ParseStats(
            timezone=timezone_name,
            date_order="mdy" if date_order == "auto" else date_order,
        )

    # ------------------------------------------------------------------ helpers
    def _match_block(self, line: str):
        m = BRACKET_LINE_RE.match(line)
        if m:
            return m
        return DASH_LINE_RE.match(line)

    def detect_order(self, lines: list[str], fallback: str = "mdy") -> dates.OrderDetection:
        tokens = []
        for line in lines:
            m = self._match_block(textutil.clean_line(line))
            if m:
                tokens.append(m.group("date"))
            if len(tokens) >= 400:
                break
        return dates.detect_date_order(tokens, fallback=fallback)

    def _conversation_title(self, path: Path | None, first_sender: str) -> str:
        if path is not None:
            stem = path.stem
            # Stored originals are prefixed with the evidence hash: strip it back off.
            stem = re.sub(r"^[0-9a-f]{8,16}[_-]", "", stem)
            stem = re.sub(r"^WhatsApp Chat (?:with |- ?|-\s*)?", "", stem, flags=re.I)
            stem = re.sub(r"^[-–—]\s*", "", stem)
            stem = re.sub(r"[_\s]+", " ", stem).strip(" -_.")
            if stem:
                return stem
        return f"Conversation with {first_sender}" if first_sender else "Unnamed conversation"

    # ------------------------------------------------------------------ parsing
    def parse_lines(self, lines: Iterator[str], *, source_label: str = "",
                    conversation_title: str | None = None) -> Iterator[ParsedMessage]:
        current: dict | None = None
        current_line_no = 0
        senders: set[str] = set()
        last_dt: datetime | None = None
        session_id: str | None = None
        body_parts: list[str] = []
        multiline = False

        def flush() -> Iterator[ParsedMessage]:
            nonlocal current, body_parts, multiline, last_dt, session_id
            if current is None:
                return iter(())
            body = "\n".join(body_parts).strip()
            yield self._build_message(current, body, session_id, source_label,
                                      was_multiline=multiline)

        for line_no, raw_line in enumerate(lines, start=1):
            line = textutil.clean_line(raw_line.rstrip("\n"))
            if not line.strip():
                # Blank lines inside a block are meaningful in multiline bodies.
                if current is not None:
                    body_parts.append("")
                continue
            m = self._match_block(line)
            if m is None:
                if current is None:
                    self.stats.unresolved_lines += 1
                    if len(self.stats.issues) < 400:
                        self.stats.issues.append(ParseIssue(
                            code="unresolved_line",
                            message="Line does not belong to any timestamped record",
                            line_no=line_no, raw=line[:500]))
                    continue
                body_parts.append(line)
                multiline = True
                continue

            ts = dates.parse_timestamp(
                m.group("date"), m.group("time"),
                self._effective_order(), self.tz)
            if ts is None:
                if current is not None:
                    body_parts.append(line)
                    multiline = True
                else:
                    self.stats.unresolved_lines += 1
                    if len(self.stats.issues) < 400:
                        self.stats.issues.append(ParseIssue(
                            code="invalid_timestamp",
                            message="Timestamp could not be interpreted",
                            line_no=line_no, raw=line[:500]))
                continue

            # A new block starts: emit the buffered one first.
            if current is not None:
                for msg in flush():
                    yield msg
                current = None
            body_parts = []
            multiline = False

            rest = m.group("rest")
            sender = ""
            body = rest
            sm = SENDER_SPLIT_RE.match(rest)
            if sm and "<attached:" not in rest[:12] and len(sm.group("sender")) <= MAX_SENDER_LEN:
                sender = sm.group("sender").strip()
                body = sm.group("body")
            if sender:
                senders.add(sender)

            if ts.ambiguous:
                self.stats.ambiguous_timestamps += 1

            utc_iso = dates.to_utc_iso(ts.utc)
            if last_dt is not None and (ts.naive_local - last_dt).total_seconds() > \
                    self.session_gap_minutes * 60:
                session_id = message_fingerprint("session", utc_iso, sender)[:16]
            elif session_id is None:
                session_id = message_fingerprint("session", utc_iso, sender)[:16]
            last_dt = ts.naive_local

            current = {
                "sender": sender,
                "original_timestamp": f"{m.group('date')} {m.group('time')}",
                "local": dates.to_local_iso(ts.naive_local),
                "utc": utc_iso,
                "offset": ts.offset_minutes,
                "ambiguous": ts.ambiguous,
                "line_no": line_no,
                "rest": rest,
            }
            body_parts = [body]

        if current is not None:
            for msg in flush():
                yield msg

        self.stats.participants = len(senders)
        self.stats.is_group = len(senders) > 2 or (
            len(senders) == 2 and not any(s in self.sender_self_names for s in senders)
        )
        if conversation_title and not self.stats.conversation_title:
            self.stats.conversation_title = conversation_title

    def _effective_order(self) -> str:
        return self.stats.date_order if self.stats.date_order else "mdy"

    def _build_message(self, ctx: dict, body: str, session_id: str | None,
                       source_label: str, was_multiline: bool) -> ParsedMessage:
        raw_text = textutil.normalize_text(body)
        working, edited = textutil.strip_edited_suffix(raw_text)
        working, forwarded = textutil.strip_forwarded_prefix(working)
        placeholder = textutil.media_placeholder_kind(working)
        attached = textutil.attached_filename(raw_text)
        deleted = textutil.is_deleted_body(working)
        system_event = None
        is_system = False
        sender = ctx["sender"]

        if not sender:
            is_system = True
            system_event = textutil.detect_system_event(raw_text)
        elif placeholder is None and not working and not attached:
            # "Sender:" with an empty body still counts as a text record.
            working = ""

        message_type = "text"
        if placeholder:
            message_type = placeholder if placeholder in {
                "image", "video", "audio", "sticker", "gif", "document", "contact_card"
            } else "media"
        elif attached:
            message_type = "document"
        elif is_system:
            message_type = "system"
        elif deleted:
            message_type = "deleted"
        elif working.startswith("http") and len(working.split()) == 1:
            message_type = "link"

        sig = textutil.references(working if message_type != "media" else "")
        confidence = 1.0
        if is_system and system_event is None:
            confidence = 0.7
        if was_multiline:
            confidence = min(confidence, 0.98)
        if not raw_text:
            confidence = min(confidence, 0.6)

        self.stats.messages += 1
        if is_system:
            self.stats.system_messages += 1
        if placeholder or attached:
            self.stats.media_messages += 1
        if deleted:
            self.stats.deleted_messages += 1
        if edited:
            self.stats.edited_messages += 1
        if forwarded:
            self.stats.forwarded_messages += 1
        if was_multiline:
            self.stats.multiline_messages += 1

        return ParsedMessage(
            sender_raw=sender,
            original_timestamp=ctx["original_timestamp"],
            sent_at_local=ctx["local"],
            sent_at_utc=ctx["utc"],
            tz_offset_min=ctx["offset"],
            tz_ambiguous=ctx["ambiguous"],
            raw_text=raw_text,
            body=working,
            message_type=message_type,
            is_system=is_system,
            is_deleted=deleted,
            is_edited=edited,
            is_forwarded=forwarded,
            has_media=bool(placeholder or attached),
            media_ref=attached or (placeholder if placeholder else None),
            source_ref=f"{source_label}:{ctx['line_no']}",
            parse_confidence=confidence,
            content_hash=message_fingerprint(ctx["utc"], sender, working or raw_text),
            session_id=session_id,
            word_count=len(working.split()),
            char_count=len(working),
            emojis=sig.emojis,
            urls=sig.urls,
            emails=sig.emails,
            phones=sig.phones,
            group_event=system_event,
        )

    # ------------------------------------------------------------------ file API
    def parse_file(self, path: Path | str, source_label: str = "") -> Iterator[ParsedMessage]:
        p = Path(path)
        size = p.stat().st_size
        if size > config.MAX_TEXT_FILE_BYTES:
            raise ValueError(f"Text export exceeds size limit: {size} bytes")
        raw = p.read_bytes()
        text, encoding = decode_text(raw)
        self.stats.encoding = encoding
        lines = text.splitlines()

        if self.date_order_pref == "auto":
            det = self.detect_order(lines, fallback="mdy")
            self.stats.date_order = det.order
            self.stats.date_order_confidence = det.confidence
            if not det.decisive:
                self.stats.issues.append(ParseIssue(
                    code="ambiguous_date_order",
                    message=(
                        "Date order could not be proven from the data; assumed "
                        f"{det.order.upper()}. Verify timestamps in the import report."),
                    severity="info"))
        else:
            self.stats.date_order = self.date_order_pref
            self.stats.date_order_confidence = 1.0

        hint = textutil.detect_language_guess("".join(lines[:200]))
        self.stats.language = hint
        self.stats.conversation_title = self._conversation_title(p, "")

        yield from self.parse_lines(iter(lines), source_label=source_label or p.name)
        if self.stats.participants > 0 and self.stats.participants > 2:
            self.stats.is_group = True
