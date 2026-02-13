"""Semantic retrieval channel backed by Qdrant vectors."""
from typing import Dict, List, Optional

from qdrant_client import QdrantClient, models

from utils.embedding_client import EmbeddingClient

from ..helpers import parse_chapter_no, shorten_text
from ..models import RetrievalCandidate


class VectorRetriever:
    """Run semantic search and normalize result payload."""

    def __init__(
        self,
        config: Dict,
        qdrant_client: Optional[QdrantClient] = None,
        embedding_client: Optional[EmbeddingClient] = None,
    ):
        self.config = config
        self.collection_name = config["vector_db"]["collection_name"]
        self.vector_db_path = config["paths"]["vector_db_path"]
        self.qdrant_client = qdrant_client or QdrantClient(path=self.vector_db_path)
        self.embedding_client = embedding_client or EmbeddingClient(config)

    def query(
        self,
        query_text: str,
        top_k: int = 30,
        active_characters: Optional[List[str]] = None,
        location_hints: Optional[List[str]] = None,
        unlocked_chapter: Optional[int] = None,
    ) -> List[RetrievalCandidate]:
        if not query_text:
            return []

        query_vector = self.embedding_client.embed([query_text])[0]
        query_filter = self._build_filter(active_characters, location_hints)

        kwargs = {
            "collection_name": self.collection_name,
            "query_vector": query_vector,
            "limit": top_k,
            "with_payload": True,
            "with_vectors": False,
        }
        if query_filter is not None:
            kwargs["query_filter"] = query_filter

        results = self._search_points(kwargs)

        candidates: List[RetrievalCandidate] = []
        for result in results:
            payload = dict(result.payload or {})
            chapter = payload.get("chapter")
            chapter_no = payload.get("chapter_no")
            if chapter_no is None:
                chapter_no = parse_chapter_no(chapter)

            if unlocked_chapter is not None and chapter_no is not None and chapter_no > unlocked_chapter:
                continue

            score = float(getattr(result, "score", 0.0) or 0.0)
            semantic_score = self._normalize_semantic_score(score)

            candidate = RetrievalCandidate(
                source_type="scene",
                source_id=str(getattr(result, "id", "")),
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
                semantic_score=semantic_score,
            )
            candidates.append(candidate)

        return candidates

    def _search_points(self, kwargs: Dict) -> List:
        """Support both legacy `search` and modern `query_points` APIs."""
        if hasattr(self.qdrant_client, "search"):
            return self.qdrant_client.search(**kwargs)

        query_kwargs = {
            "collection_name": kwargs["collection_name"],
            "query": kwargs["query_vector"],
            "limit": kwargs["limit"],
            "with_payload": kwargs["with_payload"],
            "with_vectors": kwargs["with_vectors"],
        }
        if "query_filter" in kwargs:
            query_kwargs["query_filter"] = kwargs["query_filter"]

        response = self.qdrant_client.query_points(**query_kwargs)
        return list(getattr(response, "points", []) or [])

    def _build_filter(
        self,
        active_characters: Optional[List[str]],
        location_hints: Optional[List[str]],
    ):
        should_conditions = []

        if active_characters:
            should_conditions.append(
                models.FieldCondition(
                    key="characters",
                    match=models.MatchAny(any=list(active_characters)),
                )
            )

        if location_hints:
            should_conditions.append(
                models.FieldCondition(
                    key="location",
                    match=models.MatchAny(any=list(location_hints)),
                )
            )

        if not should_conditions:
            return None

        return models.Filter(should=should_conditions)

    def _normalize_semantic_score(self, raw_score: float) -> float:
        if raw_score < -1.0:
            return 0.0
        if raw_score <= 1.0:
            return (raw_score + 1.0) / 2.0
        return min(raw_score, 1.0)
