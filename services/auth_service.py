"""Authentication and session management (cookie-based).

This is an MVP implementation using stdlib PBKDF2 for password hashing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from .db import Database, utc_now


USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")


def normalize_username(username: str) -> str:
    return str(username or "").strip().lower()


def validate_username(username: str) -> None:
    if not USERNAME_RE.match(username):
        raise ValueError("username must match ^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")


def validate_password(password: str) -> None:
    pwd = str(password or "")
    if len(pwd) < 8:
        raise ValueError("password too short (min 8)")
    if len(pwd) > 256:
        raise ValueError("password too long")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padded = str(data or "")
    padded += "=" * (-len(padded) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def hash_password(password: str, iterations: int = 360_000) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iter_s, salt_s, hash_s = str(encoded).split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iter_s)
        salt = _b64decode(salt_s)
        expected = _b64decode(hash_s)
    except Exception:
        return False

    dk = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk, expected)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Actor:
    type: str  # "user" | "guest"
    user_id: Optional[str] = None
    username: Optional[str] = None
    guest_id: Optional[str] = None

    @property
    def is_user(self) -> bool:
        return self.type == "user" and bool(self.user_id)

    @property
    def is_guest(self) -> bool:
        return self.type == "guest"


class AuthService:
    def __init__(
        self,
        db: Database,
        cookie_name: str = "airp_sid",
        user_session_days: int = 30,
        guest_session_days: int = 30,
    ):
        self.db = db
        self.cookie_name = cookie_name
        self.user_session_days = max(1, int(user_session_days or 30))
        self.guest_session_days = max(1, int(guest_session_days or 30))

    def register(self, username: str, password: str) -> Dict[str, Any]:
        normalized = normalize_username(username)
        validate_username(normalized)
        validate_password(password)

        user_id = uuid.uuid4().hex
        pwd_hash = hash_password(password)
        created_at = utc_now()

        try:
            self.db.execute(
                "INSERT INTO users (id, username, password_hash, created_at) VALUES (?,?,?,?);",
                (user_id, normalized, pwd_hash, created_at),
            )
        except Exception as exc:
            raise ValueError("username already exists") from exc

        return {"id": user_id, "username": normalized, "created_at": created_at}

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        normalized = normalize_username(username)
        row = self.db.query_one("SELECT * FROM users WHERE username = ?;", (normalized,))
        if not row:
            return None
        if not verify_password(password, row.get("password_hash", "")):
            return None
        return {"id": row["id"], "username": row["username"], "created_at": row["created_at"]}

    def create_user_session(self, user_id: str) -> Tuple[str, Dict[str, Any]]:
        token = secrets.token_urlsafe(32)
        token_hash = _sha256_hex(token)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=self.user_session_days)
        session_id = uuid.uuid4().hex
        self.db.execute(
            """
            INSERT INTO auth_sessions (id, token_hash, user_id, guest_id, created_at, expires_at, revoked_at, last_seen_at)
            VALUES (?,?,?,?,?,?,NULL,?);
            """,
            (
                session_id,
                token_hash,
                str(user_id),
                None,
                now.isoformat(),
                expires.isoformat(),
                now.isoformat(),
            ),
        )
        return token, {
            "id": session_id,
            "user_id": str(user_id),
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }

    def create_guest_session(self) -> Tuple[str, Dict[str, Any]]:
        token = secrets.token_urlsafe(32)
        token_hash = _sha256_hex(token)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=self.guest_session_days)
        session_id = uuid.uuid4().hex
        guest_id = uuid.uuid4().hex
        self.db.execute(
            """
            INSERT INTO auth_sessions (id, token_hash, user_id, guest_id, created_at, expires_at, revoked_at, last_seen_at)
            VALUES (?,?,?,?,?,?,NULL,?);
            """,
            (
                session_id,
                token_hash,
                None,
                guest_id,
                now.isoformat(),
                expires.isoformat(),
                now.isoformat(),
            ),
        )
        return token, {
            "id": session_id,
            "guest_id": guest_id,
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }

    def revoke_session(self, token: str) -> None:
        token_hash = _sha256_hex(token)
        self.db.execute(
            "UPDATE auth_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL;",
            (utc_now(), token_hash),
        )

    def actor_from_token(self, token: Optional[str]) -> Optional[Actor]:
        if not token:
            return None
        token_hash = _sha256_hex(token)
        row = self.db.query_one(
            """
            SELECT s.user_id, s.guest_id, s.expires_at, s.revoked_at, u.username
            FROM auth_sessions s
            LEFT JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?;
            """,
            (token_hash,),
        )
        if not row:
            return None
        if row.get("revoked_at"):
            return None
        try:
            expires_at = datetime.fromisoformat(str(row.get("expires_at") or ""))
        except Exception:
            return None
        if expires_at <= datetime.now(timezone.utc):
            return None

        user_id = row.get("user_id")
        if user_id:
            return Actor(type="user", user_id=str(user_id), username=str(row.get("username") or ""))
        guest_id = row.get("guest_id")
        if guest_id:
            return Actor(type="guest", guest_id=str(guest_id))
        return None

    def touch_session(self, token: Optional[str]) -> None:
        if not token:
            return
        token_hash = _sha256_hex(token)
        try:
            self.db.execute(
                "UPDATE auth_sessions SET last_seen_at = ? WHERE token_hash = ?;",
                (utc_now(), token_hash),
            )
        except Exception:
            pass

