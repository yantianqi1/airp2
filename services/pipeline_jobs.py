"""Pipeline job manager (MVP: single-process background thread + SQLite persistence)."""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from .pipeline_runner import PipelineRunSpec, PipelineRunner
from .db import Database, utc_now
from .novels_service import NovelsService


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PipelineJob:
    job_id: str
    novel_id: str
    owner_user_id: str = ""
    status: str = "queued"  # queued|running|succeeded|failed
    current_step: Optional[int] = None
    progress: float = 0.0  # 0..1
    started_at: str = ""
    finished_at: str = ""
    log_path: str = ""
    error: str = ""
    result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineJob":
        return cls(
            job_id=str(data.get("job_id", "")),
            novel_id=str(data.get("novel_id", "")),
            owner_user_id=str(data.get("owner_user_id", "")),
            status=str(data.get("status", "queued")),
            current_step=data.get("current_step"),
            progress=float(data.get("progress", 0.0) or 0.0),
            started_at=str(data.get("started_at", "")),
            finished_at=str(data.get("finished_at", "")),
            log_path=str(data.get("log_path", "")),
            error=str(data.get("error", "")),
            result=dict(data.get("result", {}) or {}),
        )


def _tail_text_file(path: str, lines: int = 200) -> str:
    if lines <= 0:
        return ""
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read().splitlines()
        return "\n".join(data[-lines:])
    except Exception:
        return ""


class PipelineJobsService:
    """Manage pipeline jobs and persist status to disk."""

    def __init__(
        self,
        db: Database,
        runner: PipelineRunner,
        novels: NovelsService,
        max_concurrent_jobs: int = 1,
        on_job_update: Optional[Callable[[PipelineJob], None]] = None,
    ):
        self.db = db
        self.runner = runner
        self.novels = novels
        self.max_concurrent_jobs = max(1, int(max_concurrent_jobs or 1))
        self.on_job_update = on_job_update
        self._lock = threading.Lock()
        self._running_job_id: Optional[str] = None
        # Best-effort cleanup of stale "running" jobs (service restart).
        try:
            self.db.execute(
                "UPDATE pipeline_jobs SET status='failed', error=? WHERE status IN ('queued','running');",
                ("job aborted due to service restart",),
            )
        except Exception:
            pass

    def _save(self, job: PipelineJob) -> None:
        payload = job.to_dict()
        self.db.execute(
            """
            INSERT INTO pipeline_jobs (id, novel_id, owner_user_id, spec, status, current_step, progress, started_at, finished_at, created_at, log_path, error, result)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              novel_id=excluded.novel_id,
              owner_user_id=excluded.owner_user_id,
              status=excluded.status,
              current_step=excluded.current_step,
              progress=excluded.progress,
              started_at=excluded.started_at,
              finished_at=excluded.finished_at,
              log_path=excluded.log_path,
              error=excluded.error,
              result=excluded.result;
            """,
            (
                payload["job_id"],
                payload["novel_id"],
                payload.get("owner_user_id", "") or "",
                json.dumps({}, ensure_ascii=False),  # spec is stored only at creation
                payload["status"],
                payload.get("current_step"),
                float(payload.get("progress") or 0.0),
                payload.get("started_at") or "",
                payload.get("finished_at") or "",
                payload.get("started_at") or utc_now(),  # keep non-empty
                payload.get("log_path") or "",
                payload.get("error") or "",
                json.dumps(payload.get("result") or {}, ensure_ascii=False),
            ),
        )
        if self.on_job_update:
            try:
                self.on_job_update(job)
            except Exception:
                pass

    def get(self, job_id: str) -> PipelineJob:
        row = self.db.query_one("SELECT * FROM pipeline_jobs WHERE id = ?;", (str(job_id or ""),))
        if not row:
            raise KeyError(f"job not found: {job_id}")
        result = {}
        try:
            result = json.loads(row.get("result") or "{}") if isinstance(row.get("result"), str) else {}
        except Exception:
            result = {}
        return PipelineJob(
            job_id=str(row.get("id") or ""),
            novel_id=str(row.get("novel_id") or ""),
            owner_user_id=str(row.get("owner_user_id") or ""),
            status=str(row.get("status") or "queued"),
            current_step=row.get("current_step"),
            progress=float(row.get("progress") or 0.0),
            started_at=str(row.get("started_at") or ""),
            finished_at=str(row.get("finished_at") or ""),
            log_path=str(row.get("log_path") or ""),
            error=str(row.get("error") or ""),
            result=result if isinstance(result, dict) else {},
        )

    def start(
        self,
        novel_id: str,
        spec: PipelineRunSpec,
        log_path: str,
        job_id: Optional[str] = None,
    ) -> PipelineJob:
        novel_id = str(novel_id or "").strip()
        if not novel_id:
            raise ValueError("novel_id is empty")

        record = self.novels.get(novel_id)

        with self._lock:
            if self._running_job_id is not None:
                running = self.get(self._running_job_id)
                if running.status in {"queued", "running"}:
                    raise RuntimeError("another pipeline job is already running")
                self._running_job_id = None

            allocated_job_id = str(job_id or "").strip() or uuid.uuid4().hex
            job = PipelineJob(
                job_id=allocated_job_id,
                novel_id=novel_id,
                owner_user_id=record.owner_user_id,
                log_path=log_path,
            )

            now = utc_now()
            self.db.execute(
                """
                INSERT INTO pipeline_jobs (id, novel_id, owner_user_id, spec, status, current_step, progress, started_at, finished_at, created_at, log_path, error, result)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?);
                """,
                (
                    job.job_id,
                    job.novel_id,
                    job.owner_user_id,
                    json.dumps(asdict(spec), ensure_ascii=False),
                    job.status,
                    job.current_step,
                    float(job.progress),
                    "",
                    "",
                    now,
                    job.log_path,
                    "",
                    "{}",
                ),
            )

            if self.on_job_update:
                try:
                    self.on_job_update(job)
                except Exception:
                    pass
            self._running_job_id = allocated_job_id

            thread = threading.Thread(target=self._run_job_thread, args=(job, spec), daemon=True)
            thread.start()
            return job

    def _run_job_thread(self, job: PipelineJob, spec: PipelineRunSpec) -> None:
        job.status = "running"
        job.started_at = _utc_now()
        job.current_step = spec.step
        job.progress = 0.01
        self._save(job)

        try:
            # Provide coarse progress updates per step.
            if spec.step is None:
                total_steps = 5
                merged_result: Dict[str, Any] = {}
                for step in range(1, 6):
                    job.current_step = step
                    job.progress = (step - 1) / total_steps
                    self._save(job)
                    step_result = self.runner.run(
                        job.novel_id,
                        PipelineRunSpec(step=step, force=spec.force, redo_chapter=spec.redo_chapter),
                        log_path=job.log_path,
                    )
                    if isinstance(step_result, dict):
                        merged_result.update(step_result)
                job.progress = 1.0
                job.current_step = 5
                job.result = {"mode": "full", **merged_result}
            else:
                job.current_step = int(spec.step)
                job.progress = 0.1
                self._save(job)
                result = self.runner.run(job.novel_id, spec, log_path=job.log_path)
                job.progress = 1.0
                job.result = result

            job.status = "succeeded"
            job.finished_at = _utc_now()
            self._save(job)
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = _utc_now()
            self._save(job)
        finally:
            with self._lock:
                if self._running_job_id == job.job_id:
                    self._running_job_id = None

    def tail_logs(self, job_id: str, lines: int = 200) -> str:
        job = self.get(job_id)
        return _tail_text_file(job.log_path, lines=lines)
