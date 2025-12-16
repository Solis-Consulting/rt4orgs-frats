-- JSON-Native CRM Schema Migration
-- Creates cards table, card_relationships table, and bridges to conversations

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

-- 3. Bridge to Conversations
-- Add card_id reference to conversations (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'conversations' AND column_name = 'card_id'
    ) THEN
        ALTER TABLE conversations ADD COLUMN card_id TEXT REFERENCES cards(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_conversations_card_id ON conversations(card_id);

