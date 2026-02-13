"""Structured filter retrieval channel backed by payload indexes."""
from typing import Dict, List, Optional

from qdrant_client import QdrantClient, models

from ..helpers import parse_chapter_no, shorten_text
from ..models import RetrievalCandidate


class FilterRetriever:
    """Recall candidates using metadata filters (character/location/chapter)."""

    def __init__(self, config: Dict, qdrant_client: Optional[QdrantClient] = None):
        self.config = config
        self.collection_name = config["vector_db"]["collection_name"]
        self.vector_db_path = config["paths"]["vector_db_path"]
        self.qdrant_client = qdrant_client or QdrantClient(path=self.vector_db_path)

    def query(
        self,
        entities: List[str],
        locations: List[str],
        top_k: int = 20,
        unlocked_chapter: Optional[int] = None,
    ) -> List[RetrievalCandidate]:
        query_filter = self._build_filter(entities, locations)
        if query_filter is None:
            return []

        points, _ = self.qdrant_client.scroll(
            collection_name=self.collection_name,
            scroll_filter=query_filter,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )

        candidates = []
        for point in points:
            payload = dict(point.payload or {})
            chapter = payload.get("chapter")
            chapter_no = payload.get("chapter_no")
            if chapter_no is None:
                chapter_no = parse_chapter_no(chapter)

            if unlocked_chapter is not None and chapter_no is not None and chapter_no > unlocked_chapter:
                continue

            candidate = RetrievalCandidate(
                source_type="scene",
                source_id=str(getattr(point, "id", "")),
                text=payload.get("text", ""),
                chapter=chapter,
                chapter_no=chapter_no,
                scene_index=payload.get("scene_index"),
                chapter_title=payload.get("chapter_title", ""),
                scene_summary=payload.get("scene_summary", ""),
                event_summary=payload.get("event_summary", ""),
                characters=payload.get("characters", []) or [],
                location=payload.get("location", ""),
                metadata={"excerpt": shorten_text(payload.get("text", ""), 180), "payload": payload},
                semantic_score=0.55,
            )
            candidates.append(candidate)

        return candidates

    def _build_filter(self, entities: List[str], locations: List[str]):
        should_conditions = []

        if entities:
            should_conditions.append(
                models.FieldCondition(
                    key="characters",
                    match=models.MatchAny(any=list(entities)),
                )
            )

        if locations:
            should_conditions.append(
                models.FieldCondition(
                    key="location",
                    match=models.MatchAny(any=list(locations)),
                )
            )

        if not should_conditions:
            return None

        return models.Filter(should=should_conditions)
