"""Relationship network construction for the graph workspace.

Solid edges are *observed* relationships (a direct 1:1 conversation, or the
presence of a participant's messages inside a group). Dashed edges are
*inferred* associations (topic co-occurrence) and are labelled as such.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .. import textutil


def build(conn, case_id: str, *, date_from: str | None = None,
          date_to: str | None = None, include_topics: bool = True,
          min_messages: int = 1) -> dict[str, Any]:
    clauses = ["m.case_id=?", "m.sender_id IS NOT NULL"]
    params: list[Any] = [case_id]
    if date_from:
        clauses.append("m.sent_at_utc>=?")
        params.append(date_from)
    if date_to:
        clauses.append("m.sent_at_utc<=?")
        params.append(date_to if len(date_to) > 10 else date_to + "T23:59:59Z")
    where = " AND ".join(clauses)

    contacts = {r["id"]: dict(r) for r in conn.execute(
        "SELECT id, display_name, is_self FROM contacts WHERE case_id=?", (case_id,))}
    conversations = {r["id"]: dict(r) for r in conn.execute(
        "SELECT id, title, kind FROM conversations WHERE case_id=?", (case_id,))}

    # Observed message counts per (conversation, sender).
    counts = conn.execute(
        f"SELECT m.conversation_id, m.sender_id, COUNT(*) AS c FROM messages m"
        f" WHERE {where} GROUP BY m.conversation_id, m.sender_id", params).fetchall()
    per_conv: dict[str, dict[str, int]] = defaultdict(dict)
    totals: Counter[str] = Counter()
    for row in counts:
        per_conv[row["conversation_id"]][row["sender_id"]] = row["c"]
        totals[row["sender_id"]] += row["c"]

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()

    for cid, total in totals.items():
        if total < min_messages or cid not in contacts:
            continue
        contact = contacts[cid]
        nodes[f"contact:{cid}"] = {
            "id": f"contact:{cid}",
            "label": contact["display_name"],
            "kind": "self" if contact["is_self"] else "contact",
            "weight": total,
            "contact_id": cid,
        }

    for conv_id, members in per_conv.items():
        conv = conversations.get(conv_id)
        if not conv or conv["kind"] != "group":
            continue
        node_id = f"group:{conv_id}"
        if node_id not in nodes:
            nodes[node_id] = {
                "id": node_id, "label": conv["title"], "kind": "group",
                "weight": sum(members.values()), "conversation_id": conv_id,
            }
        for cid, count in members.items():
            if f"contact:{cid}" not in nodes:
                continue
            key = (f"contact:{cid}", node_id, "membership")
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append({
                "id": f"e-{len(edges)}",
                "source": f"contact:{cid}",
                "target": node_id,
                "kind": "membership",
                "inferred": False,
                "weight": count,
                "label": f"{count} messages in group",
            })

    # Direct 1:1 communication: every participant pair of a chat conversation.
    for conv_id, members in per_conv.items():
        conv = conversations.get(conv_id)
        if not conv or conv["kind"] != "chat":
            continue
        ids = [cid for cid in members if f"contact:{cid}" in nodes]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = sorted([ids[i], ids[j]])
                key = (f"contact:{a}", f"contact:{b}", "direct")
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append({
                    "id": f"e-{len(edges)}",
                    "source": f"contact:{a}",
                    "target": f"contact:{b}",
                    "kind": "direct",
                    "inferred": False,
                    "weight": members[a] + members[b],
                    "label": f"1:1 conversation '{conv['title']}'",
                    "conversation_id": conv_id,
                })

    if include_topics:
        topic_nodes, topic_edges = _topic_associations(conn, case_id, where, params, nodes)
        nodes.update(topic_nodes)
        edges.extend(topic_edges)

    values = list(nodes.values())
    metrics = {
        "nodes": len(values),
        "edges": len(edges),
        "contacts": sum(1 for n in values if n["kind"] in ("contact", "self")),
        "groups": sum(1 for n in values if n["kind"] == "group"),
        "topics": sum(1 for n in values if n["kind"] == "topic"),
        "density": round(len(edges) / max(1, len(values) * (len(values) - 1)), 4),
        "method": ("Nodes are contacts and groups observed in the evidence. Solid edges "
                   "are observed (participant of a group, participant of a 1:1 chat). "
                   "Dashed edges are inferred topic associations only."),
    }
    return {"nodes": values, "edges": edges, "metrics": metrics}


def _topic_associations(conn, case_id: str, where: str, params: list[Any],
                        nodes: dict[str, dict[str, Any]]) -> tuple[dict, list]:
    topic_counts: Counter[str] = Counter()
    contact_terms: dict[str, Counter[str]] = defaultdict(Counter)
    for row in conn.execute(
            f"SELECT m.sender_id, m.body FROM messages m WHERE {where}"
            f" AND m.is_system=0 AND m.body<>'' LIMIT 40000", params):
        terms = textutil.tokenize(row["body"] or "")
        topic_counts.update(terms)
        contact_terms[row["sender_id"]].update(terms)
    top_topics = [t for t, c in topic_counts.most_common(10) if c >= 3]
    topic_nodes = {
        f"topic:{t}": {"id": f"topic:{t}", "label": t, "kind": "topic",
                       "weight": topic_counts[t]}
        for t in top_topics
    }
    edges = []
    for cid, counter in contact_terms.items():
        node_id = f"contact:{cid}"
        if node_id not in nodes:
            continue
        for topic in top_topics:
            count = counter.get(topic, 0)
            if count >= 3:
                edges.append({
                    "id": f"e-t-{len(edges)}",
                    "source": node_id,
                    "target": f"topic:{topic}",
                    "kind": "topic",
                    "inferred": True,
                    "weight": count,
                    "label": f"{count} occurrences of '{topic}'",
                })
    return topic_nodes, edges
