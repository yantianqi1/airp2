"""DB-backed novels service + per-novel filesystem paths."""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .db import Database, utc_now
from .storage_layout import StorageLayout


_SLUG_SAFE_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = _SLUG_SAFE_RE.sub("-", value)
    value = value.strip("-")
    return value


def _validate_novel_id(novel_id: str) -> str:
    novel_id = str(novel_id or "").strip()
    if not novel_id:
        raise KeyError("novel_id is empty")
    if "/" in novel_id or "\\" in novel_id or ".." in novel_id:
        raise KeyError("invalid novel_id")
    return novel_id


def _json_load(value: str) -> Dict[str, Any]:
    try:
        data = json.loads(value or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _json_dump(value: Any) -> str:
    try:
        return json.dumps(value or {}, ensure_ascii=False)
    except Exception:
        return "{}"


@dataclass(frozen=True)
class NovelRecord:
    novel_id: str
    owner_user_id: str
    title: str
    visibility: str
    status: str
    created_at: str
    updated_at: str
    source: Dict[str, Any]
    stats: Dict[str, Any]
    last_job_id: str
    last_error: str

    def to_entry_dict(self) -> Dict[str, Any]:
        return {
            "novel_id": self.novel_id,
            "title": self.title,
            "visibility": self.visibility,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source": self.source,
            "stats": self.stats,
            "last_job_id": self.last_job_id,
            "last_error": self.last_error,
        }

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "novel_id": self.novel_id,
            "title": self.title,
            "status": self.status,
            "updated_at": self.updated_at,
        }


