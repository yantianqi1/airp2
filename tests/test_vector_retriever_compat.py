"""Compatibility tests for vector retrieval and orchestrator defaults."""
import unittest

from tests.stubs import install_dependency_stubs

install_dependency_stubs()

import services.retrieval_orchestrator as retrieval_orchestrator_module
from services.retrievers.vector_retriever import VectorRetriever


class _FakeEmbeddingClient:
    def embed(self, texts):
        if not texts:
            return []
        return [[0.1, 0.2, 0.3]]


class _FakePoint:
    def __init__(self, point_id, score, payload):
        self.id = point_id
        self.score = score
        self.payload = payload


class _QueryResponse:
    def __init__(self, points):
        self.points = points


class _QdrantQueryPointsOnly:
    def __init__(self):
        self.last_kwargs = None

    def query_points(self, **kwargs):
        self.last_kwargs = kwargs
        return _QueryResponse(
            [
                _FakePoint(
                    point_id="p1",
                    score=0.88,
                    payload={
                        "text": "许七安与朱县令在县衙对话。",
                        "chapter": "chapter_0003",
                        "chapter_no": 3,
                        "scene_index": 1,
                        "chapter_title": "第三章",
                        "scene_summary": "县衙对话",
                        "event_summary": "讨论案情",
                        "characters": ["许七安", "朱县令"],
                        "location": "县衙",
                    },
                )
            ]
        )


class _QdrantSearchOnly:
    def __init__(self):
        self.last_kwargs = None

    def search(self, **kwargs):
        self.last_kwargs = kwargs
        return [
            _FakePoint(
                point_id="p2",
                score=0.66,
                payload={
                    "text": "许七安破案。",
                    "chapter": "chapter_0002",
                    "chapter_no": 2,
                    "scene_index": 0,
                    "characters": ["许七安"],
                },
            )
        ]


class _FakeVectorWithClient:
    def __init__(self, qdrant_client):
        self.qdrant_client = qdrant_client

    def query(self, **kwargs):
        return []


class _CaptureFilterRetriever:
    def __init__(self, config, qdrant_client=None):
        self.qdrant_client = qdrant_client

    def query(self, **kwargs):
        return []


class _FakeProfileRetriever:
    def query(self, entities, top_k=10):
        return []


class VectorRetrieverCompatTests(unittest.TestCase):
    def _base_config(self):
        return {
            "embedding": {
                "base_url": "http://localhost:8000/v1",
                "api_key": "not-needed",
                "model": "x",
                "dimensions": 3,
                "batch_size": 8,
                "max_retries": 1,
                "retry_delay": 0,
            },
            "paths": {"vector_db_path": "vector_db"},
            "vector_db": {"collection_name": "novel_scenes"},
        }

    def test_vector_retriever_supports_query_points_api(self):
        cfg = self._base_config()
        qdrant = _QdrantQueryPointsOnly()
        retriever = VectorRetriever(
            cfg,
            qdrant_client=qdrant,
            embedding_client=_FakeEmbeddingClient(),
        )

        items = retriever.query(
            query_text="许七安和朱县令是什么关系？",
            top_k=5,
            active_characters=["许七安"],
            location_hints=["县衙"],
            unlocked_chapter=10,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_id, "p1")
        self.assertIn("query", qdrant.last_kwargs)
        self.assertNotIn("query_vector", qdrant.last_kwargs)
        self.assertEqual(qdrant.last_kwargs["limit"], 5)

    def test_vector_retriever_keeps_legacy_search_api(self):
        cfg = self._base_config()
        qdrant = _QdrantSearchOnly()
        retriever = VectorRetriever(
            cfg,
            qdrant_client=qdrant,
            embedding_client=_FakeEmbeddingClient(),
        )

        items = retriever.query(
            query_text="许七安最近做了什么？",
            top_k=3,
            unlocked_chapter=10,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_id, "p2")
        self.assertIn("query_vector", qdrant.last_kwargs)
        self.assertEqual(qdrant.last_kwargs["limit"], 3)

    def test_orchestrator_reuses_vector_qdrant_client_for_filter(self):
        sentinel_client = object()
        original_filter_cls = retrieval_orchestrator_module.FilterRetriever

        retrieval_orchestrator_module.FilterRetriever = _CaptureFilterRetriever
        try:
            orchestrator = retrieval_orchestrator_module.RetrievalOrchestrator(
                config=self._base_config(),
                vector_retriever=_FakeVectorWithClient(sentinel_client),
                filter_retriever=None,
                profile_retriever=_FakeProfileRetriever(),
            )
        finally:
            retrieval_orchestrator_module.FilterRetriever = original_filter_cls

        self.assertIs(orchestrator.filter_retriever.qdrant_client, sentinel_client)


if __name__ == "__main__":
    unittest.main()
