-- Migration 008: Add ON DELETE CASCADE to conversations.card_id foreign key
-- This ensures conversations are automatically deleted when cards are deleted
-- Handles case where FK exists but lacks CASCADE by dropping and recreating

DO $$
DECLARE
  fk_exists BOOLEAN;
  has_cascade BOOLEAN;
  constraint_name TEXT;
BEGIN
  -- Find existing FK constraint name
  SELECT conname INTO constraint_name
  FROM pg_constraint
  WHERE conrelid = 'conversations'::regclass
    AND confrelid = 'cards'::regclass
    AND contype = 'f'
    AND conkey::text LIKE '%card_id%'
  LIMIT 1;
  
  fk_exists := (constraint_name IS NOT NULL);
  
  -- Check if existing FK has CASCADE
  IF fk_exists THEN
    SELECT confdeltype = 'c' INTO has_cascade
    FROM pg_constraint
    WHERE conname = constraint_name;
    
    -- If FK exists but no CASCADE, drop and recreate
    IF NOT has_cascade THEN
      EXECUTE 'ALTER TABLE conversations DROP CONSTRAINT ' || constraint_name;
      fk_exists := FALSE;
    END IF;
  END IF;
  
  -- Create FK with CASCADE if it doesn't exist
  IF NOT fk_exists THEN
    ALTER TABLE conversations
    ADD CONSTRAINT conversations_card_id_fkey
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE;
  END IF;
END $$;
