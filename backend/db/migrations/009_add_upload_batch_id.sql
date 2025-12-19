-- Migration: Add upload_batch_id to cards table
-- This tracks which JSON upload/batch each card came from

-- Add upload_batch_id column to cards table
ALTER TABLE cards ADD COLUMN IF NOT EXISTS upload_batch_id TEXT;

-- Create index for efficient grouping
CREATE INDEX IF NOT EXISTS idx_cards_upload_batch_id ON cards(upload_batch_id);

-- Add comment
COMMENT ON COLUMN cards.upload_batch_id IS 'Identifier for the upload batch/JSON source that imported this card';
