-- JSON-Native CRM Schema Migration
-- Creates conversations table, cards table, card_relationships table, and bridges them

-- 0. Conversations Table (required for Markov + Cards bridge)
-- This table stores SMS conversation state for the intelligence/Markov system
CREATE TABLE IF NOT EXISTS conversations (
    phone TEXT PRIMARY KEY,
    contact_id TEXT,
    card_id TEXT,  -- Will be linked to cards table via foreign key constraint below
    owner TEXT,
    state TEXT DEFAULT 'initial_outreach',
    source_batch_id TEXT,
    history JSONB DEFAULT '[]'::jsonb,
    last_outbound_at TIMESTAMP,
    last_inbound_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_phone ON conversations(phone);
CREATE INDEX IF NOT EXISTS idx_conversations_state ON conversations(state);
CREATE INDEX IF NOT EXISTS idx_conversations_owner ON conversations(owner);
CREATE INDEX IF NOT EXISTS idx_conversations_card_id ON conversations(card_id);

-- 1. Cards Table (JSONB storage)
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('person', 'fraternity', 'team', 'business')),
    card_data JSONB NOT NULL,
    sales_state TEXT DEFAULT 'cold',
    owner TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cards_type ON cards(type);
CREATE INDEX IF NOT EXISTS idx_cards_sales_state ON cards(sales_state);
CREATE INDEX IF NOT EXISTS idx_cards_owner ON cards(owner);
CREATE INDEX IF NOT EXISTS idx_cards_card_data_gin ON cards USING GIN(card_data);

-- 2. Relationships Table (relational)
CREATE TABLE IF NOT EXISTS card_relationships (
    id SERIAL PRIMARY KEY,
    parent_card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    child_card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL, -- 'member', 'contact', 'owner'
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(parent_card_id, child_card_id, relationship_type)
);

CREATE INDEX IF NOT EXISTS idx_relationships_parent ON card_relationships(parent_card_id);
CREATE INDEX IF NOT EXISTS idx_relationships_child ON card_relationships(child_card_id);

-- 3. Blast Runs Table (tracking blasts triggered from UI / scripts)
CREATE TABLE IF NOT EXISTS blast_runs (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW(),
    owner TEXT,
    source TEXT,
    limit_count INTEGER,
    total_targets INTEGER,
    sent_count INTEGER,
    status TEXT
);

-- 4. Markov Response Configuration Table
CREATE TABLE IF NOT EXISTS markov_responses (
    state_key TEXT PRIMARY KEY,
    response_text TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_markov_responses_state ON markov_responses(state_key);

-- 5. Bridge Conversations to Cards
-- Add foreign key constraint to card_id column (if conversations table exists and column exists)
DO $$ 
BEGIN
    -- Only proceed if conversations table exists
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'conversations'
    ) THEN
        -- Check if card_id column exists (it should, since we created it above)
        IF EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_schema = 'public'
            AND table_name = 'conversations' 
            AND column_name = 'card_id'
        ) THEN
            -- Add foreign key constraint if it doesn't already exist
            -- First check if constraint already exists
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu 
                    ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_schema = 'public'
                AND tc.table_name = 'conversations'
                AND kcu.column_name = 'card_id'
                AND tc.constraint_type = 'FOREIGN KEY'
            ) THEN
                ALTER TABLE conversations 
                ADD CONSTRAINT fk_conversations_card_id 
                FOREIGN KEY (card_id) REFERENCES cards(id);
            END IF;
        END IF;
    END IF;
END $$;

