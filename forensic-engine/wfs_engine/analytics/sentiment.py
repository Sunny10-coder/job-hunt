"""Lexicon-based sentiment and emotional-language indicators.

These are *linguistic estimates* over a fixed word list, not verified internal
emotional states. The module is explicitly optional and disabled when the user
turns interpretive analysis off.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .. import textutil

POSITIVE = {
    "happy", "great", "good", "love", "thanks", "thank", "nice", "awesome", "perfect",
    "excellent", "glad", "beautiful", "amazing", "wonderful", "congrats", "congratulations",
    "best", "fun", "enjoy", "excited", "proud", "smile", "laugh", "welcome", "please",
    "സന്തോഷം", "നന്ദി", "കൊള്ളാം", "അടിപൊളി",
    "खुश", "धन्यवाद", "अच्छा", "बहुत", "शुभ",
    "سعيد", "شكرا", "جيد",
}
NEGATIVE = {
    "sad", "angry", "hate", "sorry", "bad", "terrible", "awful", "upset", "worried",
    "problem", "issue", "fail", "failed", "wrong", "hurt", "pain", "cry", "afraid",
    "annoying", "frustrated", "disappointed", "worst", "useless", "broken", "late",
    "ദുഃഖം", "സങ്കടം", "ദേഷ്യം", "പ്രശ്നം", "ക്ഷമിക്കണം",
    "दुख", "गुस्सा", "समस्या", "माफ",
    "حزين", "غاضب", "مشكلة", "آسف",
}
EMOTIONS = {
    "happiness": {"happy", "glad", "joy", "smile", "excited", "cheerful", "സന്തോഷം"},
    "sadness": {"sad", "upset", "cry", "down", "lonely", "miss", "ദുഃഖം", "सadне"},
    "anger": {"angry", "furious", "mad", "hate", "annoyed", "गुस्सा", "ദേഷ്യം"},
    "frustration": {"frustrated", "stuck", "again", "why", "tired", "problem"},
    "concern": {"worried", "afraid", "concerned", "careful", "risk", "safe"},
    "excitement": {"excited", "amazing", "wow", "cant", "finally", "yay"},
    "affection": {"love", "miss", "dear", "sweet", "hug", "kiss", "❤", "പ്രിയ"},
    "uncertainty": {"maybe", "perhaps", "unsure", "confused", "可能", "ഒരുപക്ഷേ"},
}
INTENSIFIERS = {"very", "really", "so", "extremely", "totally", "ഒരുപാട്", "बहुत"}


def analyze(conn, case_id: str, *, conversation_id: str | None = None,
            date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    clauses = ["m.case_id=?", "m.is_system=0", "m.body<>''"]
    params: list[Any] = [case_id]
    if conversation_id:
        clauses.append("m.conversation_id=?")
        params.append(conversation_id)
    if date_from:
        clauses.append("m.sent_at_utc>=?")
        params.append(date_from)
    if date_to:
        clauses.append("m.sent_at_utc<=?")
        params.append(date_to if len(date_to) > 10 else date_to + "T23:59:59Z")
    where = " AND ".join(clauses)

    totals = Counter()
    daily: dict[str, Counter] = defaultdict(Counter)
    per_conversation: dict[str, Counter] = defaultdict(Counter)
    emotions = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    scanned = 0

    for row in conn.execute(
            f"SELECT m.body, substr(m.sent_at_utc,1,10) AS d, c.title FROM messages m"
            f" JOIN conversations c ON c.id=m.conversation_id WHERE {where}", params):
        scanned += 1
        tokens = [t for t in textutil.tokenize(row["body"])]
        pos = sum(1 for t in tokens if t in POSITIVE)
        neg = sum(1 for t in tokens if t in NEGATIVE)
        label = "positive" if pos > neg else "negative" if neg > pos else "neutral"
        totals[label] += 1
        daily[row["d"]][label] += 1
        per_conversation[row["title"]][label] += 1
        for emotion, words in EMOTIONS.items():
            if any(t in words for t in tokens):
                emotions[emotion] += 1
                if len(samples[emotion]) < 3:
                    samples[emotion].append(row["body"][:180])

    series = []
    for day in sorted(daily):
        bucket = daily[day]
        total = sum(bucket.values()) or 1
        series.append({
            "date": day,
            "positive": bucket["positive"],
            "negative": bucket["negative"],
            "neutral": bucket["neutral"],
            "score": round((bucket["positive"] - bucket["negative"]) / total, 3),
        })

    return {
        "scanned_messages": scanned,
        "counts": {k: totals.get(k, 0) for k in ("positive", "negative", "neutral")},
        "share": {k: round(totals.get(k, 0) / scanned * 100, 2) if scanned else 0
                  for k in ("positive", "negative", "neutral")},
        "series": series,
        "emotions": [{"emotion": e, "count": c, "examples": samples[e]}
                     for e, c in emotions.most_common()],
        "by_conversation": [
            {"conversation": name, "positive": c["positive"], "negative": c["negative"],
             "neutral": c["neutral"]}
            for name, c in sorted(per_conversation.items(),
                                  key=lambda kv: sum(kv[1].values()), reverse=True)[:20]
        ],
        "method": ("Fixed multilingual word-list matching on normalised message text; "
                   "a message is labelled by majority polarity of matched terms."),
        "disclaimer": ("Linguistic estimate only. This is not a measurement of any "
                       "person's emotional state, intent or mental health."),
    }
