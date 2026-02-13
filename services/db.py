"""SQLite database helpers (MVP: schema init + small query helpers).

We keep this dependency-free (stdlib sqlite3) to simplify deployment.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Database:
    path: str

    def connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
        except Exception:
            pass
        return conn

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        with self.conn() as conn:
            conn.execute(sql, tuple(params))

    def execute_many(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        with self.conn() as conn:
            conn.executemany(sql, [tuple(row) for row in rows])

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
        with self.conn() as conn:
            cur = conn.execute(sql, tuple(params))
            row = cur.fetchone()
            return dict(row) if row else None

    def query_all(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        with self.conn() as conn:
            cur = conn.execute(sql, tuple(params))
            return [dict(row) for row in cur.fetchall()]

    def init_schema(self) -> None:
        # Keep schema idempotent and easy to evolve (no external migrator).
        statements: Tuple[str, ...] = (
            """
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY,
              username TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
              id TEXT PRIMARY KEY,
              token_hash TEXT NOT NULL UNIQUE,
              user_id TEXT,
              guest_id TEXT,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              revoked_at TEXT,
              last_seen_at TEXT,
              FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_guest_id ON auth_sessions(guest_id);",
            """
            CREATE TABLE IF NOT EXISTS novels (
              id TEXT PRIMARY KEY,
              owner_user_id TEXT NOT NULL,
              title TEXT NOT NULL DEFAULT '',
              visibility TEXT NOT NULL DEFAULT 'private',
              status TEXT NOT NULL DEFAULT 'created',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              source_meta TEXT NOT NULL DEFAULT '{}',
              stats TEXT NOT NULL DEFAULT '{}',
              last_job_id TEXT NOT NULL DEFAULT '',
              last_error TEXT NOT NULL DEFAULT '',
              FOREIGN KEY(owner_user_id) REFERENCES users(id)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_novels_owner_user_id ON novels(owner_user_id);",
            "CREATE INDEX IF NOT EXISTS idx_novels_visibility ON novels(visibility);",
            """
            CREATE TABLE IF NOT EXISTS pipeline_jobs (
              id TEXT PRIMARY KEY,
              novel_id TEXT NOT NULL,
              owner_user_id TEXT NOT NULL,
              spec TEXT NOT NULL DEFAULT '{}',
              status TEXT NOT NULL DEFAULT 'queued',
              current_step INTEGER,
              progress REAL NOT NULL DEFAULT 0.0,
              started_at TEXT NOT NULL DEFAULT '',
              finished_at TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              log_path TEXT NOT NULL DEFAULT '',
              error TEXT NOT NULL DEFAULT '',
              result TEXT NOT NULL DEFAULT '{}',
              FOREIGN KEY(novel_id) REFERENCES novels(id),
              FOREIGN KEY(owner_user_id) REFERENCES users(id)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_owner_user_id ON pipeline_jobs(owner_user_id);",
            "CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_novel_id ON pipeline_jobs(novel_id);",
        )
        with self.conn() as conn:
            for stmt in statements:
                conn.execute(stmt)

