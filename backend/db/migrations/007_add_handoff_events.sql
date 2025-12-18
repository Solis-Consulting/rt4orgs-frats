-- Migration 007: Add handoff_events table for tracking ownership changes and Markov state transitions
-- This provides full auditability for rep reassignments, card deletions, and blast claims

CREATE TABLE IF NOT EXISTS handoff_events (
  id SERIAL PRIMARY KEY,
  card_id TEXT NOT NULL,
  from_rep TEXT,
  to_rep TEXT,
  reason TEXT,
  markov_state_before TEXT,
  markov_state_after TEXT,
  assigned_by TEXT,  -- Admin/rep who triggered the handoff
  conversation_id TEXT,  -- Futureproof: nullable for now
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_handoff_events_card_id ON handoff_events(card_id);
CREATE INDEX IF NOT EXISTS idx_handoff_events_to_rep ON handoff_events(to_rep);
CREATE INDEX IF NOT EXISTS idx_handoff_events_created_at ON handoff_events(created_at);

-- Note: to_rep can be NULL for terminal events (card deletion)
