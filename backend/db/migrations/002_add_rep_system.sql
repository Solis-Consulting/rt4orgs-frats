-- Migration 002: Add Sales Rep System
-- Creates users table, card_assignments table, and extends conversations table

-- 1. Users table - Store rep accounts
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,  -- e.g., "david", "rep_1"
    username TEXT UNIQUE NOT NULL,
    api_token TEXT UNIQUE NOT NULL,  -- Hashed token for authentication
    role TEXT DEFAULT 'rep' CHECK (role IN ('admin', 'rep')),
    twilio_phone_number TEXT,  -- Rep's dedicated Twilio phone number
    twilio_account_sid TEXT,  -- Optional: rep-specific Twilio account
    twilio_auth_token TEXT,   -- Optional: rep-specific Twilio auth token
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_api_token ON users(api_token);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- 2. Card assignments table - Track which cards are assigned to which reps
CREATE TABLE IF NOT EXISTS card_assignments (
    id SERIAL PRIMARY KEY,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP DEFAULT NOW(),
    assigned_by TEXT,  -- Admin user who made the assignment
    status TEXT DEFAULT 'assigned' CHECK (status IN ('assigned', 'active', 'closed', 'lost')),
    notes TEXT,
    UNIQUE(card_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_card_assignments_user_id ON card_assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_card_assignments_card_id ON card_assignments(card_id);
CREATE INDEX IF NOT EXISTS idx_card_assignments_status ON card_assignments(status);

-- 3. Extend conversations table for rep routing
DO $$ 
BEGIN
    -- Add routing_mode column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'conversations' 
        AND column_name = 'routing_mode'
    ) THEN
        ALTER TABLE conversations 
        ADD COLUMN routing_mode TEXT DEFAULT 'ai' CHECK (routing_mode IN ('ai', 'rep'));
    END IF;

    -- Add rep_user_id column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'conversations' 
        AND column_name = 'rep_user_id'
    ) THEN
        ALTER TABLE conversations 
        ADD COLUMN rep_user_id TEXT REFERENCES users(id);
    END IF;

    -- Add rep_phone_number column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'conversations' 
        AND column_name = 'rep_phone_number'
    ) THEN
        ALTER TABLE conversations 
        ADD COLUMN rep_phone_number TEXT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_conversations_rep_user_id ON conversations(rep_user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_routing_mode ON conversations(routing_mode);
