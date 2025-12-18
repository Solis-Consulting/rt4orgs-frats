-- Migration 003: Normalize rep API tokens to use Twilio Account SID
-- Updates existing rep users to use their Twilio Account SID as their API token
-- Owner (admin role) tokens remain unchanged (randomly generated)

-- Enable pgcrypto extension for digest function (required for SHA-256 hashing)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- This migration updates the api_token for all rep users to use their twilio_account_sid
-- Only affects users where:
--   1. role = 'rep' (not admin/owner)
--   2. twilio_account_sid is not NULL
--   3. twilio_account_sid is not empty

-- Note: Uses SHA-256 hashing (same as hash_token function in backend/auth.py)
-- The hash_token function does: hashlib.sha256(token.encode()).hexdigest()
-- Which is equivalent to: encode(digest(token, 'sha256'), 'hex') in PostgreSQL

DO $$
DECLARE
    rep_record RECORD;
    new_hashed_token TEXT;
    updated_count INTEGER := 0;
BEGIN
    -- Loop through all rep users with Twilio Account SIDs
    FOR rep_record IN 
        SELECT id, username, twilio_account_sid, api_token
        FROM users
        WHERE role = 'rep' 
          AND twilio_account_sid IS NOT NULL 
          AND twilio_account_sid != ''
    LOOP
        -- Hash the Twilio Account SID (same way we hash tokens in auth.py)
        -- hash_token() does: hashlib.sha256(token.encode()).hexdigest()
        -- PostgreSQL equivalent: encode(digest(token, 'sha256'), 'hex')
        SELECT encode(digest(rep_record.twilio_account_sid, 'sha256'), 'hex') INTO new_hashed_token;
        
        -- Only update if the token is different (avoid unnecessary updates)
        IF rep_record.api_token != new_hashed_token THEN
            -- Update the api_token to the hashed Twilio Account SID
            UPDATE users
            SET api_token = new_hashed_token,
                updated_at = NOW()
            WHERE id = rep_record.id;
            
            updated_count := updated_count + 1;
            RAISE NOTICE 'Updated rep % (%) to use Twilio Account SID % as API token', 
                rep_record.username, rep_record.id, rep_record.twilio_account_sid;
        ELSE
            RAISE NOTICE 'Rep % (%) already using Twilio Account SID as API token', 
                rep_record.username, rep_record.id;
        END IF;
    END LOOP;
    
    RAISE NOTICE 'Migration 003: Normalized % rep API token(s) to Twilio Account SIDs', updated_count;
END $$;
