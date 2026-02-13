"""Orchestrate multi-channel retrieval and reranking."""
import logging
import time
from typing import Dict, List, Optional, Tuple

from .guardrails import Guardrails
from .models import QueryUnderstandingResult, RetrievalCandidate
from .reranker import RetrievalReranker
from .retrievers import FilterRetriever, ProfileRetriever, VectorRetriever
from .session_state import SessionState

logger = logging.getLogger(__name__)


class RetrievalOrchestrator:
    """Run vector/filter/profile retrieval and produce ranked evidence."""

    def __init__(
        self,
        config: Dict,
        vector_retriever: Optional[VectorRetriever] = None,
        filter_retriever: Optional[FilterRetriever] = None,
        profile_retriever: Optional[ProfileRetriever] = None,
        reranker: Optional[RetrievalReranker] = None,
        guardrails: Optional[Guardrails] = None,
    ):
        self.config = config
        self.vector_retriever = vector_retriever or VectorRetriever(config)

        shared_qdrant_client = None
        if hasattr(self.vector_retriever, "qdrant_client"):
            shared_qdrant_client = getattr(self.vector_retriever, "qdrant_client")

        self.filter_retriever = filter_retriever or FilterRetriever(
            config,
            qdrant_client=shared_qdrant_client,
        )
        self.profile_retriever = profile_retriever or ProfileRetriever(config)
        self.reranker = reranker or RetrievalReranker()
        self.guardrails = guardrails or Guardrails()
        rp_cfg = config.get("rp_query", {})
        self.vector_top_k = int(rp_cfg.get("vector_top_k", 30))
        self.filter_top_k = int(rp_cfg.get("filter_top_k", 20))
        self.profile_top_k = int(rp_cfg.get("profile_top_k", 10))

    def retrieve(
        self,
        query_result: QueryUnderstandingResult,
        session_state: SessionState,
        max_candidates: int = 60,
    ) -> Tuple[List[RetrievalCandidate], Dict]:
        """Execute retrieval channels and return ranked evidence with debug data."""
        start_time = time.perf_counter()

        errors: Dict[str, str] = {}

        vector_start = time.perf_counter()
        try:
            vector_candidates = self.vector_retriever.query(
                query_text=query_result.normalized_query,
                top_k=self.vector_top_k,
                active_characters=query_result.constraints.active_characters,
                location_hints=query_result.locations,
                unlocked_chapter=query_result.constraints.unlocked_chapter,
            )
        except Exception as exc:  # pragma: no cover - runtime resilience
            logger.exception("Vector retrieval failed: %s", exc)
            errors["vector"] = str(exc)
            vector_candidates = []
        vector_cost_ms = (time.perf_counter() - vector_start) * 1000

        filter_start = time.perf_counter()
        try:
            filter_candidates = self.filter_retriever.query(
                entities=query_result.entities,
                locations=query_result.locations,
                top_k=self.filter_top_k,
                unlocked_chapter=query_result.constraints.unlocked_chapter,
            )
        except Exception as exc:  # pragma: no cover - runtime resilience
            logger.exception("Filter retrieval failed: %s", exc)
            errors["filter"] = str(exc)
            filter_candidates = []
        filter_cost_ms = (time.perf_counter() - filter_start) * 1000

        profile_start = time.perf_counter()
        profile_entities = query_result.entities or query_result.constraints.active_characters
        try:
            profile_candidates = self.profile_retriever.query(profile_entities, top_k=self.profile_top_k)
        except Exception as exc:  # pragma: no cover - runtime resilience
            logger.exception("Profile retrieval failed: %s", exc)
            errors["profile"] = str(exc)
            profile_candidates = []
        profile_cost_ms = (time.perf_counter() - profile_start) * 1000

        merged = self._dedupe(vector_candidates + filter_candidates + profile_candidates)

        spoiler_filtered = self.guardrails.filter_spoilers(
            merged,
            unlocked_chapter=query_result.constraints.unlocked_chapter,
        )
        ranked = self.reranker.rank(
            spoiler_filtered,
            query_result=query_result,
            session_entities=session_state.recent_entities,
        )

        ranked = ranked[:max_candidates]

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        debug = {
            "counts": {
                "vector": len(vector_candidates),
                "filter": len(filter_candidates),
                "profile": len(profile_candidates),
                "merged": len(merged),
                "after_spoiler_filter": len(spoiler_filtered),
                "ranked": len(ranked),
            },
            "timing_ms": {
                "vector": round(vector_cost_ms, 2),
                "filter": round(filter_cost_ms, 2),
                "profile": round(profile_cost_ms, 2),
                "total": round(elapsed_ms, 2),
            },
            "errors": errors,
        }
        return ranked, debug

    def _dedupe(self, items: List[RetrievalCandidate]) -> List[RetrievalCandidate]:
        bucket = {}
        for item in items:
            key = item.dedupe_key()
            best = bucket.get(key)
            if best is None or item.semantic_score > best.semantic_score:
                bucket[key] = item
        return list(bucket.values())
