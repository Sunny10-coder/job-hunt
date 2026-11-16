-- WhatsApp Forensic Studio AI :: schema v1
-- All timestamps stored as ISO-8601 UTC ("Z") or ISO local strings where documented.
-- Evidence is never mutated: parsed rows always cite evidence_id + source_ref.

CREATE TABLE IF NOT EXISTS cases (
  id                      TEXT PRIMARY KEY,
  case_number             INTEGER UNIQUE,
  name                    TEXT NOT NULL,
  description             TEXT NOT NULL DEFAULT '',
  examiner                TEXT NOT NULL DEFAULT '',
  status                  TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  authorization_statement TEXT NOT NULL DEFAULT '',
  dir_path                TEXT NOT NULL,
  created_at              TEXT NOT NULL,
  updated_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_settings (
  case_id   TEXT PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
  json      TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_sources (
  id                TEXT PRIMARY KEY,
  case_id           TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  original_name     TEXT NOT NULL,
  stored_path       TEXT NOT NULL,
  source_type       TEXT NOT NULL,
  size_bytes        INTEGER NOT NULL DEFAULT 0,
  sha256            TEXT NOT NULL,
  imported_at       TEXT NOT NULL,
  message_count     INTEGER NOT NULL DEFAULT 0,
  language          TEXT,
  date_order        TEXT,
  date_order_confidence REAL,
  parse_confidence  REAL,
  status            TEXT NOT NULL DEFAULT 'imported',
  notes             TEXT NOT NULL DEFAULT '',
  extra_json        TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_evidence_case ON evidence_sources(case_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_hash ON evidence_sources(case_id, sha256);

CREATE TABLE IF NOT EXISTS evidence_hashes (
  id          TEXT PRIMARY KEY,
  evidence_id TEXT NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
  algo        TEXT NOT NULL DEFAULT 'sha256',
  hash        TEXT NOT NULL,
  verified_at TEXT,
  ok          INTEGER,
  note        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_evhash_ev ON evidence_hashes(evidence_id);

CREATE TABLE IF NOT EXISTS import_jobs (
  id           TEXT PRIMARY KEY,
  case_id      TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  status       TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed','cancelled')),
  stage        TEXT NOT NULL DEFAULT 'queued',
  progress     REAL NOT NULL DEFAULT 0,
  started_at   TEXT,
  finished_at  TEXT,
  options_json TEXT NOT NULL DEFAULT '{}',
  log_json     TEXT NOT NULL DEFAULT '[]',
  error        TEXT,
  created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_case ON import_jobs(case_id);

CREATE TABLE IF NOT EXISTS import_errors (
  id          TEXT PRIMARY KEY,
  job_id      TEXT REFERENCES import_jobs(id) ON DELETE CASCADE,
  case_id     TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  evidence_id TEXT,
  severity    TEXT NOT NULL DEFAULT 'warning',
  code        TEXT NOT NULL,
  message     TEXT NOT NULL,
  line_no     INTEGER,
  raw         TEXT
);
CREATE INDEX IF NOT EXISTS idx_importerr_job ON import_errors(job_id);

CREATE TABLE IF NOT EXISTS contacts (
  id           TEXT PRIMARY KEY,
  case_id      TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL,
  phone        TEXT,
  is_self      INTEGER NOT NULL DEFAULT 0,
  first_seen   TEXT,
  last_seen    TEXT,
  notes        TEXT NOT NULL DEFAULT '',
  UNIQUE (case_id, display_name)
);

CREATE TABLE IF NOT EXISTS contact_aliases (
  id         TEXT PRIMARY KEY,
  contact_id TEXT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  alias      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alias_contact ON contact_aliases(contact_id);

CREATE TABLE IF NOT EXISTS conversations (
  id              TEXT PRIMARY KEY,
  case_id         TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  title           TEXT NOT NULL,
  kind            TEXT NOT NULL DEFAULT 'chat' CHECK (kind IN ('chat','group')),
  chat_identifier TEXT,
  evidence_id     TEXT,
  message_count   INTEGER NOT NULL DEFAULT 0,
  media_count     INTEGER NOT NULL DEFAULT 0,
  first_at        TEXT,
  last_at         TEXT,
  UNIQUE (case_id, title, kind)
);
CREATE INDEX IF NOT EXISTS idx_conv_case ON conversations(case_id);

CREATE TABLE IF NOT EXISTS conversation_participants (
  id              TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  contact_id      TEXT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  message_count   INTEGER NOT NULL DEFAULT 0,
  first_at        TEXT,
  last_at         TEXT,
  role_note       TEXT NOT NULL DEFAULT '',
  UNIQUE (conversation_id, contact_id)
);

CREATE TABLE IF NOT EXISTS messages (
  id                 TEXT PRIMARY KEY,
  case_id            TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  evidence_id        TEXT NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
  conversation_id    TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  sender_id          TEXT REFERENCES contacts(id) ON DELETE SET NULL,
  sender_raw         TEXT NOT NULL DEFAULT '',
  original_timestamp TEXT NOT NULL,
  sent_at_local      TEXT NOT NULL,
  sent_at_utc        TEXT NOT NULL,
  tz_offset_min      INTEGER NOT NULL DEFAULT 0,
  tz_ambiguous       INTEGER NOT NULL DEFAULT 0,
  raw_text           TEXT NOT NULL DEFAULT '',
  body               TEXT NOT NULL DEFAULT '',
  message_type       TEXT NOT NULL DEFAULT 'text',
  is_system          INTEGER NOT NULL DEFAULT 0,
  is_deleted         INTEGER NOT NULL DEFAULT 0,
  is_edited          INTEGER NOT NULL DEFAULT 0,
  is_forwarded       INTEGER NOT NULL DEFAULT 0,
  has_media          INTEGER NOT NULL DEFAULT 0,
  media_ref          TEXT,
  source_ref         TEXT NOT NULL DEFAULT '',
  parse_confidence   REAL NOT NULL DEFAULT 1.0,
  content_hash       TEXT NOT NULL,
  imported_at        TEXT NOT NULL,
  word_count         INTEGER NOT NULL DEFAULT 0,
  char_count         INTEGER NOT NULL DEFAULT 0,
  session_id         TEXT,
  UNIQUE (case_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_msg_conv_time ON messages(conversation_id, sent_at_utc);
CREATE INDEX IF NOT EXISTS idx_msg_case_time ON messages(case_id, sent_at_utc);
CREATE INDEX IF NOT EXISTS idx_msg_sender ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_msg_evidence ON messages(evidence_id);

-- One normalised message can be observed in several evidence items (e.g. two
-- exports of the same conversation). Observations keep per-source provenance
-- without duplicating message rows.
CREATE TABLE IF NOT EXISTS message_observations (
  id           TEXT PRIMARY KEY,
  message_id   TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  evidence_id  TEXT NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
  source_ref   TEXT NOT NULL DEFAULT '',
  observed_at  TEXT NOT NULL,
  body_hash    TEXT NOT NULL DEFAULT '',
  UNIQUE (message_id, evidence_id)
);
CREATE INDEX IF NOT EXISTS idx_obs_evidence ON message_observations(evidence_id);
CREATE INDEX IF NOT EXISTS idx_obs_message ON message_observations(message_id);

CREATE TABLE IF NOT EXISTS message_versions (
  id          TEXT PRIMARY KEY,
  message_id  TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  version     INTEGER NOT NULL,
  body        TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  evidence_id TEXT,
  note        TEXT NOT NULL DEFAULT '',
  UNIQUE (message_id, version)
);

CREATE TABLE IF NOT EXISTS message_references (
  id        TEXT PRIMARY KEY,
  message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  ref_type  TEXT NOT NULL,
  ref_value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msgref_msg ON message_references(message_id);

CREATE TABLE IF NOT EXISTS attachments (
  id              TEXT PRIMARY KEY,
  case_id         TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  evidence_id     TEXT,
  message_id      TEXT REFERENCES messages(id) ON DELETE SET NULL,
  conversation_id TEXT,
  file_name       TEXT NOT NULL,
  relative_path   TEXT NOT NULL DEFAULT '',
  stored_path     TEXT,
  media_type      TEXT NOT NULL DEFAULT 'document',
  mime            TEXT,
  size_bytes      INTEGER NOT NULL DEFAULT 0,
  sha256          TEXT,
  phash           TEXT,
  width           INTEGER,
  height          INTEGER,
  duration_ms     INTEGER,
  missing         INTEGER NOT NULL DEFAULT 0,
  linked          INTEGER NOT NULL DEFAULT 1,
  meta_json       TEXT NOT NULL DEFAULT '{}',
  created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_att_case ON attachments(case_id);
CREATE INDEX IF NOT EXISTS idx_att_msg ON attachments(message_id);
CREATE INDEX IF NOT EXISTS idx_att_hash ON attachments(case_id, sha256);

CREATE TABLE IF NOT EXISTS media_metadata (
  id            TEXT PRIMARY KEY,
  attachment_id TEXT NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
  key           TEXT NOT NULL,
  value         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audio_transcripts (
  id            TEXT PRIMARY KEY,
  attachment_id TEXT NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
  model         TEXT NOT NULL,
  language      TEXT,
  text          TEXT NOT NULL,
  json          TEXT NOT NULL DEFAULT '{}',
  confidence    REAL,
  created_at    TEXT NOT NULL,
  edited        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_transcript_att ON audio_transcripts(attachment_id);

CREATE TABLE IF NOT EXISTS group_events (
  id              TEXT PRIMARY KEY,
  case_id         TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  message_id      TEXT,
  event_type      TEXT NOT NULL,
  actor           TEXT,
  target          TEXT,
  occurred_at     TEXT NOT NULL,
  raw_text        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS message_tags (
  id         TEXT PRIMARY KEY,
  case_id    TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  tag        TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (message_id, tag)
);

CREATE TABLE IF NOT EXISTS bookmarks (
  id         TEXT PRIMARY KEY,
  case_id    TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  label      TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE (message_id)
);

CREATE TABLE IF NOT EXISTS investigation_notes (
  id         TEXT PRIMARY KEY,
  case_id    TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  message_id TEXT,
  author     TEXT NOT NULL DEFAULT '',
  body       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_searches (
  id         TEXT PRIMARY KEY,
  case_id    TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  query_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timeline_events (
  id              TEXT PRIMARY KEY,
  case_id         TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  occurred_at     TEXT NOT NULL,
  kind            TEXT NOT NULL,
  title           TEXT NOT NULL,
  detail          TEXT NOT NULL DEFAULT '',
  ref_table       TEXT,
  ref_id          TEXT,
  conversation_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_tl_case_time ON timeline_events(case_id, occurred_at);

CREATE TABLE IF NOT EXISTS analysis_runs (
  id          TEXT PRIMARY KEY,
  case_id     TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,
  params_json TEXT NOT NULL DEFAULT '{}',
  status      TEXT NOT NULL DEFAULT 'done',
  started_at  TEXT NOT NULL,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS analysis_results (
  id           TEXT PRIMARY KEY,
  case_id      TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  run_id       TEXT,
  kind         TEXT NOT NULL,
  subject_type TEXT,
  subject_id   TEXT,
  value_json   TEXT NOT NULL DEFAULT '{}',
  created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ares_case_kind ON analysis_results(case_id, kind);

CREATE TABLE IF NOT EXISTS ai_models (
  id         TEXT PRIMARY KEY,
  provider   TEXT NOT NULL,
  name       TEXT NOT NULL,
  kind       TEXT NOT NULL DEFAULT 'chat',
  size_bytes INTEGER,
  installed  INTEGER NOT NULL DEFAULT 0,
  added_at   TEXT NOT NULL,
  UNIQUE (provider, name)
);

CREATE TABLE IF NOT EXISTS ai_queries (
  id            TEXT PRIMARY KEY,
  case_id       TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  question      TEXT NOT NULL,
  provider      TEXT NOT NULL,
  model         TEXT NOT NULL,
  answer        TEXT NOT NULL DEFAULT '',
  citations_json TEXT NOT NULL DEFAULT '[]',
  observed_json TEXT NOT NULL DEFAULT '{}',
  status        TEXT NOT NULL DEFAULT 'done',
  error         TEXT,
  duration_ms   INTEGER,
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_evidence_citations (
  id         TEXT PRIMARY KEY,
  query_id   TEXT NOT NULL REFERENCES ai_queries(id) ON DELETE CASCADE,
  message_id TEXT,
  score      REAL,
  snippet    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_cite_query ON ai_evidence_citations(query_id);

CREATE TABLE IF NOT EXISTS recovery_findings (
  id          TEXT PRIMARY KEY,
  case_id     TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,
  status      TEXT NOT NULL,
  summary     TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  message_id  TEXT,
  evidence_id TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rec_case ON recovery_findings(case_id);

CREATE TABLE IF NOT EXISTS reports (
  id          TEXT PRIMARY KEY,
  case_id     TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  type        TEXT NOT NULL,
  format      TEXT NOT NULL,
  path        TEXT NOT NULL,
  size_bytes  INTEGER NOT NULL DEFAULT 0,
  sha256      TEXT,
  params_json TEXT NOT NULL DEFAULT '{}',
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS export_jobs (
  id          TEXT PRIMARY KEY,
  case_id     TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'done',
  path        TEXT,
  created_at  TEXT NOT NULL,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id          TEXT PRIMARY KEY,
  case_id     TEXT,
  at          TEXT NOT NULL,
  actor       TEXT NOT NULL DEFAULT 'user',
  action      TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_logs(case_id, at);

CREATE TABLE IF NOT EXISTS application_settings (
  key        TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Full text index. Standalone (not external-content) so case_id and denormalised
-- sender/conversation labels can be filtered directly inside FTS queries.
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  message_id UNINDEXED,
  case_id UNINDEXED,
  body,
  sender,
  conversation,
  tokenize = 'unicode61 remove_diacritics 2'
);
