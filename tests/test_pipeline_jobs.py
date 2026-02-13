"""Tests for pipeline job state machine (without running real steps)."""

import os
import tempfile
import time
import unittest

from tests.stubs import install_dependency_stubs

install_dependency_stubs()

from services.db import Database, utc_now
from services.novels_service import NovelsService
from services.pipeline_jobs import PipelineJobsService
from services.pipeline_runner import PipelineRunSpec
from services.storage_layout import StorageLayout


class _FakeRunner:
    def __init__(self, delay_s: float = 0.02):
        self.delay_s = delay_s
        self.calls = []

    def run(self, novel_id, spec, log_path):  # noqa: ANN001 - test stub
        self.calls.append((novel_id, spec.step))
        time.sleep(self.delay_s)
        return {"novel_id": novel_id, "step": spec.step}


class PipelineJobsTests(unittest.TestCase):
    def test_runs_single_step_job_to_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(path=os.path.join(tmp, "app.sqlite3"))
            db.init_schema()
            db.execute(
                "INSERT INTO users (id, username, password_hash, created_at) VALUES (?,?,?,?);",
                ("u1", "user1", "x", utc_now()),
            )
            db.execute(
                """
                INSERT INTO novels (id, owner_user_id, title, visibility, status, created_at, updated_at, source_meta, stats, last_job_id, last_error)
                VALUES (?,?,?,?,?,?,?,?,?,?,?);
                """,
                ("n1", "u1", "t", "private", "created", utc_now(), utc_now(), "{}", "{}", "", ""),
            )
            layout = StorageLayout(data_root=tmp, vector_db_root=os.path.join(tmp, "vdb"), logs_root=os.path.join(tmp, "logs"))
            novels = NovelsService(db=db, layout=layout)
            runner = _FakeRunner(delay_s=0.01)
            jobs = PipelineJobsService(db=db, runner=runner, novels=novels)

            job = jobs.start(
                novel_id="n1",
                spec=PipelineRunSpec(step=1, force=False, redo_chapter=None),
                log_path=os.path.join(tmp, "job.log"),
                job_id="job-1",
            )
            self.assertEqual(job.job_id, "job-1")

            deadline = time.time() + 2.0
            while time.time() < deadline:
                current = jobs.get("job-1")
                if current.status in {"succeeded", "failed"}:
                    break
                time.sleep(0.01)

            final = jobs.get("job-1")
            self.assertEqual(final.status, "succeeded")
            self.assertEqual(final.novel_id, "n1")
            self.assertTrue(final.started_at)
            self.assertTrue(final.finished_at)
            self.assertEqual(runner.calls, [("n1", 1)])

    def test_rejects_concurrent_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(path=os.path.join(tmp, "app.sqlite3"))
            db.init_schema()
            db.execute(
                "INSERT INTO users (id, username, password_hash, created_at) VALUES (?,?,?,?);",
                ("u1", "user1", "x", utc_now()),
            )
            db.execute(
                "INSERT INTO users (id, username, password_hash, created_at) VALUES (?,?,?,?);",
                ("u2", "user2", "x", utc_now()),
            )
            db.execute(
                """
                INSERT INTO novels (id, owner_user_id, title, visibility, status, created_at, updated_at, source_meta, stats, last_job_id, last_error)
                VALUES (?,?,?,?,?,?,?,?,?,?,?);
                """,
                ("n1", "u1", "t", "private", "created", utc_now(), utc_now(), "{}", "{}", "", ""),
            )
            db.execute(
                """
                INSERT INTO novels (id, owner_user_id, title, visibility, status, created_at, updated_at, source_meta, stats, last_job_id, last_error)
                VALUES (?,?,?,?,?,?,?,?,?,?,?);
                """,
                ("n2", "u2", "t2", "private", "created", utc_now(), utc_now(), "{}", "{}", "", ""),
            )
            layout = StorageLayout(data_root=tmp, vector_db_root=os.path.join(tmp, "vdb"), logs_root=os.path.join(tmp, "logs"))
            novels = NovelsService(db=db, layout=layout)
            runner = _FakeRunner(delay_s=0.2)
            jobs = PipelineJobsService(db=db, runner=runner, novels=novels)

            jobs.start(
                novel_id="n1",
                spec=PipelineRunSpec(step=1),
                log_path=os.path.join(tmp, "a.log"),
                job_id="job-a",
            )

            with self.assertRaises(RuntimeError):
                jobs.start(
                    novel_id="n2",
                    spec=PipelineRunSpec(step=1),
                    log_path=os.path.join(tmp, "b.log"),
                    job_id="job-b",
                )

            # Let background thread finish before temp dir is removed.
            deadline = time.time() + 2.0
            while time.time() < deadline:
                current = jobs.get("job-a")
                if current.status in {"succeeded", "failed"}:
                    break
                time.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
