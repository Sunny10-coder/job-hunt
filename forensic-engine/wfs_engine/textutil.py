"""Unicode-aware text helpers: emoji, tokens, references, media placeholders."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Zero-width / directionality marks that WhatsApp injects into exports.
INVISIBLE_MARKS = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
     0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF, 0x061C]
)

EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U0001F1E6-\U0001F1FF"
    "\u2600-\u27BF"
    "\u2B00-\u2BFF"
    "\u2190-\u21FF"
    "\u2900-\u297F"
    "\u3030\u303D\u3297\u3299"
    "\uFE0F\u20E3"
    "]"
)

URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<![\w.])\+?\d[\d\s().\-]{6,}\d(?![\w.])")

WORD_RE = re.compile(r"[^\s\.,;:!\?\"“”‘’\(\)\[\]\{\}/\\|<>=+*&^%$#@~`…]+")
WORD_STRIP = " -–—_\u00a0'"

MEDIA_PLACEHOLDER_RE = re.compile(
    r"^\s*(?:<)?\s*(?P<kind>image|video|audio|sticker|gif|document|contact card|media|file)"
    r"\s+omitted\s*(?:>)?\s*$",
    re.IGNORECASE,
)
ATTACHED_FILE_RE = re.compile(
    r"(?:<attached:\s*(?P<a1>[^>]+)>|(?P<a2>[^\s]+\.(?:jpg|jpeg|png|webp|gif|mp4|mov|3gp|opus|ogg|mp3|m4a|aac|pdf|docx?|xlsx?|pptx?|txt|vcf|zip))\s*\(file attached\))",
    re.IGNORECASE,
)
EDITED_SUFFIX_RE = re.compile(
    r"\s*(?:<this message was edited>|\(edited\)|\[edited\])\s*$", re.IGNORECASE
)
FORWARDED_PREFIX_RE = re.compile(r"^\s*(?:\[forwarded\]|\(forwarded\))\s*", re.IGNORECASE)

DELETED_BODIES = {
    "this message was deleted",
    "this message was deleted.",
    "you deleted this message",
    "you deleted this message.",
}

SYSTEM_EVENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("group_created", re.compile(r"created (?:the )?group|created this group", re.I)),
    ("participant_added", re.compile(r"\badded\b|\bjoined using this group's invite link\b", re.I)),
    ("participant_removed", re.compile(r"\bremoved\b|\bleft\b", re.I)),
    ("subject_changed", re.compile(r"changed the subject|changed this group's subject", re.I)),
    ("icon_changed", re.compile(r"changed this group's icon|changed the group icon", re.I)),
    ("phone_changed", re.compile(r"changed (?:their|his|her) phone number", re.I)),
    ("settings_changed", re.compile(r"changed the settings|turned on|turned off", re.I)),
    ("disappearing_changed", re.compile(r"disappearing messages", re.I)),
    ("e2ee_notice", re.compile(r"end-to-end encrypted|messages and calls are", re.I)),
    ("call", re.compile(r"^(?:missed )?(?:voice|video) call", re.I)),
]

STOPWORDS = {
    # English
    "the", "and", "you", "that", "for", "are", "with", "this", "have", "but", "not",
    "was", "your", "what", "when", "how", "its", "it's", "all", "can", "will", "just",
    "from", "they", "them", "then", "there", "here", "about", "would", "could", "should",
    "been", "were", "his", "her", "she", "him", "our", "out", "get", "got", "like",
    "know", "think", "going", "want", "yes", "yeah", "ok", "okay", "one", "now", "also",
    "very", "much", "more", "some", "any", "who", "why", "did", "does", "doing", "at",
    "on", "in", "of", "to", "is", "it", "be", "as", "or", "if", "do", "my", "me", "we",
    # Hindi / Malayalam / Tamil common particles
    "hai", "hain", "kya", "nahi", "nahin", "aur", "mera", "meri", "aap", "main", "tha",
    "theek", "ആണ്", "ഇല്ല", "അത്", "ഞാൻ", "നിങ്ങൾ", "എന്ത്", "ഒരു", "ആണോ",
    "இது", "அது", "நான்", "நீ", "என்ன", "ஒரு", "இல்லை",
    # Arabic
    "في", "من", "على", "إلى", "هذا", "هذه", "أن", "لا", "ما", "مع",
    # English contractions that survive tokenisation
    "i'm", "i'll", "i've", "don't", "doesn't", "didn't", "can't", "won't", "it's",
    "that's", "you're", "we're", "they're", "let's", "isn't", "aren't",
}


@dataclass
class TextSignals:
    urls: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    emojis: list[str] = field(default_factory=list)
    words: list[str] = field(default_factory=list)


def clean_line(line: str) -> str:
    """Remove BOM/LRM/LRE marks that prefix most WhatsApp export lines."""
    return line.translate(INVISIBLE_MARKS)


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text).strip()


def extract_emojis(text: str) -> list[str]:
    return EMOJI_RE.findall(text)


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for raw in WORD_RE.findall(text.lower()):
        token = raw.strip(WORD_STRIP)
        if not token or token in STOPWORDS:
            continue
        if len(token) < 2 and not token.isdigit():
            continue
        if not any(ch.isalpha() for ch in token):
            continue
        out.append(token)
    return out


def signals(text: str) -> TextSignals:
    return TextSignals(
        urls=[u.rstrip(").,;") for u in URL_RE.findall(text)],
        emails=EMAIL_RE.findall(text),
        phones=[p.strip() for p in PHONE_RE.findall(text)],
        emojis=extract_emojis(text),
        words=tokenize(text),
    )


def references(text: str) -> TextSignals:
    """Reference/emoji signals only - no word tokenisation.

    Import uses this: word frequencies are computed at analysis time, so the
    per-message tokenisation pass is pure overhead in the import hot path.
    """
    return TextSignals(
        urls=[u.rstrip(").,;") for u in URL_RE.findall(text)],
        emails=EMAIL_RE.findall(text),
        phones=[p.strip() for p in PHONE_RE.findall(text)],
        emojis=extract_emojis(text),
    )


def media_placeholder_kind(body: str) -> str | None:
    m = MEDIA_PLACEHOLDER_RE.match(body)
    if not m:
        return None
    kind = m.group("kind").lower().replace(" ", "_")
    return {
        "media": "media",
        "file": "document",
        "contact_card": "contact_card",
    }.get(kind, kind)


def attached_filename(body: str) -> str | None:
    m = ATTACHED_FILE_RE.search(body)
    if not m:
        return None
    return (m.group("a1") or m.group("a2") or "").strip()


def strip_edited_suffix(body: str) -> tuple[str, bool]:
    m = EDITED_SUFFIX_RE.search(body)
    if not m:
        return body, False
    return body[: m.start()].rstrip(), True


def strip_forwarded_prefix(body: str) -> tuple[str, bool]:
    m = FORWARDED_PREFIX_RE.match(body)
    if not m:
        return body, False
    return body[m.end():], True


def is_deleted_body(body: str) -> bool:
    return body.strip().lower() in DELETED_BODIES


def detect_system_event(text: str) -> tuple[str, str | None, str | None] | None:
    """Best-effort classification of a WhatsApp system notice.

    Returns (event_type, actor, target) or None. Never infers membership that
    the export does not state.
    """
    plain = normalize_text(text)
    for kind, pattern in SYSTEM_EVENT_PATTERNS:
        if not pattern.search(plain):
            continue
        actor: str | None = None
        target: str | None = None
        m = re.match(r"^(.+?)\s+(?:added|removed|changed|created|left|joined)\b", plain, re.I)
        if m:
            actor = m.group(1).strip()[:120]
        m2 = re.search(r"added\s+(.+?)(?:\s|$)", plain, re.I)
        if m2:
            target = m2.group(1).strip()[:120]
        if kind == "call":
            actor = None
        return kind, actor, target
    return None


def detect_language_guess(text: str) -> str:
    """Script-based language hint (not a statistical language identifier)."""
    counts = {
        "malayalam": sum(1 for c in text if 0x0D00 <= ord(c) <= 0x0D7F),
        "hindi": sum(1 for c in text if 0x0900 <= ord(c) <= 0x097F),
        "tamil": sum(1 for c in text if 0x0B80 <= ord(c) <= 0x0BFF),
        "arabic": sum(1 for c in text if 0x0600 <= ord(c) <= 0x06FF),
        "latin": sum(1 for c in text if "a" <= c.lower() <= "z"),
    }
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else "unknown"
