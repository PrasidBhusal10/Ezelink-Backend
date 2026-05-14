
import os
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv

import database

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production-use-a-long-random-string")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

def hash_password(password: str) -> str:
    """Hash a password with a salt using SHA-256."""
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100_000)
    return salt.hex() + ':' + key.hex()


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        salt_hex, key_hex = stored_hash.split(':')
        salt = bytes.fromhex(salt_hex)
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100_000)
        return hmac.compare_digest(key.hex(), key_hex)
    except Exception:
        return False
def create_access_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired — please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_token(token)
    return {
        "user_id": int(payload["sub"]),
        "email": payload["email"],
    }


def get_optional_user(token: Optional[str] = Depends(OAuth2PasswordBearer(
    tokenUrl="/auth/login", auto_error=False
))) -> Optional[dict]:
    if not token:
        return None
    try:
        payload = decode_token(token)
        return {"user_id": int(payload["sub"]), "email": payload["email"]}
    except HTTPException:
        return None
def create_user(email: str, password: str) -> dict:
    """Insert a new user into the DB. Returns the created user."""
    conn = database.get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO users (email, password_hash)
            VALUES (%s, %s)
            RETURNING id, email, api_key, created_at
        """, (email.lower().strip(), hash_password(password)))

        row = cur.fetchone()
        conn.commit()
        return {
            "user_id": row[0],
            "email": row[1],
            "api_key": row[2],
            "created_at": row[3],
        }
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Email already registered")
        raise
    finally:
        cur.close()
        conn.close()


def get_user_by_email(email: str) -> Optional[dict]:
    """Fetch a user by email for login verification."""
    conn = database.get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, email, password_hash, api_key
        FROM users WHERE email = %s
    """, (email.lower().strip(),))

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return None
    return {
        "user_id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "api_key": row[3],
    }