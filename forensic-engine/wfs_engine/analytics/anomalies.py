"""Statistical anomaly detection over observable communication patterns.

Methods are deliberately simple and disclosed: rolling median baseline plus a
robust scaled deviation (MAD). No anomaly is described as suspicious conduct -
it is only a deviation from the case's own baseline.
"""
from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

from .. import db, textutil
from . import metrics


def _scaled_deviation(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0
    median = statistics.median(values)
    mad = statistics.median([abs(v - median) for v in values])
    return mad * 1.4826 if mad else 0.0


def detect(conn, case_id: str, *, sensitivity: float = 3.0,
           conversation_id: str | None = None) -> dict[str, Any]:
    where = "m.case_id=?"
    params: list[Any] = [case_id]
    if conversation_id:
        where += " AND m.conversation_id=?"
        params.append(conversation_id)
    rows = conn.execute(
        f"SELECT substr(m.sent_at_utc,1,10) AS d, COUNT(*) AS c, SUM(m.has_media) AS media,"
        f" SUM(m.char_count) AS chars FROM messages m WHERE {where} AND m.is_system=0"
        f" GROUP BY d ORDER BY d", params).fetchall()
    daily = [(r["d"], r["c"], r["media"] or 0, r["chars"] or 0) for r in rows]
    findings: list[dict[str, Any]] = []
    if len(daily) < 10:
        return {"findings": [], "method": "needs at least 10 active days",
                "sensitivity": sensitivity, "baseline_days": len(daily)}

    counts = [d[1] for d in daily]
    window = 14
    for idx, (day, count, media, chars) in enumerate(daily):
        if idx < window:
            continue
        baseline = counts[idx - window:idx]
        median = statistics.median(baseline)
        scale = _scaled_deviation(baseline) or max(1.0, median * 0.25)
        z = (count - median) / scale
        if abs(z) >= sensitivity:
            kind = "volume_spike" if z > 0 else "activity_drop"
            findings.append({
                "kind": kind,
                "date": day,
                "metric": "messages_per_day",
                "observed": count,
                "baseline_median": median,
                "deviation": round(z, 2),
                "samples": window,
                "explanation": (
                    f"{count} messages on {day} vs a {window}-day rolling median of "
                    f"{median:.0f} (robust z = {z:.1f})."),
            })
        mean_chars = chars / count if count else 0
        base_chars = [c[3] / c[1] for c in daily[idx - window:idx] if c[1]]
        if base_chars and count >= 3:
            mchars = statistics.median(base_chars)
            if mchars and (mean_chars / mchars) >= 2.2:
                findings.append({
                    "kind": "message_length_change",
                    "date": day,
                    "metric": "mean_chars_per_message",
                    "observed": round(mean_chars, 1),
                    "baseline_median": round(mchars, 1),
                    "deviation": round(mean_chars / mchars, 2),
                    "samples": window,
                    "explanation": (f"Mean message length {mean_chars:.0f} chars vs "
                                    f"{mchars:.0f} baseline on {day}."),
                })
        base_media = [c[2] for c in daily[idx - window:idx]]
        if base_media and statistics.median(base_media) == 0 and media >= 5:
            findings.append({
                "kind": "media_spike",
                "date": day,
                "metric": "media_messages_per_day",
                "observed": media,
                "baseline_median": 0,
                "deviation": float(media),
                "samples": window,
                "explanation": f"{media} media messages on a day where the baseline is 0.",
            })

    findings.extend(_activity_hour_anomalies(conn, case_id, sensitivity, conversation_id))
    findings.extend(_topic_shift(conn, case_id, conversation_id))
    findings.sort(key=lambda f: (f["date"], -abs(f.get("deviation") or 0)), reverse=True)
    return {
        "findings": findings[:60],
        "sensitivity": sensitivity,
        "baseline_days": len(daily),
        "method": ("Rolling 14-day median baseline with MAD-scaled deviation "
                   "(1.4826 x MAD). Flagged when |z| >= sensitivity."),
        "disclaimer": ("A flagged deviation is a statistical observation about message "
                       "metadata, not evidence of misconduct."),
    }


def _activity_hour_anomalies(conn, case_id: str, sensitivity: float,
                             conversation_id: str | None) -> list[dict[str, Any]]:
    where = "case_id=?"
    params: list[Any] = [case_id]
    if conversation_id:
        where += " AND conversation_id=?"
        params.append(conversation_id)
    rows = conn.execute(
        f"SELECT CAST(substr(sent_at_utc,12,2) AS INTEGER) AS h, COUNT(*) AS c"
        f" FROM messages WHERE {where} GROUP BY h", params).fetchall()
    if not rows:
        return []
    counts = {r["h"]: r["c"] for r in rows}
    total = sum(counts.values())
    expected = total / 24
    flagged = []
    for hour, count in counts.items():
        if expected > 0 and count / expected >= sensitivity:
            flagged.append({
                "kind": "unusual_hour",
                "date": "",
                "metric": "messages_at_hour (UTC)",
                "observed": count,
                "baseline_median": round(expected, 1),
                "deviation": round(count / expected, 2),
                "samples": total,
                "explanation": (f"Hour {hour:02d}:00 UTC holds {count} messages, "
                                f"{count / expected:.1f}x an even spread across 24 hours."),
            })
    return flagged


def _topic_shift(conn, case_id: str, conversation_id: str | None) -> list[dict[str, Any]]:
    where = "m.case_id=?"
    params: list[Any] = [case_id]
    if conversation_id:
        where += " AND m.conversation_id=?"
        params.append(conversation_id)
    months: dict[str, list[str]] = {}
    for row in conn.execute(
            f"SELECT substr(m.sent_at_utc,1,7) AS b, m.body FROM messages m"
            f" WHERE {where} AND m.is_system=0 AND m.body<>''", params):
        months.setdefault(row["b"], []).append(row["body"])
    ordered = sorted(months.items())
    if len(ordered) < 3:
        return []
    findings = []
    for idx in range(1, len(ordered)):
        prev_month, prev_bodies = ordered[idx - 1]
        month, bodies = ordered[idx]
        prev_terms = {w for w, _ in Counter(
            textutil.tokenize(" ".join(prev_bodies))).most_common(25)}
        terms = Counter(textutil.tokenize(" ".join(bodies))).most_common(25)
        emerging = [w for w, _ in terms if w not in prev_terms][:6]
        if len(emerging) >= 4:
            findings.append({
                "kind": "topic_shift",
                "date": f"{month}-01",
                "metric": "new_top_terms_vs_previous_month",
                "observed": len(emerging),
                "baseline_median": len(prev_terms),
                "deviation": float(len(emerging)),
                "samples": len(bodies),
                "explanation": (f"{len(emerging)} new high-frequency terms in {month} "
                                f"compared with {prev_month}: {', '.join(emerging)}"),
            })
    return findings
