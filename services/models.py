"""Data models shared by RP query services."""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class QueryConstraints:
    """Runtime constraints inferred from user/session context."""

    unlocked_chapter: Optional[int] = None
    active_characters: List[str] = field(default_factory=list)
    location_hints: List[str] = field(default_factory=list)


@dataclass
class QueryUnderstandingResult:
    """Parsed query result."""

    intent: str
    normalized_query: str
    entities: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    event_keywords: List[str] = field(default_factory=list)
    constraints: QueryConstraints = field(default_factory=QueryConstraints)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data


@dataclass
class RetrievalCandidate:
    """Unified candidate format across retrievers."""

    source_type: str
    source_id: str
    text: str
    chapter: Optional[str] = None
    chapter_no: Optional[int] = None
    scene_index: Optional[int] = None
    chapter_title: str = ""
    scene_summary: str = ""
    event_summary: str = ""
    characters: List[str] = field(default_factory=list)
    location: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    semantic_score: float = 0.0
    entity_overlap: float = 0.0
    narrative_fit: float = 0.0
    recency_in_session: float = 0.0
    final_score: float = 0.0

    def dedupe_key(self) -> str:
        if self.source_type == "scene":
            return f"scene:{self.chapter}:{self.scene_index}"
        return f"{self.source_type}:{self.source_id}"

    def citation(self) -> Dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "chapter": self.chapter,
            "scene_index": self.scene_index,
            "chapter_title": self.chapter_title,
            "excerpt": self.metadata.get("excerpt", ""),
        }

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data


@dataclass
class WorldbookContext:
    """Final context payload consumed by RP response generation."""

    facts: List[Dict[str, Any]] = field(default_factory=list)
    character_state: List[Dict[str, Any]] = field(default_factory=list)
    timeline_notes: List[Dict[str, Any]] = field(default_factory=list)
    forbidden: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
