"""Timestamp parsing with explicit date-order detection and timezone flags.

WhatsApp exports contain local wall-clock timestamps with no timezone. We keep
the original string verbatim, derive a local naive value, then apply the
configured source timezone to obtain UTC. Ambiguous (DST-fold or DST-gap)
values are flagged rather than silently resolved.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

try:  # pragma: no cover - platform dependent
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

DATE_TOKEN_RE = re.compile(r"^(\d{1,4})[./-](\d{1,2})[./-](\d{1,4})$")
TIME_TOKEN_RE = re.compile(
    r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(?P<ampm>[AaPp]\.?[Mm]\.?)?$"
)
AMPM_RE = re.compile(r"[AaPp]\.?[Mm]\.?")


@dataclass
class OrderDetection:
    order: str            # 'mdy' | 'dmy' | 'ymd'
    confidence: float
    decisive: bool
    day_first_votes: int = 0
    month_first_votes: int = 0
    sample_size: int = 0


def split_date(value: str) -> tuple[int, int, int] | None:
    m = DATE_TOKEN_RE.match(value.strip())
    if not m:
        return None
    a, b, c = (int(g) for g in m.groups())
    return a, b, c


def detect_date_order(date_tokens: Iterable[str], fallback: str = "mdy") -> OrderDetection:
    """Decide between day-first and month-first layouts from observed values.

    A component > 12 proves its position. When nothing is decisive the fallback
    (user preference or locale default) is used with reduced confidence, and the
    result is reported in the import quality report.
    """
    day_votes = month_votes = 0
    seen = 0
    year_first = 0
    for token in date_tokens:
        parts = split_date(token)
        if parts is None:
            continue
        seen += 1
        first, second, _third = parts
        head = re.split(r"[./-]", token.strip())[0]
        if len(head) == 4:
            year_first += 1
            continue
        if first > 12:
            day_votes += 1
        elif second > 12:
            month_votes += 1
    if seen == 0:
        return OrderDetection(fallback, 0.3, False, 0, 0, 0)
    if year_first == seen:
        return OrderDetection("ymd", 1.0, True, day_votes, month_votes, seen)
    if day_votes and not month_votes:
        return OrderDetection("dmy", 1.0, True, day_votes, month_votes, seen)
    if month_votes and not day_votes:
        return OrderDetection("mdy", 1.0, True, day_votes, month_votes, seen)
    if day_votes and month_votes:
        # Mixed evidence: pick the majority but mark low confidence.
        order = "dmy" if day_votes > month_votes else "mdy"
        return OrderDetection(order, 0.5, False, day_votes, month_votes, seen)
    return OrderDetection(fallback, 0.6, False, day_votes, month_votes, seen)


@dataclass
class ParsedTimestamp:
    naive_local: datetime
    utc: datetime
    offset_minutes: int
    ambiguous: bool
    ok: bool


def resolve_timezone(name: str | None):
    if not name:
        return timezone.utc
    if ZoneInfo is None:  # pragma: no cover
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - invalid tz name falls back to UTC
        return timezone.utc


def parse_timestamp(date_value: str, time_value: str, order: str,
                    tz_name: str | None = "UTC") -> ParsedTimestamp | None:
    parts = split_date(date_value)
    if parts is None:
        return None
    a, b, c = parts
    if len(str(a)) == 4:
        year, month, day = a, b, c
    elif len(str(c)) == 4:
        year = c
        if order == "dmy":
            day, month = a, b
        else:
            month, day = a, b
    else:  # two digit year
        year = 2000 + c if c < 70 else 1900 + c
        if order == "dmy":
            day, month = a, b
        else:
            month, day = a, b
    tm = TIME_TOKEN_RE.match(time_value.strip())
    if not tm:
        return None
    hour, minute = int(tm.group(1)), int(tm.group(2))
    second = int(tm.group(3) or 0)
    ampm = tm.group("ampm")
    if ampm:
        marker = AMPM_RE.search(ampm).group(0).replace(".", "").lower()
        if hour > 12 or hour == 0 and marker == "am":
            hour = hour % 12
        if marker == "pm" and hour < 12:
            hour += 12
        if marker == "am" and hour == 12:
            hour = 0
    if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23
            and 0 <= minute <= 59 and 0 <= second <= 59):
        return None
    try:
        naive = datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None
    tz = resolve_timezone(tz_name)
    ambiguous = False
    try:
        aware = naive.replace(tzinfo=tz)
        offset = aware.utcoffset() or timedelta(0)
        fold_a = naive.replace(tzinfo=tz, fold=0).utcoffset()
        fold_b = naive.replace(tzinfo=tz, fold=1).utcoffset()
        ambiguous = fold_a != fold_b
        utc = naive - offset
        # Detect non-existent local times (spring-forward gap).
        roundtrip = (naive - offset).replace(tzinfo=timezone.utc).astimezone(tz)
        if roundtrip.replace(tzinfo=None) != naive:
            ambiguous = True
    except Exception:  # noqa: BLE001 - keep UTC math even for exotic zones
        offset = timedelta(0)
        utc = naive
    return ParsedTimestamp(
        naive_local=naive,
        utc=utc,
        offset_minutes=int(offset.total_seconds() // 60),
        ambiguous=ambiguous,
        ok=True,
    )


def to_utc_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def to_local_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def parse_utc_iso(value: str) -> datetime:
    v = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
