"""Multilingual end-to-end checks for the evidence-grounded assistant.

The same loopback stub as the English test, but the imported evidence is
Malayalam, Arabic and Tamil. These tests prove that:

* citations still resolve to the correct stored record, and the snippet for a
  marker matches that marker's excerpt line (no off-by-one drift when the
  evidence block contains non-Latin text);
* script text is preserved codepoint-for-codepoint through import, retrieval,
  prompt construction and the returned answer - RTL text is not reversed,
  transliterated or re-ordered;
* the application strips the directionality marks WhatsApp injects and never
  introduces bidi controls of its own.
"""

from __future__ import annotations

import re
import unicodedata

import pytest

from wfs_engine import importer
from wfs_engine.ai import assistant, retrieval

MALAYALAM = "നാളെ യാത്ര തുടങ്ങാം. വണ്ടി രാവിലെ ഏഴ് മണിക്ക്."
ARABIC = "رحلة السفر غدا في الصباح. سآخذ السيارة."
TAMIL = "நாளை பயணம் தொடங்குகிறது. காலை ஏழு மணி."

# LRM/RLM/embedding/isolate overrides plus the Arabic letter mark. WhatsApp
# writes these into exports; the engine strips them at line level.
BIDI_CONTROLS = "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u061c"

QUERIES = {"ml": "യാത്ര", "ar": "السفر", "ta": "பயணம்"}
EXPECTED = {"ml": MALAYALAM, "ar": ARABIC, "ta": TAMIL}

CONVERSATION = (
    f"12/10/2024, 9:30 PM - Amma: {MALAYALAM}\n"
    f"12/10/2024, 9:32 PM - Ahmed: \u200f{ARABIC}\n"
    f"12/10/2024, 9:34 PM - Meena: \u200e{TAMIL}\n"
)


@pytest.fixture()
def multilingual_case(conn, case, tmp_path):
    source = tmp_path / "WhatsApp Chat with Family.txt"
    source.write_text(CONVERSATION, encoding="utf-8")
    importer.import_single_file(conn, case["id"], source,
                                {"source_timezone": "UTC", "date_order": "mdy"})
    return case


def _bodies(conn, case_id):
    return [row["body"] for row in conn.execute(
        "SELECT body FROM messages WHERE case_id=? ORDER BY sent_at_utc", (case_id,))]


def _prompt(state) -> tuple[str, str]:
    payload = state.requests[-1]
    system = next(m["content"] for m in payload["messages"] if m["role"] == "system")
    user = next(m["content"] for m in payload["messages"] if m["role"] == "user")
    return system, user


def _evidence_map(user: str) -> dict[str, str]:
    """Map each [M#] marker to the body text of its excerpt line."""
    mapping: dict[str, str] = {}
    for line in user.splitlines():
        match = re.match(r"\[M(\d+)\] ", line)
        if match:
            mapping[f"M{match.group(1)}"] = line.rsplit(" | ", 1)[-1]
    return mapping


@pytest.mark.parametrize("lang", ["ml", "ar", "ta"])
def test_citations_map_to_the_right_script_record(conn, multilingual_case, ai_stub, lang):
    state, _base = ai_stub

    result = assistant.ask(conn, multilingual_case["id"], QUERIES[lang])

    assert result["status"] == "ok", result.get("error")
    assert result["citations"], f"no citation validated for {lang}"
    # Guard against a false pass through the "most recent messages" fallback:
    # the excerpts must come from a real full-text match on the query.
    assert not result["observed"]["notes"], "retrieval fell back instead of matching"

    stored = {row["id"]: row["body"] for row in conn.execute(
        "SELECT id, body FROM messages WHERE case_id=?", (multilingual_case["id"],))}
    expected_nfc = unicodedata.normalize("NFC", EXPECTED[lang])
    assert expected_nfc in stored.values(), f"{lang} evidence was not stored intact"

    _system, user = _prompt(state)
    markers = _evidence_map(user)
    assert markers, "no evidence excerpts reached the model"

    for citation in result["citations"]:
        marker = (citation["marker"] or "").strip("[]")
        assert marker in markers, "citation marker is not in the prompt"
        assert citation["message_id"] in stored
        # The citation must be the excerpt the model was shown at that marker,
        # and that excerpt must be the stored record - not shifted by one.
        assert citation["snippet"] == retrieval.sanitize_evidence_text(markers[marker])[:280]
        assert citation["snippet"] == retrieval.sanitize_evidence_text(
            stored[citation["message_id"]])[:280]

    cited_text = " ".join(citation["snippet"] for citation in result["citations"])
    assert expected_nfc in cited_text, f"{lang} citation resolved to the wrong record"


def test_rtl_text_is_not_reversed_or_reordered(conn, multilingual_case, ai_stub):
    state, _base = ai_stub
    arabic_nfc = unicodedata.normalize("NFC", ARABIC)

    result = assistant.ask(conn, multilingual_case["id"], QUERIES["ar"])

    _system, user = _prompt(state)
    assert arabic_nfc in user, "the Arabic excerpt did not reach the model verbatim"
    # The stub echoes the excerpt, so the answer proves the round trip too.
    assert arabic_nfc in result["answer"]
    # Codepoint order is identical to the source: no reversal, no substitution.
    assert list(user[user.index(arabic_nfc):user.index(arabic_nfc) + len(arabic_nfc)]) == \
        list(arabic_nfc)
    # No bidi machinery introduced by the application.
    assert not any(control in user for control in BIDI_CONTROLS)
    assert not any(control in result["answer"] for control in BIDI_CONTROLS)
    assert not any(control in "".join(_bodies(conn, multilingual_case["id"]))
                   for control in BIDI_CONTROLS)


def test_whatsapp_directionality_marks_are_stripped_not_leaked(conn, multilingual_case):
    """The RLM/LRM in the export is removed once, at line level."""
    bodies = _bodies(conn, multilingual_case["id"])
    assert len(bodies) == 3
    assert bodies[0] == unicodedata.normalize("NFC", MALAYALAM)
    assert bodies[1] == unicodedata.normalize("NFC", ARABIC)
    assert bodies[2] == unicodedata.normalize("NFC", TAMIL)
    for body in bodies:
        assert not any(control in body for control in BIDI_CONTROLS)


def test_retrieval_finds_non_latin_question_terms(conn, multilingual_case):
    for lang, query in QUERIES.items():
        context = retrieval.retrieve(conn, multilingual_case["id"], query)
        assert context.query_terms, f"{lang} question produced no searchable terms"
        assert any(EXPECTED[lang] in message.body for message in context.messages), \
            f"{lang} evidence was not retrieved for its own question"
        # The fallback supplies "the most recent messages", which would make the
        # assertion above pass without the index understanding the script.
        assert not context.notes, f"{lang} query fell back to recent messages"
        assert all(message.reason == "full-text match" for message in context.messages), \
            f"{lang} excerpts did not come from full-text search"


@pytest.mark.parametrize("text", [MALAYALAM, ARABIC, TAMIL])
def test_sanitizer_preserves_clean_multilingual_text(text):
    assert retrieval.sanitize_evidence_text(text) == text
