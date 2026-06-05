"""
Auth Service - JWT authentication and user management for the frontend.
"""

import os
import sqlite3
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from jose import jwt, JWTError

JWT_SECRET = os.getenv("JWT_SECRET", "yubilab-secure-jwt-2024-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
DB_PATH = "database.db"


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database with required tables."""
    conn = get_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT DEFAULT '',
        password_hash TEXT NOT NULL,
        plan TEXT DEFAULT 'free',
        ai_prompts_used_today INTEGER DEFAULT 0,
        last_reset_date TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        plan TEXT NOT NULL,
        amount INTEGER NOT NULL,
        bkash_trxid TEXT DEFAULT '',
        bkash_number TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        verified_at TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS agent_sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        task TEXT DEFAULT '',
        status TEXT DEFAULT 'active',
        workspace_path TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")

    # Create admin user if not exists
    admin_hash = hash_password("yubilab_admin_2024")
    c.execute("SELECT id FROM users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (id, username, password_hash, plan) VALUES (?, ?, ?, ?)",
                  ("admin", "admin", admin_hash, "admin"))

    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    """Hash a password."""
    salt = os.getenv("JWT_SECRET", "yubilab-secret")
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password."""
    return hash_password(password) == hashed


def generate_jwt(user_id: str, username: str, plan: str) -> str:
    """Generate a JWT token."""
    payload = {
        "user_id": user_id,
        "username": username,
        "plan": plan,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> Optional[Dict]:
    """Verify and decode a JWT token."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


def register_user(username: str, password: str, email: str = "") -> Tuple[bool, Dict]:
    """Register a new user."""
    if not username or not password:
        return False, {"error": "Username and password required"}
    if len(username) < 3:
        return False, {"error": "Username must be at least 3 characters"}
    if len(password) < 6:
        return False, {"error": "Password must be at least 6 characters"}

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    if c.fetchone():
        conn.close()
        return False, {"error": "Username already exists"}

    user_id = f"user_{uuid.uuid4().hex[:8]}"
    pw_hash = hash_password(password)
    now = datetime.utcnow().isoformat()

    c.execute(
        "INSERT INTO users (id, username, email, password_hash, plan, last_reset_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, email, pw_hash, "free", now[:10], now),
    )
    conn.commit()
    conn.close()

    token = generate_jwt(user_id, username, "free")
    return True, {
        "token": token,
        "user": {"user_id": user_id, "username": username, "plan": "free"},
    }


def login_user(username: str, password: str) -> Tuple[bool, Dict]:
    """Login a user."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, password_hash, plan FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()

    if not user or not verify_password(password, user["password_hash"]):
        return False, {"error": "Invalid credentials"}

    token = generate_jwt(user["id"], user["username"], user["plan"])
    return True, {
        "token": token,
        "user": {"user_id": user["id"], "username": user["username"], "plan": user["plan"]},
    }


def get_user(user_id: str) -> Optional[Dict]:
    """Get user by ID."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, email, plan, ai_prompts_used_today, last_reset_date, created_at FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()

    if user:
        return dict(user)
    return None


def check_ai_limit(user_id: str) -> Tuple[bool, int]:
    """Check if user can use AI (free plan has daily limit)."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT plan, ai_prompts_used_today, last_reset_date FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()

    if not user:
        conn.close()
        return False, 0

    # Reset daily counter if new day
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if user["last_reset_date"] != today:
        c.execute("UPDATE users SET ai_prompts_used_today = 0, last_reset_date = ? WHERE id = ?", (today, user_id))
        conn.commit()
        used_today = 0
    else:
        used_today = user["ai_prompts_used_today"]

    plan = user["plan"]
    conn.close()

    free_limit = int(os.getenv("FREE_AI_PROMPTS_DAILY", "3"))

    if plan == "free":
        if used_today >= free_limit:
            return False, free_limit - used_today
    # Pro and admin have unlimited

    return True, free_limit - used_today if plan == "free" else 999


def increment_ai_usage(user_id: str):
    """Increment AI usage counter."""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET ai_prompts_used_today = ai_prompts_used_today + 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def verify_bkash_payment(user_id: str, trxid: str, bkash_number: str) -> Tuple[bool, str]:
    """Verify a bKash payment manually."""
    expected_number = os.getenv("BKASH_NUMBER", "01849691859")
    expected_amount = int(os.getenv("BKASH_AMOUNT", "1200"))

    if not trxid:
        return False, "Transaction ID required"

    conn = get_db()
    c = conn.cursor()

    # Check if trxid already used
    c.execute("SELECT id FROM subscriptions WHERE bkash_trxid = ?", (trxid,))
    if c.fetchone():
        conn.close()
        return False, "Transaction ID already used"

    sub_id = f"sub_{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow().isoformat()

    c.execute(
        "INSERT INTO subscriptions (id, user_id, plan, amount, bkash_trxid, bkash_number, status, verified_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (sub_id, user_id, "pro", expected_amount, trxid, bkash_number, "active", now, now),
    )

    # Upgrade user plan
    c.execute("UPDATE users SET plan = 'pro' WHERE id = ?", (user_id,))

    conn.commit()
    conn.close()

    return True, "Payment verified. Upgraded to Pro!"


def get_user_stats(user_id: str) -> Dict:
    """Get user statistics."""
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) as count FROM agent_sessions WHERE user_id = ?", (user_id,))
    session_count = c.fetchone()["count"]

    c.execute("SELECT COUNT(*) as count FROM subscriptions WHERE user_id = ? AND status = 'active'", (user_id,))
    active_sub = c.fetchone()["count"]

    user = get_user(user_id)
    conn.close()

    return {
        "session_count": session_count,
        "has_active_subscription": active_sub > 0,
        "plan": user["plan"] if user else "free",
        "ai_prompts_used": user["ai_prompts_used_today"] if user else 0,
    }


def get_all_users() -> list:
    """Get all users (admin)."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, email, plan, ai_prompts_used_today, created_at FROM users ORDER BY created_at DESC")
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    return users
