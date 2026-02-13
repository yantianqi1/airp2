"""Tests for retrieval orchestration and ranking behavior."""
import unittest

from tests.stubs import install_dependency_stubs

install_dependency_stubs()

from services.models import QueryConstraints, QueryUnderstandingResult, RetrievalCandidate
from services.retrieval_orchestrator import RetrievalOrchestrator
from services.session_state import SessionState


class _FakeVectorRetriever:
    def query(self, **kwargs):
        return [
            RetrievalCandidate(
                source_type="scene",
                source_id="1",
                chapter="chapter_0001",
                chapter_no=1,
                scene_index=2,
                text="许七安与朱县令在县衙对话。",
                event_summary="县衙问案",
                characters=["许七安", "朱县令"],
                semantic_score=0.7,
            ),
            RetrievalCandidate(
                source_type="scene",
                source_id="2",
                chapter="chapter_0020",
                chapter_no=20,
                scene_index=1,
                text="后期剧情",
                event_summary="剧透内容",
                characters=["许七安"],
                semantic_score=0.8,
            ),
        ]


class _FakeFilterRetriever:
    def query(self, **kwargs):
        return [
            RetrievalCandidate(
                source_type="scene",
                source_id="1b",
                chapter="chapter_0001",
                chapter_no=1,
                scene_index=2,
                text="许七安与朱县令在县衙对话（结构化召回）。",
                event_summary="县衙问案",
                characters=["许七安", "朱县令"],
                semantic_score=0.9,
            )
        ]


class _FakeProfileRetriever:
    def query(self, entities, top_k=10):
        return [
            RetrievalCandidate(
                source_type="profile",
                source_id="许七安",
                text="许七安性格坚韧。",
                characters=["许七安"],
                semantic_score=0.5,
            )
        ]


class RetrievalOrchestratorTests(unittest.TestCase):
    def test_orchestrator_dedupes_and_filters_spoilers(self):
        query = QueryUnderstandingResult(
            intent="story_recap",
            normalized_query="许七安和朱县令在县衙发生了什么",
            entities=["许七安", "朱县令"],
            locations=["县衙"],
            event_keywords=["县衙", "问案"],
            constraints=QueryConstraints(unlocked_chapter=10, active_characters=["许七安"]),
        )
        state = SessionState(session_id="s1", recent_entities=["许七安"])

        orchestrator = RetrievalOrchestrator(
            config={"paths": {"vector_db_path": "vector_db"}, "vector_db": {"collection_name": "novel_scenes"}},
            vector_retriever=_FakeVectorRetriever(),
            filter_retriever=_FakeFilterRetriever(),
            profile_retriever=_FakeProfileRetriever(),
        )

        ranked, debug = orchestrator.retrieve(query, state)

        # chapter_0020 should be removed by spoiler boundary.
        self.assertTrue(all((c.chapter_no or 0) <= 10 for c in ranked if c.source_type == "scene"))
        # duplicate scene (chapter_0001 scene_2) should remain once.
        scene_keys = [f"{c.chapter}:{c.scene_index}" for c in ranked if c.source_type == "scene"]
        self.assertEqual(scene_keys.count("chapter_0001:2"), 1)
        self.assertGreaterEqual(debug["counts"]["merged"], 2)
        self.assertGreaterEqual(len(ranked), 2)


if __name__ == "__main__":
    unittest.main()
