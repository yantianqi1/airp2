"""Session memory and persistence for RP conversations."""
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .helpers import normalize_entities


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SessionState:
    """Persistent state for one RP session."""

    session_id: str
    max_unlocked_chapter: int = 0
    active_characters: List[str] = field(default_factory=list)
    current_scene: str = ""
    long_term_summary: str = ""
    turns: List[Dict[str, Any]] = field(default_factory=list)
    recent_entities: List[str] = field(default_factory=list)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        return cls(
            session_id=data.get("session_id", ""),
            max_unlocked_chapter=int(data.get("max_unlocked_chapter", 0) or 0),
            active_characters=list(data.get("active_characters", [])),
            current_scene=str(data.get("current_scene", "")),
            long_term_summary=str(data.get("long_term_summary", "")),
            turns=list(data.get("turns", [])),
            recent_entities=list(data.get("recent_entities", [])),
            updated_at=str(data.get("updated_at", _utc_now())),
        )


class SessionStateStore:
    """Filesystem-backed session state store."""

    def __init__(self, base_dir: str = "data/sessions"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _path(self, session_id: str) -> str:
        safe_id = str(session_id).replace("/", "_").replace("\\", "_")
        return os.path.join(self.base_dir, f"{safe_id}.json")

    def load(self, session_id: str, default_unlocked: int = 0) -> SessionState:
        path = self._path(session_id)
        if not os.path.exists(path):
            return SessionState(session_id=session_id, max_unlocked_chapter=default_unlocked)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SessionState.from_dict(data)

    def save(self, state: SessionState) -> None:
        state.updated_at = _utc_now()
        path = self._path(state.session_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)

    def append_turn(self, state: SessionState, role: str, content: str) -> None:
        state.turns.append({"role": role, "content": content, "ts": _utc_now()})
        # Keep short memory bounded for prompt cost control.
        if len(state.turns) > 20:
            state.turns = state.turns[-20:]

    def apply_runtime_updates(
        self,
        state: SessionState,
        unlocked_chapter: Optional[int] = None,
        active_characters: Optional[List[str]] = None,
        current_scene: Optional[str] = None,
    ) -> None:
        if unlocked_chapter is not None:
            state.max_unlocked_chapter = max(int(unlocked_chapter), state.max_unlocked_chapter)

        if active_characters is not None:
            state.active_characters = normalize_entities(active_characters)

        if current_scene is not None:
            state.current_scene = str(current_scene)

    def remember_entities(self, state: SessionState, entities: List[str]) -> None:
        merged = normalize_entities(list(state.recent_entities) + list(entities or []))
        state.recent_entities = merged[-30:]
