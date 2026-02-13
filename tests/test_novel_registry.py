"""Tests for multi-novel registry and workspace layout."""

import os
import tempfile
import unittest

from tests.stubs import install_dependency_stubs

install_dependency_stubs()

from services.novel_registry import NovelRegistry


class NovelRegistryTests(unittest.TestCase):
    def test_create_list_get_update_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = os.path.join(tmp, "data")
            vector_db_root = os.path.join(tmp, "vector_db")
            logs_root = os.path.join(tmp, "logs")

            registry = NovelRegistry(data_root=data_root, vector_db_root=vector_db_root, logs_root=logs_root)

            created = registry.create(title="My Novel")
            novel_id = created["novel_id"]
            self.assertTrue(novel_id.startswith("my-novel-"))

            listed = registry.list()
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["novel_id"], novel_id)

            fetched = registry.get(novel_id)
            self.assertEqual(fetched["title"], "My Novel")
            self.assertEqual(fetched["status"], "created")

            paths = registry.paths(novel_id)
            self.assertTrue(os.path.isdir(paths["chapters_dir"]))
            self.assertTrue(os.path.isdir(paths["vector_db_path"]))
            self.assertTrue(os.path.isdir(paths["log_dir"]))

            registry.update(novel_id, status="uploaded", source={"filename": "a.txt", "bytes": 10})
            fetched2 = registry.get(novel_id)
            self.assertEqual(fetched2["status"], "uploaded")
            self.assertEqual(fetched2["source"]["filename"], "a.txt")

            registry.delete(novel_id, delete_vector_db=True)
            self.assertEqual(registry.list(), [])
            self.assertFalse(os.path.exists(paths["novel_dir"]))
            self.assertFalse(os.path.exists(paths["vector_db_path"]))


if __name__ == "__main__":
    unittest.main()
