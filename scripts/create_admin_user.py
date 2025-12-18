#!/usr/bin/env python3
"""
Script to create the first admin user.
Run this to generate an API token for initial login.
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.auth import create_user, hash_token
import psycopg2

def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        return
    
    username = input("Enter username for admin user: ").strip()
    if not username:
        print("❌ Username is required")
        return
    
    user_id = input(f"Enter user ID (or press Enter to use '{username.lower().replace(' ', '_')}'): ").strip()
    if not user_id:
        user_id = username.lower().replace(" ", "_").replace("-", "_")
    
    twilio_phone = input("Enter Twilio phone number (optional, press Enter to skip): ").strip() or None
    
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        
        user = create_user(
            conn=conn,
            username=username,
            role="admin",
            twilio_phone=twilio_phone,
            user_id=user_id
        )
        
        print("\n" + "=" * 60)
        print("✅ Admin user created successfully!")
        print("=" * 60)
        print(f"Username: {user['username']}")
        print(f"User ID: {user['id']}")
        print(f"Role: admin")
        print("\n🔑 API TOKEN (save this - it won't be shown again):")
        print("=" * 60)
        print(user['api_token'])
        print("=" * 60)
        print("\nUse this token to log in at: /ui/login.html")
        
        conn.close()
    except Exception as e:
        print(f"❌ Error creating user: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
