"""AI investigation assistant: grounded answers with validated citations."""
from __future__ import annotations

import re
import time
from typing import Any

from .. import db
from ..analytics import metrics
from . import providers, retrieval

DISCLOSURE = (
    "AI answers are generated interpretations over the retrieved evidence. They are "
    "not forensic findings, and every citation is validated against stored records "
    "before it is shown.")


def ask(conn, case_id: str, question: str, *, conversation_id: str | None = None,
        provider_name: str | None = None, model: str | None = None,
        api_key: str | None = None, limit: int = 24) -> dict[str, Any]:
    if not question.strip():
        raise ValueError("question is required")
    settings = db.get_settings(conn)
    if provider_name:
        settings = {**settings, "ai_provider": provider_name}
    if model:
        settings = {**settings, "ai_model": model}
    started = time.perf_counter()
    ctx = retrieval.retrieve(conn, case_id, question, conversation_id=conversation_id,
                             limit=limit)
    query_id = db.new_id()
    citations = [{
        "id": db.new_id(),
        "message_id": m.message_id,
        "score": round(m.score, 4),
        "snippet": m.body[:280],
        "sender": m.sender,
        "conversation": m.conversation,
        "sent_at_utc": m.sent_at_utc,
        "reason": m.reason,
    } for m in ctx.messages]

    answer_text = ""
    status = "ok"
    error = None
    model_used = settings.get("ai_model", "")
    provider_used = settings.get("ai_provider", "ollama")

    if not settings.get("ai_enabled"):
        status = "disabled"
        answer_text = ("AI features are switched off. The retrieved evidence and the "
                       "computed statistics below are still available.")
    else:
        try:
            provider = providers.build_provider(settings, api_key=api_key)
            health = provider.health()
            if not health.get("ok"):
                raise providers.ProviderError(health.get("error") or "provider unavailable")
            messages = retrieval.build_messages(question, ctx)
            result = provider.chat(messages, model_used,
                                   temperature=float(settings.get("ai_temperature", 0.2)),
                                   context_length=int(settings.get("ai_context_length", 8192)))
            answer_text = result.text.strip()
            provider_used = result.provider
            model_used = result.model
        except Exception as exc:  # noqa: BLE001 - degrade, never lose the evidence
            status = "unavailable"
            error = str(exc)[:600]
            answer_text = (
                "No local language model answered this question. The evidence excerpts "
                "and computed statistics were retrieved successfully and are shown "
                "below; install a model (Settings → AI) to get a written answer.")

    validation = validate_citations(answer_text, citations)
    answer_text = _strip_invalid_markers(answer_text, validation["invalid_markers"])

    observed = {
        "stats": ctx.stats,
        "retrieved": len(ctx.messages),
        "truncated": ctx.truncated,
        "notes": ctx.notes,
        # The records that retrieval supplied. Exposed so the UI can show the
        # evidence even when no model wrote an answer; these are observed
        # records, not claims, and are deliberately not called citations.
        "records": [{
            "message_id": m.message_id,
            "snippet": m.body[:280],
            "sender": m.sender,
            "conversation": m.conversation,
            "sent_at_utc": m.sent_at_utc,
            "score": round(m.score, 4),
            "reason": m.reason,
        } for m in ctx.messages],
    }
    duration_ms = int((time.perf_counter() - started) * 1000)

    conn.execute(
        "INSERT INTO ai_queries(id, case_id, question, provider, model, answer,"
        " citations_json, observed_json, status, error, duration_ms, created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (query_id, case_id, question, provider_used, model_used, answer_text,
         db.json_dump(citations), db.json_dump(observed), status, error, duration_ms,
         db.now_utc()))
    # Persist only the citations that survived validation: the table is the
    # audit trail of what the answer actually cited, not everything retrieved.
    for cite in validation["citations"]:
        conn.execute(
            "INSERT INTO ai_evidence_citations(id, query_id, message_id, score, snippet)"
            " VALUES(?,?,?,?,?)",
            (cite["id"], query_id, cite["message_id"], cite["score"], cite["snippet"]))
    db.audit(conn, "ai.query", case_id, "user", {
        "query_id": query_id, "status": status, "provider": provider_used,
        "model": model_used, "citations": len(citations)})

    return {
        "id": query_id,
        "question": question,
        "answer": answer_text,
        "status": status,
        "error": error,
        "provider": provider_used,
        "model": model_used,
        "citations": validation["citations"],
        "invalid_citations": validation["invalid_markers"],
        "observed": observed,
        "duration_ms": duration_ms,
        "disclosure": DISCLOSURE,
        "sections": {
            # Without a written answer there are no claims to cite, so the
            # retrieved records are shown instead of an empty evidence panel.
            "observed_evidence": (validation["citations"]
                                  or observed["records"])[:8],
            "computed_statistics": ctx.stats,
            "ai_interpretation": answer_text if status == "ok" else "",
        },
    }


def validate_citations(answer: str, citations: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep only [M#] markers that resolve to a retrieved record."""
    by_marker = {f"M{idx}": c for idx, c in enumerate(citations, start=1)}
    used = set(re.findall(r"\[M(\d+)\]", answer or ""))
    valid = []
    invalid: list[str] = []
    for marker in sorted(used, key=lambda m: int(m)):
        key = f"M{marker}"
        if key in by_marker:
            cite = {**by_marker[key], "marker": f"[{key}]", "validated": True}
            if not any(c["message_id"] == cite["message_id"] for c in valid):
                valid.append(cite)
        else:
            invalid.append(f"[{key}]")
    return {
        "citations": valid or citations[:0],
        "invalid_markers": invalid,
        "unused_citations": [c for k, c in by_marker.items()
                             if k[1:] not in used],
    }


def _strip_invalid_markers(answer: str, invalid: list[str]) -> str:
    for marker in invalid:
        answer = answer.replace(marker, "[citation not found]")
    return answer


def history(conn, case_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.rows_to_list(conn.execute(
        "SELECT * FROM ai_queries WHERE case_id=? ORDER BY created_at DESC LIMIT ?",
        (case_id, limit)))
    for row in rows:
        row["citations"] = db.json_load(row.pop("citations_json"), [])
        row["observed"] = db.json_load(row.pop("observed_json"), {})
    return rows


def message_context(conn, case_id: str, message_id: str) -> dict[str, Any]:
    """Neighbouring messages for a citation deep-link."""
    row = conn.execute("SELECT * FROM messages WHERE id=? AND case_id=?",
                       (message_id, case_id)).fetchone()
    if not row:
        raise KeyError("message not found")
    message = dict(row)
    neighbours = db.rows_to_list(conn.execute(
        "SELECT id, sender_raw, sent_at_utc, body, message_type FROM messages"
        " WHERE conversation_id=? AND sent_at_utc BETWEEN datetime(?, '-6 hours')"
        " AND datetime(?, '+6 hours') ORDER BY sent_at_utc LIMIT 60",
        (message["conversation_id"], message["sent_at_utc"], message["sent_at_utc"])))
    return {"message": message, "neighbours": neighbours}


def statistics_summary(conn, case_id: str, conversation_id: str | None = None) -> dict:
    return metrics.overview(conn, case_id, conversation_id=conversation_id)
