-- Migration 005: Add rep-scoped Markov responses
-- Allows each rep to have their own markov response configurations

DO $$ 
BEGIN
    -- Add user_id column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'markov_responses' 
        AND column_name = 'user_id'
    ) THEN
        ALTER TABLE markov_responses 
        ADD COLUMN user_id TEXT REFERENCES users(id) ON DELETE CASCADE;
        
        -- Add comment explaining the column
        COMMENT ON COLUMN markov_responses.user_id IS 'User ID for rep-scoped responses. NULL = global/owner responses.';
        
        -- Create index for faster lookups
        CREATE INDEX IF NOT EXISTS idx_markov_responses_user_id ON markov_responses(user_id);
        
        -- Create unique constraint: state_key + user_id (NULL user_id = global)
        -- Use partial unique indexes to handle NULL user_id correctly
        -- For rep-specific responses (user_id IS NOT NULL): unique on (state_key, user_id)
        CREATE UNIQUE INDEX IF NOT EXISTS idx_markov_responses_state_user 
        ON markov_responses(state_key, user_id)
        WHERE user_id IS NOT NULL;
        
        -- For global responses (user_id IS NULL): unique on state_key only
        CREATE UNIQUE INDEX IF NOT EXISTS idx_markov_responses_state_global
        ON markov_responses(state_key)
        WHERE user_id IS NULL;
    END IF;
END $$;
