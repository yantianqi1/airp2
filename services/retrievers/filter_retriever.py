"""Structured filter retrieval channel backed by payload indexes."""
import logging
from typing import Dict, List, Optional

from qdrant_client import QdrantClient, models

from ..helpers import parse_chapter_no, shorten_text
from ..models import RetrievalCandidate

logger = logging.getLogger(__name__)


class FilterRetriever:
    """Recall candidates using metadata filters (character/location/chapter)."""

    def __init__(self, config: Dict, qdrant_client: Optional[QdrantClient] = None):
        self.config = config
        self.collection_name = config["vector_db"]["collection_name"]
        self.vector_db_path = config["paths"]["vector_db_path"]
        self.qdrant_client = qdrant_client or QdrantClient(path=self.vector_db_path)
        self._owns_qdrant_client = qdrant_client is None

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

        points = self._scroll_with_retry(query_filter=query_filter, top_k=top_k)

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

    def _scroll_with_retry(self, query_filter, top_k: int):
        kwargs = {
            "collection_name": self.collection_name,
            "scroll_filter": query_filter,
            "limit": top_k,
            "with_payload": True,
            "with_vectors": False,
        }
        try:
            points, _ = self.qdrant_client.scroll(**kwargs)
            return points
        except ValueError as exc:
            if not self._is_collection_not_found(exc):
                raise

            logger.warning(
                "Qdrant collection '%s' not found during filter query: %s",
                self.collection_name,
                exc,
            )

            if self._reopen_qdrant_client():
                try:
                    points, _ = self.qdrant_client.scroll(**kwargs)
                    return points
                except ValueError as retry_exc:
                    if not self._is_collection_not_found(retry_exc):
                        raise
                    logger.warning(
                        "Qdrant collection '%s' still missing after reconnect; return empty filter results.",
                        self.collection_name,
                    )
                    return []

            logger.warning(
                "Skip filter retrieval because collection '%s' is unavailable.",
                self.collection_name,
            )
            return []

    @staticmethod
    def _is_collection_not_found(exc: ValueError) -> bool:
        message = str(exc).lower()
        return "collection" in message and "not found" in message

    def _reopen_qdrant_client(self) -> bool:
        if not self._owns_qdrant_client:
            return False

        try:
            self.qdrant_client = QdrantClient(path=self.vector_db_path)
            return True
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            logger.warning("Failed to reopen local Qdrant client: %s", exc)
            return False
