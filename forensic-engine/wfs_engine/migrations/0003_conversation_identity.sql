-- Conversation identity used for message fingerprints and cross-snapshot
-- reconciliation. Distinct chats must never collapse just because a sender,
-- timestamp and text happen to match.
ALTER TABLE conversations ADD COLUMN identity_key TEXT;

-- Legacy rows were identified by their display title; adopt that as their key so
-- existing cases keep working and are upgraded on the next import.
UPDATE conversations
   SET identity_key = 'title:' || lower(trim(title))
 WHERE identity_key IS NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_identity
    ON conversations(case_id, identity_key);
