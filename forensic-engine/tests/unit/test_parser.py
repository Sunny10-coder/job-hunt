from pathlib import Path

import pytest

from wfs_engine.parsers.whatsapp_txt import WhatsAppTxtParser, decode_text

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def parse(name: str, **kwargs):
    parser = WhatsAppTxtParser(**kwargs)
    messages = list(parser.parse_file(FIXTURES / name, source_label=name))
    return parser, messages


def test_android_twelve_hour_export():
    # 10 timestamped lines, one of which is a continuation -> 9 records.
    parser, messages = parse("android_12h.txt")
    assert len(messages) == 9
    assert messages[0].sender_raw == "Alice"
    assert messages[0].sent_at_utc == "2023-12-31T23:59:00Z"
    assert parser.stats.date_order == "mdy"
    assert parser.stats.multiline_messages == 1


def test_multiline_message_body_is_preserved():
    _, messages = parse("android_12h.txt")
    target = next(m for m in messages if m.sender_raw == "Bob" and "second line" in m.body)
    assert "continues the message on a new line" in target.body
    assert "\n" in target.body


def test_media_placeholders_are_flagged():
    _, messages = parse("android_12h.txt")
    media = [m for m in messages if m.has_media]
    assert len(media) == 2
    assert {m.message_type for m in media} == {"media", "image"}
    assert media[0].media_ref is not None


def test_deleted_and_edited_markers():
    _, messages = parse("android_12h.txt")
    deleted = [m for m in messages if m.is_deleted]
    edited = [m for m in messages if m.is_edited]
    assert len(deleted) == 1
    assert len(edited) == 1
    # The marker itself is not left inside the stored body.
    assert "<this message was edited>" not in edited[0].body.lower()
    assert edited[0].body.strip().lower() == "edited text"


def test_links_and_contact_references_extracted():
    _, messages = parse("android_12h.txt")
    urls = [u for m in messages for u in m.urls]
    emails = [e for m in messages for e in m.emails]
    phones = [p for m in messages for p in m.phones]
    assert "https://example.com/report" in urls
    assert "bob@example.com" in emails
    assert any("555" in p for p in phones)


def test_day_first_export_uses_proven_order():
    parser, messages = parse("android_24h_dmy.txt")
    assert parser.stats.date_order == "dmy"
    assert messages[0].sent_at_local.startswith("2023-12-31T23:59")


def test_ios_bracket_timestamps_and_attachments():
    parser, messages = parse("ios_bracket.txt")
    assert messages[0].sent_at_local == "2023-12-28T21:12:05"
    attached = [m for m in messages if m.media_ref == "IMG-20231229-WA0001.jpg"]
    assert len(attached) == 1
    assert attached[0].has_media is True


def test_iso_and_multilingual_scripts_roundtrip():
    parser, messages = parse("iso_multilingual.txt")
    bodies = [m.body for m in messages]
    assert any("മലയാളം" in b for b in bodies)
    assert any("हिंदी" in b for b in bodies)
    assert any("தமிழ்" in b for b in bodies)
    assert any("العربية" in b for b in bodies)
    assert parser.stats.language in {"malayalam", "hindi", "tamil", "arabic", "latin"}


def test_system_events_and_unusual_sender_names():
    parser, messages = parse("unusual_names.txt")
    system = [m for m in messages if m.is_system]
    assert system, "system notices must be captured"
    assert parser.stats.is_group is True
    senders = {m.sender_raw for m in messages if not m.is_system}
    assert senders == {"Alice", "Bob (work)", "Carol"}
    bodies = " ".join(m.body for m in messages)
    # Unicode sender names inside message bodies survive intact.
    assert "O'Brien-Smith, 李雷, محمد" in bodies
    assert sum(1 for m in messages if m.is_system) >= 3


def test_empty_body_message_does_not_crash():
    _, messages = parse("unusual_names.txt")
    assert all(isinstance(m.body, str) for m in messages)


def test_empty_file_produces_no_messages():
    parser = WhatsAppTxtParser()
    assert list(parser.parse_lines(iter([]))) == []


def test_unresolved_lines_are_counted_not_dropped():
    lines = ["random text before any timestamp", "01/05/24, 10:00 - A: hello"]
    parser = WhatsAppTxtParser(date_order="mdy")
    messages = list(parser.parse_lines(iter(lines)))
    assert len(messages) == 1
    assert parser.stats.unresolved_lines == 1


def test_utf16_export_is_decoded():
    raw = "01/05/24, 10:00 - Alice: hello\n".encode("utf-16")
    text, encoding = decode_text(raw)
    assert "Alice" in text
    assert encoding.startswith("utf-16")


def test_duplicate_records_share_a_fingerprint():
    parser = WhatsAppTxtParser(date_order="mdy")
    text = "01/05/24, 10:00 - Alice: same\n01/05/24, 10:00 - Alice: same\n"
    messages = list(parser.parse_lines(iter(text.splitlines())))
    assert messages[0].content_hash == messages[1].content_hash
