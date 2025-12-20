-- Migration 010: Fix ON DELETE CASCADE on conversations.card_id foreign key
-- This migration ensures conversations are automatically deleted when cards are deleted
-- Handles all cases: missing FK, FK without CASCADE, or FK with wrong name

DO $$
DECLARE
  constraint_name TEXT;
BEGIN
  -- Find any existing FK constraint on conversations.card_id
  SELECT conname INTO constraint_name
  FROM pg_constraint
  WHERE conrelid = 'conversations'::regclass
    AND contype = 'f'
    AND conkey::text LIKE '%card_id%'
  LIMIT 1;
  
  -- Drop existing FK if it exists (regardless of name or CASCADE status)
  IF constraint_name IS NOT NULL THEN
    EXECUTE 'ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ' || quote_ident(constraint_name);
    RAISE NOTICE 'Dropped existing FK constraint: %', constraint_name;
  END IF;
  
  -- Also try dropping by common names (in case the query didn't find it)
  ALTER TABLE conversations DROP CONSTRAINT IF EXISTS fk_conversations_card_id;
  ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_card_id_fkey;
  
  -- Create FK with CASCADE (idempotent - will only create if doesn't exist)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'conversations'::regclass
      AND contype = 'f'
      AND conkey::text LIKE '%card_id%'
  ) THEN
    ALTER TABLE conversations
    ADD CONSTRAINT fk_conversations_card_id
    FOREIGN KEY (card_id)
    REFERENCES cards(id)
    ON DELETE CASCADE;
    
    RAISE NOTICE 'Created FK constraint with ON DELETE CASCADE';
  END IF;
END $$;
