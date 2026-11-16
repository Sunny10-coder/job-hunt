-- v2: optional local embeddings for semantic retrieval
CREATE TABLE IF NOT EXISTS message_embeddings (
  message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  model      TEXT NOT NULL,
  dim        INTEGER NOT NULL,
  vector     BLOB NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (message_id, model)
);
CREATE INDEX IF NOT EXISTS idx_embed_model ON message_embeddings(model);
