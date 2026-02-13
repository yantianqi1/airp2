#!/usr/bin/env python3
"""Migrate legacy single-tenant filesystem registry to the new multi-user layout.

Legacy (old):
- data/novels/index.json
- data/novels/<novel_id>/
- vector_db/<novel_id>/
- logs/novels/<novel_id>/

New (multi-user):
- SQLite: data/airp2.sqlite3 (configurable via paths.db_path)
- data/users/<user_id>/novels/<novel_id>/
- vector_db/users/<user_id>/<novel_id>/
- logs/users/<user_id>/novels/<novel_id>/

Default behavior is non-destructive (copy). Use --move to move directories.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

import yaml

from services.auth_service import AuthService, normalize_username
from services.db import Database, utc_now
from services.storage_layout import StorageLayout


def _derive_data_root(config: Dict[str, Any]) -> str:
    paths = config.get("paths", {}) or {}
    for key in ("profiles_dir", "chapters_dir", "annotated_dir", "scenes_dir"):
        value = paths.get(key)
        if value:
            return os.path.dirname(str(value).rstrip("/\\"))
    return "data"


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _copy_or_move(src: str, dst: str, move: bool) -> None:
    if not os.path.exists(src):
        return
    _ensure_dir(os.path.dirname(dst))
    if os.path.exists(dst):
        # Keep idempotent: do not overwrite existing target.
        return
    if move:
        shutil.move(src, dst)
    else:
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def _create_or_get_user(db: Database, auth: AuthService, username: str, password: Optional[str]) -> Tuple[str, str]:
    normalized = normalize_username(username)
    row = db.query_one("SELECT id, username FROM users WHERE username = ?;", (normalized,))
    if row:
        return str(row["id"]), str(row["username"])
    if not password:
        # Generate a one-time random password for the migration-created user.
        password = os.urandom(16).hex()
        print(f"[migrate] created user password (SAVE THIS): {password}", file=sys.stderr)
    user = auth.register(username=normalized, password=password)
    return str(user["id"]), str(user["username"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy novels registry to multi-user layout")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--legacy-index", default="", help="Override legacy index.json path")
    parser.add_argument("--username", default="legacy_admin", help="Owner username for migrated novels")
    parser.add_argument("--password", default="", help="Password for newly created user (optional)")
    parser.add_argument("--visibility", default="private", choices=["private", "public"], help="Visibility for migrated novels")
    parser.add_argument("--move", action="store_true", help="Move directories instead of copying")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without changing disk/DB")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    data_root = _derive_data_root(config)
    vector_db_root = str(config.get("paths", {}).get("vector_db_path") or "vector_db")
    logs_root = str(config.get("paths", {}).get("log_dir") or "logs")
    db_path = str(config.get("paths", {}).get("db_path") or os.path.join(data_root, "airp2.sqlite3"))

    legacy_index = args.legacy_index or os.path.join(data_root, "novels", "index.json")
    if not os.path.exists(legacy_index):
        print(f"[migrate] legacy index not found: {legacy_index}", file=sys.stderr)
        return 2

    db = Database(path=db_path)
    if not args.dry_run:
        db.init_schema()
    auth = AuthService(db=db)
    layout = StorageLayout(data_root=data_root, vector_db_root=vector_db_root, logs_root=logs_root)

    if args.dry_run:
        user_id, username = ("dryrun-user", normalize_username(args.username))
    else:
        user_id, username = _create_or_get_user(db, auth, args.username, args.password or None)

    index = _load_json(legacy_index)
    novels: List[Dict[str, Any]] = list((index or {}).get("novels") or [])

    migrated = 0
    skipped = 0

    for item in novels:
        novel_id = str(item.get("novel_id", "") or "").strip()
        if not novel_id:
            continue

        # Skip if already exists.
        if not args.dry_run:
            exists = db.query_one("SELECT id FROM novels WHERE id = ?;", (novel_id,))
            if exists:
                skipped += 1
                continue

        title = str(item.get("title", "") or "")
        status = str(item.get("status", "created") or "created")
        created_at = str(item.get("created_at", utc_now()) or utc_now())
        updated_at = str(item.get("updated_at", utc_now()) or utc_now())
        source_meta = item.get("source") or {}
        stats = item.get("stats") or {}
        last_job_id = str(item.get("last_job_id", "") or "")
        last_error = str(item.get("last_error", "") or "")

        print(f"[migrate] novel {novel_id} -> user {username} ({user_id})", file=sys.stderr)

        if not args.dry_run:
            db.execute(
                """
                INSERT INTO novels (id, owner_user_id, title, visibility, status, created_at, updated_at, source_meta, stats, last_job_id, last_error)
                VALUES (?,?,?,?,?,?,?,?,?,?,?);
                """,
                (
                    novel_id,
                    user_id,
                    title,
                    args.visibility,
                    status,
                    created_at,
                    updated_at,
                    json.dumps(source_meta, ensure_ascii=False),
                    json.dumps(stats, ensure_ascii=False),
                    last_job_id,
                    last_error,
                ),
            )
            layout.ensure_novel_dirs(user_id, novel_id)

        # Copy/move workspace + vdb + logs.
        old_workspace = os.path.join(data_root, "novels", novel_id)
        new_workspace = os.path.join(layout.user_root(user_id), "novels", novel_id)
        old_vdb = os.path.join(vector_db_root, novel_id)
        new_vdb = os.path.join(vector_db_root, "users", user_id, novel_id)
        old_logs = os.path.join(logs_root, "novels", novel_id)
        new_logs = os.path.join(logs_root, "users", user_id, "novels", novel_id)

        if not args.dry_run:
            _copy_or_move(old_workspace, new_workspace, move=bool(args.move))
            _copy_or_move(old_vdb, new_vdb, move=bool(args.move))
            _copy_or_move(old_logs, new_logs, move=bool(args.move))

        migrated += 1

    print(f"[migrate] done: migrated={migrated} skipped={skipped} move={args.move} dry_run={args.dry_run}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

