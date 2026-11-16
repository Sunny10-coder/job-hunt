# Supported evidence formats

Only evidence the examiner owns or is explicitly authorised to examine may be
imported. Nothing in this list involves decryption, key extraction or device
acquisition.

## WhatsApp text exports

| Shape | Example | Support |
| --- | --- | --- |
| Android 12-hour, dash separator | `12/31/23, 11:59 PM - Alice: hello` | Yes |
| Android 24-hour | `31/12/2023, 23:59 - Alice: hello` | Yes |
| iOS bracketed | `[12/31/23, 11:59:59 PM] Alice: hello` | Yes |
| ISO-ish dates | `2023-12-31, 23:59 - Alice: hello` | Yes |
| Dot separators | `31.12.2023 23:59 - Alice: hello` | Yes |
| Multiline bodies | continuation lines without a timestamp | Yes |
| UTF-8, UTF-16 LE/BE, UTF-32 with BOM, cp1252 fallback | — | Yes, encoding recorded per import |
| Arabic, Malayalam, Tamil, Hindi, English text and emoji | — | Stored verbatim; RTL/bidi text is rendered with `dir="auto"` |
| Group system notices (add/remove/subject/icon changes) | — | Parsed as system events, never as participant messages |
| `<Media omitted>`, `image omitted`, `GIF omitted`, `sticker omitted` | — | Recorded as a media placeholder; the attachment is **not** guessed |
| Deleted-message and edit notices | `This message was deleted`, `You deleted this message` | Recorded as indicators; content is never reconstructed |
| Forwarded markers | `Forwarded` | Recorded only when the export states it |
| Contact cards, documents, audio, video | `<attached: …>` and `… (file attached)` | Referenced; media linked only when the file is present |
| ZIP exports with media | `WhatsApp Chat with X.zip` | Text parsed, media extracted and linked by exact name match |

Date order is detected per file and reported with a confidence value. An
ambiguous order is never treated as proven: the raw timestamp is preserved and
the ambiguity is counted in the import quality report.

## Accessible SQLite databases

Unencrypted databases that can already be opened without any key:

| Requirement | Detail |
| --- | --- |
| Message table | `message`, `messages` or `message_view` |
| Timestamps | `timestamp` in UTC epoch seconds or milliseconds |
| Message text | `data` or `text_data` |
| Direction | `from_me` and/or `key_from_me` |
| Conversation identity | `key_remote_jid`, or `chat_row_id` with a `chat`/`chat_list`/`jid` table |
| Group detection | JID ending in `@g.us`; senders from `remote_resource` |
| Optional | `media_wa_type` (1 image, 2 audio, 3 video, 9 document, 13 GIF, 20 sticker), `chat.subject` for titles |

Each JID becomes its own conversation. Databases missing a conversation
identifier or timestamps are rejected with the reason, rather than imported under
a single invented conversation named after the file.

Confidence for database rows is 0.9 for text and 0.85 for media rows: readable
bytes do not prove the semantics of every column, so a perfect score is never
assigned.

**Not supported:** encrypted `msgstore.db.crypt12/14/15`, key extraction, iOS
backup containers, cloud account extraction.

## Other evidence

| Input | Handling |
| --- | --- |
| Standalone image/audio/video/document | Stored as evidence, hashed, listed as unlinked media |
| Previously exported case package | Restored through the verified backup path |
| Unknown or unsupported file | Rejected with a recorded import error; the file is still hashed and preserved |

## Import quality report

Every import records: detected records, parsed records, unresolved lines,
ambiguous timestamps, unsupported constructs, missing attachments, duplicates,
encoding, source hash, parser version and warnings. Unresolved content remains
readable in the import error list; nothing is silently discarded.
