"""Filesystem layout helpers for user/guest scoped storage."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Dict, Optional


def _validate_id(value: str, name: str) -> str:
    value = str(value or "").strip()
    if not value:
        raise ValueError(f"{name} is empty")
    if "/" in value or "\\" in value or ".." in value:
        raise ValueError(f"invalid {name}")
    return value


def _is_within_dir(path: str, root: str) -> bool:
    root_abs = os.path.abspath(root)
    path_abs = os.path.abspath(path)
    try:
        common = os.path.commonpath([root_abs, path_abs])
    except ValueError:
        return False
    return common == root_abs


@dataclass(frozen=True)
class StorageLayout:
    data_root: str
    vector_db_root: str
    logs_root: str

    def user_root(self, user_id: str) -> str:
        user_id = _validate_id(user_id, "user_id")
        return os.path.join(self.data_root, "users", user_id)

    def guest_root(self, guest_id: str) -> str:
        guest_id = _validate_id(guest_id, "guest_id")
        return os.path.join(self.data_root, "guests", guest_id)

    def user_novel_paths(self, owner_user_id: str, novel_id: str) -> Dict[str, str]:
        owner_user_id = _validate_id(owner_user_id, "owner_user_id")
        novel_id = _validate_id(novel_id, "novel_id")

        novel_dir = os.path.join(self.user_root(owner_user_id), "novels", novel_id)
        input_dir = os.path.join(novel_dir, "input")
        chapters_dir = os.path.join(novel_dir, "chapters")
        scenes_dir = os.path.join(novel_dir, "scenes")
        annotated_dir = os.path.join(novel_dir, "annotated")
        profiles_dir = os.path.join(novel_dir, "profiles")

        vector_db_path = os.path.join(self.vector_db_root, "users", owner_user_id, novel_id)
        log_dir = os.path.join(self.logs_root, "users", owner_user_id, "novels", novel_id)

        return {
            "novel_dir": novel_dir,
            "input_dir": input_dir,
            "source_file": os.path.join(input_dir, "source.txt"),
            "chapters_dir": chapters_dir,
            "scenes_dir": scenes_dir,
            "annotated_dir": annotated_dir,
            "profiles_dir": profiles_dir,
            "vector_db_path": vector_db_path,
            "log_dir": log_dir,
        }

    def sessions_scope_dir(self, *, user_id: Optional[str] = None, guest_id: Optional[str] = None, novel_id: Optional[str] = None) -> str:
        if user_id:
            base = os.path.join(self.user_root(user_id), "sessions")
        else:
            # guest_id must exist for stable session storage.
            gid = _validate_id(guest_id or "", "guest_id")
            base = os.path.join(self.guest_root(gid), "sessions")

        if novel_id:
            safe_novel = _validate_id(novel_id, "novel_id")
            return os.path.join(base, "novels", safe_novel)
        return os.path.join(base, "global")

    def ensure_novel_dirs(self, owner_user_id: str, novel_id: str) -> Dict[str, str]:
        paths = self.user_novel_paths(owner_user_id, novel_id)
        for key in ("input_dir", "chapters_dir", "scenes_dir", "annotated_dir", "profiles_dir", "vector_db_path", "log_dir"):
            os.makedirs(paths[key], exist_ok=True)
        return paths

    def delete_user_novel(self, owner_user_id: str, novel_id: str, *, delete_vector_db: bool = False) -> None:
        paths = self.user_novel_paths(owner_user_id, novel_id)
        novel_dir = paths["novel_dir"]
        vdb_dir = paths["vector_db_path"]

        # Delete workspace.
        if os.path.isdir(novel_dir) and _is_within_dir(novel_dir, self.user_root(owner_user_id)):
            shutil.rmtree(novel_dir, ignore_errors=True)

        if delete_vector_db and os.path.isdir(vdb_dir) and _is_within_dir(vdb_dir, os.path.join(self.vector_db_root, "users", owner_user_id)):
            shutil.rmtree(vdb_dir, ignore_errors=True)

