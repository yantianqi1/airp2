"""Contract tests for RPQueryService query/respond flow."""
import tempfile
import unittest

from tests.stubs import install_dependency_stubs

install_dependency_stubs()

from api.rp_query_api import RPQueryService
from services.models import QueryConstraints, QueryUnderstandingResult, RetrievalCandidate
from services.session_state import SessionStateStore


class _FakeQueryUnderstanding:
    def understand(self, **kwargs):
        return QueryUnderstandingResult(
            intent="story_recap",
            normalized_query=kwargs.get("message", ""),
            entities=["许七安"],
            constraints=QueryConstraints(unlocked_chapter=kwargs.get("unlocked_chapter") or 10),
        )


class _FakeOrchestrator:
    def retrieve(self, query_result, session_state, max_candidates=60):
        return [
            RetrievalCandidate(
                source_type="scene",
                source_id="p1",
                chapter="chapter_0001",
                chapter_no=1,
                scene_index=0,
                text="许七安破案。",
                event_summary="许七安破案",
                characters=["许七安"],
                final_score=0.8,
                semantic_score=0.8,
            )
        ], {"counts": {"ranked": 1}, "timing_ms": {"total": 1.2}}


class _FakeWorldbookBuilder:
    def build(self, candidates, query_result):
        return (
            {
                "facts": [
                    {
                        "fact_text": "许七安破案",
                        "source_chapter": "chapter_0001",
                        "source_scene": 0,
                        "excerpt": "许七安破案。",
                        "confidence": 0.8,
                    }
                ],
                "character_state": [],
                "timeline_notes": [],
                "forbidden": [],
            },
            [
                {
                    "source_type": "scene",
                    "source_id": "p1",
                    "chapter": "chapter_0001",
                    "scene_index": 0,
                    "excerpt": "许七安破案。",
                }
            ],
        )


class _FakeLLMClient:
    def call(self, **kwargs):
        return "基于证据，许七安已经完成破案。"


class RPApiContractTests(unittest.TestCase):
    def _base_config(self):
        return {
            "llm": {
                "base_url": "http://localhost:8000/v1",
                "api_key": "not-needed",
                "model": "x",
                "annotate_model": "x",
                "max_retries": 1,
                "retry_delay": 0,
                "rate_limit_per_minute": 0,
            },
            "embedding": {
                "base_url": "http://localhost:8000/v1",
                "api_key": "not-needed",
                "model": "x",
                "dimensions": 3,
                "batch_size": 10,
                "max_retries": 1,
                "retry_delay": 0,
            },
            "paths": {
                "vector_db_path": "vector_db",
                "profiles_dir": "data/profiles",
                "annotated_dir": "data/annotated",
            },
            "vector_db": {"collection_name": "novel_scenes"},
        }

    def test_query_and_respond_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = RPQueryService(
                config=self._base_config(),
                query_understanding=_FakeQueryUnderstanding(),
                retrieval_orchestrator=_FakeOrchestrator(),
                worldbook_builder=_FakeWorldbookBuilder(),
                session_store=SessionStateStore(base_dir=tmp),
                llm_client=_FakeLLMClient(),
            )

            context = service.query_context(
                message="许七安最近做了什么？",
                session_id="session-a",
                unlocked_chapter=10,
                active_characters=["许七安"],
            )
            self.assertIn("worldbook_context", context)
            self.assertEqual(len(context["citations"]), 1)

            resp = service.respond(
                message="继续推进剧情",
                session_id="session-a",
                worldbook_context=context["worldbook_context"],
                citations=context["citations"],
            )
            self.assertIn("assistant_reply", resp)
            self.assertIn("参考来源", resp["assistant_reply"])
            self.assertEqual(len(resp["citations"]), 1)

            session = service.get_session("session-a")
            self.assertEqual(session["session_id"], "session-a")
            self.assertGreaterEqual(len(session["turns"]), 2)


if __name__ == "__main__":
    unittest.main()
