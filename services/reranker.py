"""Candidate reranking for retrieval orchestration."""
from typing import List

from .helpers import tokenize_keywords
from .models import QueryUnderstandingResult, RetrievalCandidate


class RetrievalReranker:
    """Blend semantic/entity/narrative/session signals into final rank."""

    def __init__(self):
        self.weights = {
            "semantic_score": 0.40,
            "entity_overlap": 0.30,
            "narrative_fit": 0.20,
            "recency_in_session": 0.10,
        }

    def rank(
        self,
        candidates: List[RetrievalCandidate],
        query_result: QueryUnderstandingResult,
        session_entities: List[str],
    ) -> List[RetrievalCandidate]:
        entity_set = set(query_result.entities)
        keyword_set = set(query_result.event_keywords)
        if not keyword_set:
            keyword_set = set(tokenize_keywords(query_result.normalized_query))

        session_set = set(session_entities or [])

        ranked = []
        for candidate in candidates:
            candidate.entity_overlap = self._entity_overlap(candidate, entity_set)
            candidate.narrative_fit = self._narrative_fit(candidate, keyword_set)
            candidate.recency_in_session = self._recency_fit(candidate, session_set)

            candidate.final_score = (
                candidate.semantic_score * self.weights["semantic_score"]
                + candidate.entity_overlap * self.weights["entity_overlap"]
                + candidate.narrative_fit * self.weights["narrative_fit"]
                + candidate.recency_in_session * self.weights["recency_in_session"]
            )
            ranked.append(candidate)

        ranked.sort(key=lambda item: item.final_score, reverse=True)
        return ranked

    def _entity_overlap(self, candidate: RetrievalCandidate, entities: set) -> float:
        if not entities:
            return 0.0

        fields = set(candidate.characters or [])
        if candidate.location:
            fields.add(candidate.location)

        matched = len(fields & entities)
        return matched / max(len(entities), 1)

    def _narrative_fit(self, candidate: RetrievalCandidate, keywords: set) -> float:
        if not keywords:
            return 0.0

        text_block = " ".join(
            [
                candidate.scene_summary or "",
                candidate.event_summary or "",
                candidate.text or "",
            ]
        )
        if not text_block:
            return 0.0

        matched = 0
        for keyword in keywords:
            if keyword and keyword in text_block:
                matched += 1

        return matched / max(len(keywords), 1)

    def _recency_fit(self, candidate: RetrievalCandidate, session_entities: set) -> float:
        if not session_entities:
            return 0.0

        candidate_entities = set(candidate.characters or [])
        if not candidate_entities:
            return 0.0

        overlap = len(candidate_entities & session_entities)
        return overlap / max(len(session_entities), 1)