class NovelsService:
    def __init__(self, db: Database, layout: StorageLayout):
        self.db = db
        self.layout = layout

    def _row_to_record(self, row: Dict[str, Any]) -> NovelRecord:
        return NovelRecord(
            novel_id=str(row.get("id", "")),
            owner_user_id=str(row.get("owner_user_id", "")),
            title=str(row.get("title", "")),
            visibility=str(row.get("visibility", "private")),
            status=str(row.get("status", "created")),
            created_at=str(row.get("created_at", "")),
            updated_at=str(row.get("updated_at", "")),
            source=_json_load(str(row.get("source_meta", "{}"))),
            stats=_json_load(str(row.get("stats", "{}"))),
            last_job_id=str(row.get("last_job_id", "")),
            last_error=str(row.get("last_error", "")),
        )

    def get(self, novel_id: str) -> NovelRecord:
        novel_id = _validate_novel_id(novel_id)
        row = self.db.query_one("SELECT * FROM novels WHERE id = ?;", (novel_id,))
        if not row:
            raise KeyError(f"novel not found: {novel_id}")
        record = self._row_to_record(row)
        if record.status == "deleted":
            raise KeyError(f"novel not found: {novel_id}")
        return record

    def list_by_owner(self, owner_user_id: str) -> List[Dict[str, Any]]:
        rows = self.db.query_all(
            "SELECT * FROM novels WHERE owner_user_id = ? AND status != 'deleted' ORDER BY updated_at DESC;",
            (str(owner_user_id),),
        )
        return [self._row_to_record(row).to_entry_dict() for row in rows]

    def list_public(self) -> List[Dict[str, Any]]:
        rows = self.db.query_all(
            """
            SELECT * FROM novels
            WHERE visibility = 'public' AND status != 'deleted'
            ORDER BY updated_at DESC;
            """
        )
        return [self._row_to_record(row).to_public_dict() for row in rows]

    def create(self, owner_user_id: str, title: str = "") -> Dict[str, Any]:
        owner_user_id = str(owner_user_id or "").strip()
        if not owner_user_id:
            raise ValueError("owner_user_id is empty")

        title = str(title or "").strip()
        slug = _slugify(title) or "novel"

        # Allocate globally unique id.
        for _ in range(50):
            suffix = secrets.token_hex(3)
            novel_id = f"{slug}-{suffix}"
            existing = self.db.query_one("SELECT id FROM novels WHERE id = ?;", (novel_id,))
            if not existing:
                break
        else:
            raise RuntimeError("failed to allocate novel_id after many attempts")

        now = utc_now()
        self.db.execute(
            """
            INSERT INTO novels (id, owner_user_id, title, visibility, status, created_at, updated_at, source_meta, stats, last_job_id, last_error)
            VALUES (?,?,?,?,?,?,?,?,?,?,?);
            """,
            (
                novel_id,
                owner_user_id,
                title,
                "private",
                "created",
                now,
                now,
                "{}",
                "{}",
                "",
                "",
            ),
        )

        self.layout.ensure_novel_dirs(owner_user_id, novel_id)
        return self.get(novel_id).to_entry_dict()

    def assert_owner(self, owner_user_id: str, novel_id: str) -> NovelRecord:
        record = self.get(novel_id)
        if str(record.owner_user_id) != str(owner_user_id):
            raise PermissionError("forbidden")
        return record

    def can_read(self, *, actor_user_id: Optional[str], novel_id: str) -> bool:
        record = self.get(novel_id)
        if actor_user_id and str(actor_user_id) == str(record.owner_user_id):
            return True
        return record.visibility == "public"

    def paths(self, novel_id: str) -> Dict[str, str]:
        record = self.get(novel_id)
        return self.layout.user_novel_paths(record.owner_user_id, record.novel_id)

    def update(self, owner_user_id: str, novel_id: str, *, title: Optional[str] = None, visibility: Optional[str] = None) -> Dict[str, Any]:
        record = self.assert_owner(owner_user_id, novel_id)

        fields: Dict[str, Any] = {}
        if title is not None:
            fields["title"] = str(title or "").strip()
        if visibility is not None:
            v = str(visibility or "").strip().lower()
            if v not in {"private", "public"}:
                raise ValueError("visibility must be 'private' or 'public'")
            fields["visibility"] = v

        if not fields:
            return record.to_entry_dict()

        fields["updated_at"] = utc_now()
        assignments = ", ".join([f"{k} = ?" for k in fields.keys()])
        params = list(fields.values()) + [record.novel_id]
        self.db.execute(f"UPDATE novels SET {assignments} WHERE id = ?;", params)
        return self.get(record.novel_id).to_entry_dict()

    def update_source_meta(self, owner_user_id: str, novel_id: str, source_meta: Dict[str, Any]) -> Dict[str, Any]:
        record = self.assert_owner(owner_user_id, novel_id)
        self.db.execute(
            "UPDATE novels SET source_meta = ?, status = ?, updated_at = ?, last_error = '' WHERE id = ?;",
            (_json_dump(source_meta), "uploaded", utc_now(), record.novel_id),
        )
        return self.get(record.novel_id).to_entry_dict()

    def set_processing(self, novel_id: str, job_id: str) -> None:
        self.db.execute(
            "UPDATE novels SET status = 'processing', last_job_id = ?, updated_at = ? WHERE id = ?;",
            (str(job_id or ""), utc_now(), _validate_novel_id(novel_id)),
        )

    def set_ready(self, novel_id: str, job_id: str, stats: Dict[str, Any]) -> None:
        self.db.execute(
            "UPDATE novels SET status = 'ready', last_job_id = ?, stats = ?, updated_at = ?, last_error = '' WHERE id = ?;",
            (str(job_id or ""), _json_dump(stats), utc_now(), _validate_novel_id(novel_id)),
        )

    def set_failed(self, novel_id: str, job_id: str, error: str) -> None:
        self.db.execute(
            "UPDATE novels SET status = 'failed', last_job_id = ?, updated_at = ?, last_error = ? WHERE id = ?;",
            (str(job_id or ""), utc_now(), str(error or ""), _validate_novel_id(novel_id)),
        )

    def delete(self, owner_user_id: str, novel_id: str, *, delete_vector_db: bool = False) -> None:
        record = self.assert_owner(owner_user_id, novel_id)
        # Soft delete in DB to keep job history consistent.
        self.db.execute(
            "UPDATE novels SET status = 'deleted', updated_at = ? WHERE id = ?;",
            (utc_now(), record.novel_id),
        )
        self.layout.delete_user_novel(record.owner_user_id, record.novel_id, delete_vector_db=bool(delete_vector_db))

