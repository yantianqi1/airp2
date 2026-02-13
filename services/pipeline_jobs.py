"""Pipeline job manager (MVP: single-process background thread)."""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from .pipeline_runner import PipelineRunSpec, PipelineRunner


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PipelineJob:
    job_id: str
    novel_id: str
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
        jobs_dir: str,
        runner: PipelineRunner,
        max_concurrent_jobs: int = 1,
        on_job_update: Optional[Callable[[PipelineJob], None]] = None,
    ):
        self.jobs_dir = jobs_dir
        self.runner = runner
        self.max_concurrent_jobs = max(1, int(max_concurrent_jobs or 1))
        self.on_job_update = on_job_update
        self._lock = threading.Lock()
        self._running_job_id: Optional[str] = None
        os.makedirs(self.jobs_dir, exist_ok=True)

    def _path(self, job_id: str) -> str:
        safe_id = str(job_id).replace("/", "_").replace("\\", "_")
        return os.path.join(self.jobs_dir, f"{safe_id}.json")

    def _save(self, job: PipelineJob) -> None:
        path = self._path(job.job_id)
        # Use a unique temp file to avoid cross-thread collisions.
        tmp_path = f"{path}.{uuid.uuid4().hex}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(job.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        if self.on_job_update:
            try:
                self.on_job_update(job)
            except Exception:
                pass

    def get(self, job_id: str) -> PipelineJob:
        path = self._path(job_id)
        if not os.path.exists(path):
            raise KeyError(f"job not found: {job_id}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PipelineJob.from_dict(data)

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

        with self._lock:
            if self._running_job_id is not None:
                running = self.get(self._running_job_id)
                if running.status in {"queued", "running"}:
                    raise RuntimeError("another pipeline job is already running")
                self._running_job_id = None

            allocated_job_id = str(job_id or "").strip() or uuid.uuid4().hex
            job = PipelineJob(job_id=allocated_job_id, novel_id=novel_id, log_path=log_path)
            self._save(job)
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
