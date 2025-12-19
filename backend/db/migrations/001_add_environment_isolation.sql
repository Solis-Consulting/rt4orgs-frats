-- Migration: Add Environment Isolation to Conversations
-- This fixes the root cause: one conversation per (phone_number × rep × campaign)
-- 
-- Key changes:
-- 1. Add environment_id column to conversations
-- 2. Change primary key from phone to (phone, environment_id)
-- 3. Create message_events table to track all messages with message_sid
-- 4. Add indexes for efficient routing

-- Step 1: Create message_events table (tracks all sent messages with message_sid)
CREATE TABLE IF NOT EXISTS message_events (
    id SERIAL PRIMARY KEY,
    phone_number TEXT NOT NULL,
    environment_id TEXT NOT NULL,
    rep_id TEXT,
    campaign_id TEXT,
    message_sid TEXT,  -- REQUIRED: Only rows with message_sid count as "sent"
    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    sent_at TIMESTAMP NOT NULL DEFAULT NOW(),
    state TEXT,
    message_text TEXT,
    twilio_status TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_message_events_phone_env ON message_events(phone_number, environment_id);
CREATE INDEX IF NOT EXISTS idx_message_events_phone_sent_at ON message_events(phone_number, sent_at DESC) WHERE message_sid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_message_events_environment ON message_events(environment_id);
CREATE INDEX IF NOT EXISTS idx_message_events_message_sid ON message_events(message_sid) WHERE message_sid IS NOT NULL;

-- Step 2: Add environment_id to conversations table
-- First, check if column exists
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'conversations' 
        AND column_name = 'environment_id'
    ) THEN
        ALTER TABLE conversations ADD COLUMN environment_id TEXT;
    END IF;
END $$;

-- Step 3: Generate environment_id for existing conversations
-- Use hash of (rep_user_id + campaign_id) or default to phone-based for legacy
-- CRITICAL: Each existing conversation gets a unique environment_id to avoid primary key conflicts
-- We use phone + rep_user_id to ensure uniqueness (legacy conversations are isolated)
DO $$
DECLARE
    conv_record RECORD;
    env_id TEXT;
    counter INTEGER := 0;
BEGIN
    FOR conv_record IN SELECT phone, rep_user_id, card_id FROM conversations WHERE environment_id IS NULL
    LOOP
        -- Generate environment_id from existing data
        -- Use phone as part of hash to ensure uniqueness for legacy conversations
        -- This prevents primary key conflicts when multiple conversations exist for same phone
        IF conv_record.rep_user_id IS NOT NULL THEN
            env_id := 'env_' || MD5(COALESCE(conv_record.rep_user_id, 'owner') || '_default_' || conv_record.phone);
        ELSE
            env_id := 'env_' || MD5('owner_default_' || conv_record.phone);
        END IF;
        
        UPDATE conversations 
        SET environment_id = env_id 
        WHERE phone = conv_record.phone 
          AND (rep_user_id = conv_record.rep_user_id OR (rep_user_id IS NULL AND conv_record.rep_user_id IS NULL))
          AND environment_id IS NULL
        LIMIT 1;
        
        counter := counter + 1;
    END LOOP;
    
    RAISE NOTICE 'Generated environment_id for % existing conversations', counter;
END $$;

-- Step 4: Make environment_id NOT NULL and set default
-- First ensure all rows have environment_id (should be done in Step 3, but double-check)
UPDATE conversations SET environment_id = 'env_' || MD5('owner_default_' || phone) WHERE environment_id IS NULL;

-- Set default function (PostgreSQL doesn't support MD5 in DEFAULT directly, so we'll use a function)
-- Actually, we can't use MD5 in DEFAULT easily, so we'll just set NOT NULL
-- The application code will always provide environment_id
ALTER TABLE conversations ALTER COLUMN environment_id SET NOT NULL;

-- Step 5: Drop old primary key and create new composite key
DO $$
BEGIN
    -- Drop existing primary key constraint
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'conversations_pkey'
        AND table_name = 'conversations'
    ) THEN
        ALTER TABLE conversations DROP CONSTRAINT conversations_pkey;
    END IF;
    
    -- Create new composite primary key
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'conversations_pkey'
        AND table_name = 'conversations'
    ) THEN
        ALTER TABLE conversations ADD PRIMARY KEY (phone, environment_id);
    END IF;
END $$;

-- Step 6: Add indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_conversations_phone_env ON conversations(phone, environment_id);
CREATE INDEX IF NOT EXISTS idx_conversations_environment ON conversations(environment_id);
CREATE INDEX IF NOT EXISTS idx_conversations_phone ON conversations(phone);  -- Keep for backward compatibility

-- Step 7: Add helper function to generate environment_id
CREATE OR REPLACE FUNCTION generate_environment_id(rep_id TEXT, campaign_id TEXT) 
RETURNS TEXT AS $$
BEGIN
    RETURN 'env_' || MD5(COALESCE(rep_id, 'owner') || '_' || COALESCE(campaign_id, 'default'));
END;
$$ LANGUAGE plpgsql IMMUTABLE;
