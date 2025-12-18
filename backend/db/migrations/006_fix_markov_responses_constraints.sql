-- Migration 006: Fix markov_responses constraints for per-user responses
-- Drops the primary key on state_key and creates proper unique constraints

DO $$ 
BEGIN
    -- Check if user_id column exists (from migration 005)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'markov_responses' 
        AND column_name = 'user_id'
    ) THEN
        -- Drop the primary key constraint if it exists
        IF EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_schema = 'public'
            AND table_name = 'markov_responses'
            AND constraint_type = 'PRIMARY KEY'
        ) THEN
            ALTER TABLE markov_responses DROP CONSTRAINT markov_responses_pkey;
        END IF;
        
        -- Drop existing partial unique indexes if they exist (will recreate them)
        DROP INDEX IF EXISTS idx_markov_responses_state_user;
        DROP INDEX IF EXISTS idx_markov_responses_state_global;
        
        -- Create unique constraint for rep-specific responses (user_id IS NOT NULL)
        -- This creates a unique constraint that PostgreSQL can use with ON CONFLICT
        CREATE UNIQUE INDEX idx_markov_responses_state_user 
        ON markov_responses(state_key, user_id)
        WHERE user_id IS NOT NULL;
        
        -- Create unique constraint for global responses (user_id IS NULL)
        CREATE UNIQUE INDEX idx_markov_responses_state_global
        ON markov_responses(state_key)
        WHERE user_id IS NULL;
        
        -- Add a comment explaining the constraint strategy
        COMMENT ON INDEX idx_markov_responses_state_user IS 'Unique constraint for rep-specific responses: (state_key, user_id) where user_id IS NOT NULL';
        COMMENT ON INDEX idx_markov_responses_state_global IS 'Unique constraint for global responses: (state_key) where user_id IS NULL';
    END IF;
END $$;
