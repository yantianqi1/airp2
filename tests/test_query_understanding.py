"""Tests for rule-based query understanding."""
import json
import os
import tempfile
import unittest

from tests.stubs import install_dependency_stubs

install_dependency_stubs()

from services.query_understanding import QueryUnderstandingService
from services.session_state import SessionState


class QueryUnderstandingTests(unittest.TestCase):
    def _make_config(self, root):
        profiles_dir = os.path.join(root, "profiles")
        annotated_dir = os.path.join(root, "annotated")
        os.makedirs(profiles_dir, exist_ok=True)
        os.makedirs(annotated_dir, exist_ok=True)

        with open(os.path.join(profiles_dir, "许七安.md"), "w", encoding="utf-8") as f:
            f.write("# 许七安")

        with open(os.path.join(annotated_dir, "character_name_map.json"), "w", encoding="utf-8") as f:
            json.dump({"许七安": ["许银锣", "宁宴"]}, f, ensure_ascii=False)

        return {
            "paths": {
                "profiles_dir": profiles_dir,
                "annotated_dir": annotated_dir,
            }
        }

    def test_detects_intent_entities_and_constraints(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._make_config(tmp)
            service = QueryUnderstandingService(config)
            state = SessionState(session_id="s1", max_unlocked_chapter=12, active_characters=["许平志"])

            result = service.understand(
                message="许银锣和朱县令是什么关系？",
                history=[{"role": "user", "content": "我们在县衙"}],
                session_state=state,
            )

            self.assertEqual(result.intent, "character_relation")
            self.assertIn("许七安", result.entities)
            self.assertEqual(result.constraints.unlocked_chapter, 12)

    def test_location_and_keyword_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._make_config(tmp)
            service = QueryUnderstandingService(config)
            state = SessionState(session_id="s2")

            result = service.understand(
                message="在京城衙门接下来该怎么办？",
                session_state=state,
                unlocked_chapter=5,
                active_characters=["许七安"],
            )

            self.assertEqual(result.intent, "next_action")
            self.assertIn("京城", "".join(result.locations))
            self.assertEqual(result.constraints.unlocked_chapter, 5)
            self.assertIn("许七安", result.constraints.active_characters)
            self.assertTrue(result.event_keywords)


if __name__ == "__main__":
    unittest.main()
