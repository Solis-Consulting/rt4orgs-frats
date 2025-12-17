"""
Authentication system for sales reps.
Handles API token generation, hashing, and user management.
"""

from __future__ import annotations

import secrets
import hashlib
from typing import Optional, Dict, Any
import psycopg2


def generate_api_token() -> str:
    """Generate a secure random API token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a token using SHA-256 for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token(token: str, hashed: str) -> bool:
    """Verify a token against its hash."""
    return hash_token(token) == hashed


def get_user_by_token(conn: Any, token: str) -> Optional[Dict[str, Any]]:
    """Lookup user by API token. Returns user dict or None."""
    if not token:
        return None
    
    hashed_token = hash_token(token)
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, username, role, twilio_phone_number, twilio_account_sid, 
                   twilio_auth_token, created_at, updated_at, is_active
            FROM users
            WHERE api_token = %s AND is_active = TRUE
        """, (hashed_token,))
        
        row = cur.fetchone()
        if not row:
            return None
        
        return {
            "id": row[0],
            "username": row[1],
            "role": row[2],
            "twilio_phone_number": row[3],
            "twilio_account_sid": row[4],
            "twilio_auth_token": row[5],
            "created_at": row[6],
            "updated_at": row[7],
            "is_active": row[8],
        }


def create_user(
    conn: Any,
    username: str,
    role: str = "rep",
    twilio_phone: Optional[str] = None,
    twilio_account_sid: Optional[str] = None,
    twilio_auth_token: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new user (rep or admin).
    Returns dict with user info including the plaintext token (only shown once).
    """
    if not user_id:
        # Generate user_id from username (lowercase, replace spaces with underscores)
        user_id = username.lower().replace(" ", "_").replace("-", "_")
    
    # Generate API token
    plaintext_token = generate_api_token()
    hashed_token = hash_token(plaintext_token)
    
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (
                id, username, api_token, role, twilio_phone_number,
                twilio_account_sid, twilio_auth_token
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, username, role, created_at
        """, (
            user_id,
            username,
            hashed_token,
            role,
            twilio_phone,
            twilio_account_sid,
            twilio_auth_token,
        ))
        
        row = cur.fetchone()
        
        return {
            "id": row[0],
            "username": row[1],
            "role": row[2],
            "created_at": row[3],
            "api_token": plaintext_token,  # Only returned on creation
        }


def update_user_twilio_config(
    conn: Any,
    user_id: str,
    phone: Optional[str] = None,
    account_sid: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> bool:
    """Update a user's Twilio configuration."""
    updates = []
    params = []
    
    if phone is not None:
        updates.append("twilio_phone_number = %s")
        params.append(phone)
    
    if account_sid is not None:
        updates.append("twilio_account_sid = %s")
        params.append(account_sid)
    
    if auth_token is not None:
        updates.append("twilio_auth_token = %s")
        params.append(auth_token)
    
    if not updates:
        return False
    
    updates.append("updated_at = NOW()")
    params.append(user_id)
    
    with conn.cursor() as cur:
        cur.execute(f"""
            UPDATE users
            SET {', '.join(updates)}
            WHERE id = %s
        """, params)
        
        return cur.rowcount > 0


def get_user(conn: Any, user_id: str) -> Optional[Dict[str, Any]]:
    """Get user by ID."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, username, role, twilio_phone_number, twilio_account_sid,
                   twilio_auth_token, created_at, updated_at, is_active
            FROM users
            WHERE id = %s
        """, (user_id,))
        
        row = cur.fetchone()
        if not row:
            return None
        
        return {
            "id": row[0],
            "username": row[1],
            "role": row[2],
            "twilio_phone_number": row[3],
            "twilio_account_sid": row[4],
            "twilio_auth_token": row[5],
            "created_at": row[6],
            "updated_at": row[7],
            "is_active": row[8],
        }


def list_users(conn: Any, include_inactive: bool = False) -> list[Dict[str, Any]]:
    """List all users."""
    query = """
        SELECT id, username, role, twilio_phone_number, created_at, updated_at, is_active
        FROM users
    """
    params = []
    
    if not include_inactive:
        query += " WHERE is_active = TRUE"
    
    query += " ORDER BY created_at DESC"
    
    with conn.cursor() as cur:
        cur.execute(query, params)
        
        users = []
        for row in cur.fetchall():
            users.append({
                "id": row[0],
                "username": row[1],
                "role": row[2],
                "twilio_phone_number": row[3],
                "created_at": row[4],
                "updated_at": row[5],
                "is_active": row[6],
            })
        
        return users
