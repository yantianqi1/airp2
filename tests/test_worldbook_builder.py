"""Tests for worldbook context builder."""
import unittest

from tests.stubs import install_dependency_stubs

install_dependency_stubs()

from services.models import QueryConstraints, QueryUnderstandingResult, RetrievalCandidate
from services.worldbook_builder import WorldbookBuilder


class WorldbookBuilderTests(unittest.TestCase):
    def test_builds_facts_character_state_and_citations(self):
        builder = WorldbookBuilder(max_facts=8)
        query = QueryUnderstandingResult(
            intent="story_recap",
            normalized_query="问题",
            constraints=QueryConstraints(unlocked_chapter=13),
        )
        candidates = [
            RetrievalCandidate(
                source_type="scene",
                source_id="p1",
                chapter="chapter_0003",
                chapter_no=3,
                scene_index=1,
                text="许七安在县衙复盘税银案。",
                event_summary="复盘税银案",
                final_score=0.91,
            ),
            RetrievalCandidate(
                source_type="profile",
                source_id="许七安",
                text="许七安为人机警果断。",
                final_score=0.72,
            ),
        ]

        worldbook, citations = builder.build(candidates, query)

        self.assertEqual(len(worldbook["facts"]), 1)
        self.assertEqual(len(worldbook["character_state"]), 1)
        self.assertTrue(worldbook["timeline_notes"])
        self.assertTrue(any("防剧透" in item for item in worldbook["forbidden"]))
        self.assertEqual(len(citations), 2)


if __name__ == "__main__":
    unittest.main()
