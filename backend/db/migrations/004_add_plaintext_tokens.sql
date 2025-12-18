-- Migration 004: Add plaintext token storage for reps
-- Owner tokens remain hashed only (secure), rep tokens have both hashed and plaintext

DO $$ 
BEGIN
    -- Add api_token_plaintext column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'users' 
        AND column_name = 'api_token_plaintext'
    ) THEN
        ALTER TABLE users 
        ADD COLUMN api_token_plaintext TEXT;
        
        -- Add comment explaining the column
        COMMENT ON COLUMN users.api_token_plaintext IS 'Plaintext API token (only for reps, NULL for owner/admin). Owner tokens are hashed only for security.';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_api_token_plaintext ON users(api_token_plaintext) WHERE api_token_plaintext IS NOT NULL;
