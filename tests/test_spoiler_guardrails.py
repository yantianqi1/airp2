"""Tests for spoiler and evidence guardrails."""
import unittest

from tests.stubs import install_dependency_stubs

install_dependency_stubs()

from services.guardrails import Guardrails
from services.models import QueryConstraints, QueryUnderstandingResult, RetrievalCandidate


class GuardrailsTests(unittest.TestCase):
    def test_filter_spoilers(self):
        guardrails = Guardrails()
        items = [
            RetrievalCandidate(
                source_type="scene",
                source_id="1",
                chapter="chapter_0002",
                chapter_no=2,
                scene_index=0,
                text="safe",
            ),
            RetrievalCandidate(
                source_type="scene",
                source_id="2",
                chapter="chapter_0020",
                chapter_no=20,
                scene_index=0,
                text="spoiler",
            ),
            RetrievalCandidate(
                source_type="profile",
                source_id="许七安",
                text="profile",
            ),
        ]

        filtered = guardrails.filter_spoilers(items, unlocked_chapter=10)
        self.assertEqual(len(filtered), 2)
        self.assertTrue(any(item.source_type == "profile" for item in filtered))
        self.assertTrue(all((item.chapter_no or 0) <= 10 for item in filtered if item.source_type == "scene"))

    def test_insufficient_evidence_reply(self):
        guardrails = Guardrails()
        query = QueryUnderstandingResult(
            intent="next_action",
            normalized_query="下一步怎么办",
            constraints=QueryConstraints(unlocked_chapter=5),
        )
        reply = guardrails.build_insufficient_evidence_reply(query)
        self.assertIn("证据", reply)


if __name__ == "__main__":
    unittest.main()
