"""Regression tests for pipeline status transitions and deterministic IDs."""
import unittest
import uuid

from tests.stubs import install_dependency_stubs

install_dependency_stubs()

import step2_scene_split as step2
import step3_annotate as step3
import step4_vectorize as step4


class StatusRuleTests(unittest.TestCase):
    """Test status transition rules used by step2/3/4."""

    def test_step2_default_skips_downstream_states(self):
        self.assertTrue(step2.should_run_step2('pending'))
        self.assertFalse(step2.should_run_step2('scenes_done'))
        self.assertFalse(step2.should_run_step2('annotated_done'))
        self.assertFalse(step2.should_run_step2('vectorized'))

    def test_step2_force_or_redo_overrides_skip(self):
        self.assertTrue(step2.should_run_step2('vectorized', force=True))
        self.assertTrue(step2.should_run_step2('vectorized', redo=True))

    def test_step3_rules(self):
        self.assertTrue(step3.should_run_step3('scenes_done'))
        self.assertFalse(step3.should_run_step3('annotated_done'))
        self.assertFalse(step3.should_run_step3('vectorized'))
        self.assertTrue(step3.should_run_step3('vectorized', force=True))
        self.assertFalse(step3.should_run_step3('pending', force=True))

    def test_step4_rules(self):
        self.assertTrue(step4.should_run_step4('annotated_done'))
        self.assertFalse(step4.should_run_step4('vectorized'))
        self.assertTrue(step4.should_run_step4('vectorized', force=True))
        self.assertFalse(step4.should_run_step4('scenes_done', force=True))

    def test_step4_stable_point_id(self):
        vectorizer = step4.SceneVectorizer.__new__(step4.SceneVectorizer)
        self.assertEqual(
            vectorizer._build_point_id('chapter_0001', 7),
            str(uuid.uuid5(uuid.NAMESPACE_URL, 'chapter_0001:000007'))
        )
        self.assertEqual(
            vectorizer._build_point_id('chapter_0001', 'invalid'),
            str(uuid.uuid5(uuid.NAMESPACE_URL, 'chapter_0001:000000'))
        )


if __name__ == '__main__':
    unittest.main()
