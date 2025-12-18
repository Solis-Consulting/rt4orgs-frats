#!/usr/bin/env python3
"""
Script to set David's API token to a specific value.
Usage: python scripts/set_david_token.py
"""

import os
import sys
import hashlib
import psycopg2

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.auth import hash_token

# David's desired API token
DAVID_TOKEN = "012QosXKsYDECWtyR869YuyMdXLKHjkUXRfDFgf4lgw"
DAVID_USER_ID = "david_lee"

def set_david_token():
    """Set David's API token to the specified value."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ ERROR: DATABASE_URL environment variable not set")
        print("   Set it with: export DATABASE_URL=postgresql://...")
        return False
    
    # Hash the token
    hashed_token = hash_token(DAVID_TOKEN)
    
    print("=" * 60)
    print("Setting David's API Token")
    print("=" * 60)
    print(f"User ID: {DAVID_USER_ID}")
    print(f"Token (plaintext): {DAVID_TOKEN}")
    print(f"Token (hashed): {hashed_token}")
    print("=" * 60)
    
    try:
        conn = psycopg2.connect(database_url, connect_timeout=10)
        conn.autocommit = True
        
        with conn.cursor() as cur:
            # Check if David exists
            cur.execute("""
                SELECT id, username, role, is_active
                FROM users
                WHERE id = %s
            """, (DAVID_USER_ID,))
            
            row = cur.fetchone()
            if not row:
                print(f"❌ ERROR: User '{DAVID_USER_ID}' not found in database")
                print("   Create the user first via admin UI or create_user script")
                return False
            
            user_id, username, role, is_active = row
            print(f"✅ Found user: {username} (role: {role}, active: {is_active})")
            
            # Update the token
            cur.execute("""
                UPDATE users
                SET api_token = %s, updated_at = NOW()
                WHERE id = %s
            """, (hashed_token, DAVID_USER_ID))
            
            if cur.rowcount > 0:
                print(f"✅ Successfully updated API token for {username}")
                print(f"✅ Token is now: {DAVID_TOKEN}")
                print("=" * 60)
                print("⚠️  IMPORTANT: Save this token - it won't be shown again!")
                print("=" * 60)
                return True
            else:
                print(f"❌ ERROR: No rows updated (user might not exist)")
                return False
                
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    success = set_david_token()
    sys.exit(0 if success else 1)
