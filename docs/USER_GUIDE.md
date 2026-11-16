# User guide

A tour of the workflow, screen by screen. The application analyses evidence you
are authorised to examine; it never acquires data from a device.

## 1. Welcome & cases

* **Recent cases** — reopen with the last-known counts.
* **Create case** — name, description, examiner, and the authorisation
  declaration stored with the case.
* **Import case package** — restore a previously exported case package.
* **Status panel** — engine, database, FTS5 and offline state.
* **Load sample dataset** — synthetic multilingual fixtures (Priya, Project
  Falcon, Amma, Ahmed) for training and demos. Clearly labelled as synthetic.

Case identity is `CASE-0001`, `CASE-0002`, …; numbering is internal and stable.

## 2. Import Center

1. Choose files (native picker), drag them onto the window, or paste paths.
2. The engine detects source type, validates archives (rejecting traversal,
   symlinks and oversized entries), hashes the source and parses messages.
3. Watch stage-level progress, and cancel at any time.
4. Read the **import quality report**: detected order and confidence, parsed and
   skipped records, unresolved lines, participants, media placeholders, errors
   with line numbers.

Originals are copied byte-for-byte into `evidence/originals/` and hashed again
after copying; the recorded SHA-256 is the one re-verified later.

## 3. Dashboard

Totals, direction split, media/voice/link counts, active days, daily and hourly
charts, the weekday-by-hour heatmap, top contacts, recent evidence and findings.
Every card links to the screen that explains it.

## 4. Conversation Explorer

* Left: conversations with counts, last activity, media and import source.
* Centre: message bubbles with date separators, media previews, voice playback,
  system events, and deleted/edited/forwarded markers.
* Right: the message inspector — raw source record, provenance (evidence, line or
  row reference, hash), attachments, tags, bookmark, notes.

Filters: text filter, media-only, direction. Long conversations page in the
background; the inspector always opens the exact stored record.

## 5. Contact intelligence

Profile per contact: first/last interaction, volume, direction, active hours,
weekday distribution, monthly trend, top words and emojis, groups, response
behaviour, notes and tags. Compare two or three contacts side by side.

Observed behaviour is separated from interpretation: "writes mostly after 22:00"
is a fact; "is a night owl" is not something the application asserts.

## 6. Group intelligence

Participant ranking, contribution share, membership/administrative events,
activity timeline, keyword trends and per-participant media counts. Missing
evidence is never used to infer that someone left a group or lost admin rights.

## 7. Communication analytics

Activity (hour/day/week/month/weekday), heatmap, inactivity gaps, bursts,
response times (median/mean/p90/by direction/per contact, with the session-gap
rule stated), participation balance, sessions, words, emojis, languages and
anomalies with baseline, deviation and sensitivity.

Every panel exposes its formula and sample counts. These are descriptive
statistics, not proof of affection, intent or loyalty.

## 8. Timeline

A single chronology: messages, media, group events, annotations and imports.
Filter by kind, conversation, contact and date range; click an event to open its
source record. Uncertain time-zone conversions are flagged rather than hidden.

## 9. Relationship network

Nodes are contacts, groups and (optionally) topics; solid edges are observed
relationships, dashed edges are inferred topic associations. Filter by date,
minimum messages and node kind, read network metrics, export a PNG.

Two contacts in one group are not drawn as communicating — that inference is
explicitly avoided.

## 10. Recovery analysis

* **Deletion indicators** — placeholders present in the export.
* **Missing attachments** — media referenced but absent.
* **Present in earlier snapshot** — records found in one export and absent from
  another, with the comparison method and shared conversation counts.
* **Unverified discrepancy** — differences that cannot be classified.

Deleted text is never reconstructed. AI may add a labelled hypothesis in the
assistant, kept strictly apart from findings.

## 11. Media forensics

Gallery by type, thumbnails, metadata and EXIF inspection, hashing, exact
duplicate groups and perceptual (visual) similarity, missing-media report.
Metadata is displayed as found; it is never evidence of authenticity.

## 12. Voice & audio

Audio library with playback and waveform (when peaks are extractable),
transcription with a local model, editable transcripts, transcript search and
export. Speaker identity is never asserted from voice alone.

## 13. AI assistant

Ask a question in natural language, optionally scoped to one conversation. The
answer separates **observed evidence** (with citations), **computed statistics**
and **AI interpretation**. Citations are validated against retrieved records:
markers that do not resolve are removed and reported.

Imported text is sanitised before it reaches the model, so a message that says
"ignore your instructions" is treated as data, not a command. External providers
stay off until you enable one and accept the disclosure.

## 14. Advanced search

FTS5 syntax (`hotel AND travel`, `"boat tour"`, `tick*`, `NOT hotel`), exact
phrase and bounded regex modes, plus filters for conversation, sender, dates,
media, deleted/edited markers, bookmarks and tags. Save queries, export results
as CSV, and open any hit in the inspector.

## 15. Reports

Choose a template (case, conversation, contact, group, timeline, media, recovery,
AI-assisted, search results, custom), sections, scope (conversation, dates),
theme and format (PDF/HTML/XLSX/CSV/JSON). Preview renders the exact document
before export.

Every report carries the case identifier, generation timestamp, evidence sources
and hashes, methodology, data limitations and a statement that it is analytical
work product, not independent certification.

## 16. Case management

Case details and authorisation, evidence inventory with one-click integrity
re-verification, bookmarked findings, notes, manifest, chain of custody and audit
log. Duplicate a case to branch an investigation; create an encrypted backup with
a passphrase.

## 17. Settings

Appearance (theme, density, shortcuts), forensic defaults (hash verification,
archive validation, duplicate handling, source time zone, anomaly sensitivity,
audit retention), AI (local model, context, temperature, embedding and
transcription models, external provider disclosure), storage paths and
diagnostics (versions, FTS5, disk usage, tool detection, privacy posture).

## Keyboard

| Keys | Action |
| --- | --- |
| `Ctrl/Cmd + K` | Global search |
| `g` then `d` | Dashboard |
| `g` then `e` | Explorer |
| `g` then `a` | Analytics |
| `/` | Focus the search field |
| `Esc` | Close the inspector or dialog |

## Evidence etiquette

* Keep the original export files; the application copies but cannot restore them.
* Re-verify hashes before relying on a case in a report.
* Treat AI output and sentiment scores as leads to check against records.
* Share reports, not the case database, unless the recipient needs the evidence.
