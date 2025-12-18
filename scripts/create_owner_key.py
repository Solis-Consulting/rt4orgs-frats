#!/usr/bin/env python3
"""
Create the owner API key - the master key that unlocks everything.
Run this once to generate your owner API token.
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.auth import create_user
import psycopg2

def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        print("   Set it with: export DATABASE_URL='your_database_url'")
        return
    
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        
        # Check if owner already exists
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
            if cur.fetchone():
                print("⚠️  Owner user already exists!")
                print("   If you want to create a new one, delete the existing admin user first.")
                return
        
        # Create owner user
        user = create_user(
            conn=conn,
            username="Owner",
            role="admin",
            twilio_phone=None,
            user_id="owner"
        )
        
        print("\n" + "=" * 70)
        print("✅ OWNER API KEY CREATED!")
        print("=" * 70)
        print("\n🔑 YOUR OWNER API TOKEN (save this - it won't be shown again):")
        print("=" * 70)
        print(user['api_token'])
        print("=" * 70)
        print("\n📝 Use this token to:")
        print("   - Log in at: /ui/login.html")
        print("   - Access admin UI: /ui/admin.html")
        print("   - Manage phone pairing and blasts")
        print("   - Create rep users")
        print("\n💡 This is your master key - it has full access to everything!")
        print("=" * 70 + "\n")
        
        conn.close()
    except Exception as e:
        print(f"❌ Error creating owner key: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
