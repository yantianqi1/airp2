"""RP query service and optional FastAPI endpoints."""
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from services.guardrails import Guardrails
from services.novel_registry import NovelRegistry
from services.pipeline_jobs import PipelineJobsService
from services.pipeline_runner import PipelineRunner, PipelineRunSpec
from services.query_understanding import QueryUnderstandingService
from services.retrieval_orchestrator import RetrievalOrchestrator
from services.session_state import SessionStateStore
from services.worldbook_builder import WorldbookBuilder
from utils.llm_client import LLMClient


def _default_sessions_dir(config: Dict[str, Any]) -> str:
    paths = config.get("paths", {}) or {}
    sessions_dir = paths.get("sessions_dir")
    if sessions_dir:
        return str(sessions_dir)

    profiles_dir = paths.get("profiles_dir") or "/app/data/profiles"
    data_root = os.path.dirname(str(profiles_dir).rstrip("/\\"))
    return os.path.join(data_root, "sessions")


def _derive_data_root(config: Dict[str, Any]) -> str:
    paths = config.get("paths", {}) or {}
    for key in ("profiles_dir", "chapters_dir", "annotated_dir", "scenes_dir"):
        value = paths.get(key)
        if value:
            return os.path.dirname(str(value).rstrip("/\\"))
    return "/app/data"


class RPQueryService:
    """Application-level orchestration for RP query and response APIs."""

    def __init__(
        self,
        config: Dict[str, Any],
        query_understanding: Optional[QueryUnderstandingService] = None,
        retrieval_orchestrator: Optional[RetrievalOrchestrator] = None,
        worldbook_builder: Optional[WorldbookBuilder] = None,
        session_store: Optional[SessionStateStore] = None,
        guardrails: Optional[Guardrails] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        self.config = config
        self.query_understanding = query_understanding or QueryUnderstandingService(config)
        self.retrieval_orchestrator = retrieval_orchestrator or RetrievalOrchestrator(config)
        rp_cfg = config.get("rp_query", {})
        self.worldbook_builder = worldbook_builder or WorldbookBuilder(
            max_facts=int(rp_cfg.get("worldbook_top_n", 8))
        )
        self.session_store = session_store or SessionStateStore(base_dir=_default_sessions_dir(config))
        self.guardrails = guardrails or Guardrails()
        self.llm_client = llm_client or LLMClient(config)

    @classmethod
    def from_config_file(cls, config_file: str = "config.yaml") -> "RPQueryService":
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls(config=config)

    def query_context(
        self,
        message: str,
        session_id: str,
        unlocked_chapter: Optional[int] = None,
        active_characters: Optional[List[str]] = None,
        recent_messages: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        state = self.session_store.load(session_id, default_unlocked=unlocked_chapter or 0)
        self.session_store.apply_runtime_updates(
            state,
            unlocked_chapter=unlocked_chapter,
            active_characters=active_characters,
        )

        history = recent_messages if recent_messages is not None else state.turns[-10:]

        understanding = self.query_understanding.understand(
            message=message,
            history=history,
            session_state=state,
            unlocked_chapter=state.max_unlocked_chapter,
            active_characters=state.active_characters,
        )

        ranked_candidates, debug = self.retrieval_orchestrator.retrieve(
            query_result=understanding,
            session_state=state,
            max_candidates=60,
        )

        worldbook_context, citations = self.worldbook_builder.build(ranked_candidates, understanding)

        self.session_store.append_turn(state, role="user", content=message)
        self.session_store.remember_entities(state, understanding.entities)
        self.session_store.save(state)

        return {
            "session_id": session_id,
            "worldbook_context": worldbook_context,
            "citations": citations,
            "debug_scores": debug,
            "query_understanding": understanding.to_dict(),
        }

    def respond(
        self,
        message: str,
        session_id: str,
        worldbook_context: Optional[Dict[str, Any]] = None,
        citations: Optional[List[Dict[str, Any]]] = None,
        unlocked_chapter: Optional[int] = None,
        active_characters: Optional[List[str]] = None,
        recent_messages: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        if worldbook_context is None or citations is None:
            context_resp = self.query_context(
                message=message,
                session_id=session_id,
                unlocked_chapter=unlocked_chapter,
                active_characters=active_characters,
                recent_messages=recent_messages,
            )
            worldbook_context = context_resp["worldbook_context"]
            citations = context_resp["citations"]

        citations = citations or []
        state = self.session_store.load(session_id, default_unlocked=unlocked_chapter or 0)
        self.session_store.apply_runtime_updates(
            state,
            unlocked_chapter=unlocked_chapter,
            active_characters=active_characters,
        )

        # Avoid duplicate user turns when query_context has already recorded the same message.
        last_turn = state.turns[-1] if state.turns else {}
        if not (last_turn.get("role") == "user" and last_turn.get("content") == message):
            self.session_store.append_turn(state, role="user", content=message)

        if not self.guardrails.has_enough_evidence(citations):
            fallback_reply = "未检索到明确证据，请补充人物、地点或章节范围后重试。"
            self.session_store.append_turn(state, role="assistant", content=fallback_reply)
            self.session_store.save(state)
            return {
                "assistant_reply": fallback_reply,
                "citations": citations,
                "worldbook_context": worldbook_context,
            }

        system_prompt = self.guardrails.build_grounding_system_prompt()
        user_prompt = self.guardrails.compose_grounding_prompt(message, worldbook_context)

        try:
            reply = self.llm_client.call(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.4,
            )
        except Exception:
            reply = self._fallback_reply(message, worldbook_context)

        final_reply = self.guardrails.append_citation_footer(str(reply), citations)

        self.session_store.append_turn(state, role="assistant", content=final_reply)
        self.session_store.save(state)

        return {
            "assistant_reply": final_reply,
            "citations": citations,
            "worldbook_context": worldbook_context,
        }

    def get_session(self, session_id: str) -> Dict[str, Any]:
        state = self.session_store.load(session_id)
        return state.to_dict()

    def _fallback_reply(self, message: str, worldbook_context: Dict[str, Any]) -> str:
        facts = worldbook_context.get("facts", [])
        if not facts:
            return "当前没有足够证据支持回复，请提供更具体的问题。"

        lines = ["根据当前证据："]
        for item in facts[:3]:
            source_chapter = item.get("source_chapter") or "unknown"
            source_scene = item.get("source_scene")
            source = f"{source_chapter} / scene {source_scene}" if source_scene is not None else source_chapter
            lines.append(f"- {item.get('fact_text', '')}（{source}）")

        lines.append("如果你希望我继续推进剧情，请指定你要扮演的角色和当前目标。")
        return "\n".join(lines)


class MultiNovelRPQueryService:
    """Route RP queries to a per-novel RPQueryService instance (cached)."""

    def __init__(self, base_config: Dict[str, Any], registry: Optional[NovelRegistry] = None):
        self.base_config = base_config
        self.registry = registry
        self._lock = threading.Lock()
        self._services: Dict[str, RPQueryService] = {}
        self._default_service: Optional[RPQueryService] = None

    def invalidate(self, novel_id: str) -> None:
        novel_id = str(novel_id or "").strip()
        if not novel_id:
            return
        with self._lock:
            self._services.pop(novel_id, None)

    def _get_default(self) -> RPQueryService:
        with self._lock:
            if self._default_service is None:
                self._default_service = RPQueryService(config=self.base_config)
            return self._default_service

    def _build_service_for_novel(self, novel_id: str) -> RPQueryService:
        if self.registry is None:
            return self._get_default()

        paths = self.registry.paths(novel_id)
        config = dict(self.base_config)
        config_paths = dict((self.base_config.get("paths") or {}))
        config_paths.update(
            {
                "input_file": paths["source_file"],
                "chapters_dir": paths["chapters_dir"],
                "scenes_dir": paths["scenes_dir"],
                "annotated_dir": paths["annotated_dir"],
                "profiles_dir": paths["profiles_dir"],
                "vector_db_path": paths["vector_db_path"],
                "log_dir": paths["log_dir"],
                "sessions_dir": paths["sessions_dir"],
            }
        )
        config["paths"] = config_paths

        return RPQueryService(
            config=config,
            session_store=SessionStateStore(base_dir=paths["sessions_dir"]),
        )

    def get_service(self, novel_id: Optional[str]) -> RPQueryService:
        novel_id = str(novel_id or "").strip()
        if not novel_id:
            return self._get_default()

        with self._lock:
            cached = self._services.get(novel_id)
            if cached is not None:
                return cached

        # Ensure novel exists (outside lock to avoid blocking other callers).
        if self.registry is not None:
            self.registry.get(novel_id)

        service = self._build_service_for_novel(novel_id)
        with self._lock:
            self._services[novel_id] = service
        return service

    def query_context(self, novel_id: Optional[str], **kwargs: Any) -> Dict[str, Any]:
        return self.get_service(novel_id).query_context(**kwargs)

    def respond(self, novel_id: Optional[str], **kwargs: Any) -> Dict[str, Any]:
        return self.get_service(novel_id).respond(**kwargs)

    def get_session(self, novel_id: Optional[str], session_id: str) -> Dict[str, Any]:
        return self.get_service(novel_id).get_session(session_id)


def create_app(config_file: str = "config.yaml"):
    """Create FastAPI app lazily so dependency stays optional."""
    try:
        from fastapi import FastAPI, File, HTTPException, UploadFile
        from fastapi.responses import FileResponse
    except ImportError as exc:  # pragma: no cover - optional runtime path
        raise RuntimeError(
            "FastAPI is not installed. Install with `pip install fastapi uvicorn`."
        ) from exc

    with open(config_file, "r", encoding="utf-8") as f:
        base_config = yaml.safe_load(f)

    data_root = _derive_data_root(base_config)
    vector_db_root = str(base_config.get("paths", {}).get("vector_db_path") or "/app/vector_db")
    logs_root = str(base_config.get("paths", {}).get("log_dir") or "/app/logs")

    registry = NovelRegistry(data_root=data_root, vector_db_root=vector_db_root, logs_root=logs_root)
    rp_router = MultiNovelRPQueryService(base_config=base_config, registry=registry)

    runner = PipelineRunner(base_config=base_config, registry=registry)
    jobs_dir = os.path.join(data_root, "jobs")

    def _on_job_update(job):
        try:
            if job.status in {"queued", "running"}:
                registry.update(job.novel_id, status="processing", last_job_id=job.job_id, last_error="")
            elif job.status == "succeeded":
                registry.update(
                    job.novel_id,
                    status="ready",
                    last_job_id=job.job_id,
                    last_error="",
                    stats=job.result or {},
                )
                rp_router.invalidate(job.novel_id)
            elif job.status == "failed":
                registry.update(
                    job.novel_id,
                    status="failed",
                    last_job_id=job.job_id,
                    last_error=job.error,
                )
                rp_router.invalidate(job.novel_id)
        except Exception:
            pass

    jobs = PipelineJobsService(
        jobs_dir=jobs_dir,
        runner=runner,
        max_concurrent_jobs=1,
        on_job_update=_on_job_update,
    )
    app = FastAPI(title="RP Query API", version="1.0.0")

    @app.get("/api/v1/novels")
    def list_novels():
        return registry.list()

    @app.post("/api/v1/novels")
    def create_novel(payload: Dict[str, Any]):
        title = str(payload.get("title", "") or "")
        return registry.create(title=title)

    @app.get("/api/v1/novels/{novel_id}")
    def get_novel(novel_id: str):
        try:
            entry = registry.get(novel_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        entry["paths"] = registry.paths(novel_id)
        return entry

    @app.delete("/api/v1/novels/{novel_id}")
    def delete_novel(novel_id: str, delete_vector_db: bool = False):
        try:
            registry.delete(novel_id, delete_vector_db=bool(delete_vector_db))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"deleted": True, "novel_id": novel_id}

    @app.post("/api/v1/novels/{novel_id}/upload")
    async def upload_novel(novel_id: str, file: UploadFile = File(...)):
        try:
            registry.get(novel_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

        filename = str(getattr(file, "filename", "") or "")
        if not filename.lower().endswith(".txt"):
            raise HTTPException(status_code=400, detail="only .txt files are supported")

        paths = registry.paths(novel_id)
        os.makedirs(paths["input_dir"], exist_ok=True)
        dst_path = paths["source_file"]

        max_bytes = 50 * 1024 * 1024
        total = 0
        try:
            with open(dst_path, "wb") as f:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise HTTPException(status_code=413, detail="file too large (limit 50MB)")
                    f.write(chunk)
        finally:
            try:
                await file.close()
            except Exception:
                pass

        meta: Dict[str, Any] = {"filename": filename, "bytes": total}
        try:
            from utils.text_utils import read_text_file

            text = read_text_file(dst_path)
            meta["char_count"] = len(text)
            meta["line_count"] = len(text.splitlines())
        except Exception:
            pass

        registry.update(novel_id, status="uploaded", source=meta, last_error="")
        rp_router.invalidate(novel_id)

        return {"uploaded": True, "novel_id": novel_id, "source": meta}

    @app.get("/api/v1/novels/{novel_id}/source")
    def get_novel_source(novel_id: str):
        try:
            entry = registry.get(novel_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

        paths = registry.paths(novel_id)
        if not os.path.exists(paths["source_file"]):
            raise HTTPException(status_code=404, detail="source not uploaded")

        return entry.get("source", {}) or {}

    @app.get("/api/v1/novels/{novel_id}/pipeline/chapter-index")
    def get_pipeline_chapter_index(novel_id: str):
        try:
            registry.get(novel_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

        paths = registry.paths(novel_id)
        index_file = os.path.join(paths["chapters_dir"], "chapter_index.json")
        if not os.path.exists(index_file):
            raise HTTPException(status_code=404, detail="chapter index not found (run step1 first)")

        try:
            with open(index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"failed to read chapter index: {exc}")

    @app.post("/api/v1/novels/{novel_id}/pipeline/run")
    def run_pipeline(novel_id: str, payload: Dict[str, Any]):
        try:
            registry.get(novel_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

        step = payload.get("step")
        if step is not None:
            try:
                step = int(step)
            except Exception:
                raise HTTPException(status_code=400, detail="step must be an integer 1..5")
            if step not in {1, 2, 3, 4, 5}:
                raise HTTPException(status_code=400, detail="step must be in [1,2,3,4,5]")

        redo_chapter = payload.get("redo_chapter")
        if redo_chapter is not None:
            try:
                redo_chapter = int(redo_chapter)
            except Exception:
                raise HTTPException(status_code=400, detail="redo_chapter must be an integer")

        spec = PipelineRunSpec(
            step=step,
            force=bool(payload.get("force", False)),
            redo_chapter=redo_chapter,
        )

        paths = registry.paths(novel_id)
        os.makedirs(paths["log_dir"], exist_ok=True)
        job_id = uuid.uuid4().hex
        log_path = os.path.join(paths["log_dir"], f"job_{job_id}.log")

        try:
            job = jobs.start(novel_id=novel_id, spec=spec, log_path=log_path, job_id=job_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        registry.update(novel_id, status="processing", last_job_id=job.job_id, last_error="")
        return job.to_dict()

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str):
        try:
            return jobs.get(job_id).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/api/v1/jobs/{job_id}/logs")
    def get_job_logs(job_id: str, lines: int = 200):
        lines = max(1, min(int(lines or 200), 2000))
        try:
            text = jobs.tail_logs(job_id, lines=lines)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"job_id": job_id, "lines": lines, "text": text}

    @app.post("/api/v1/rp/query-context")
    def query_context(payload: Dict[str, Any]):
        try:
            message = payload["message"]
            session_id = payload["session_id"]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}")

        try:
            return rp_router.query_context(
                payload.get("novel_id"),
                message=message,
                session_id=session_id,
                unlocked_chapter=payload.get("unlocked_chapter"),
                active_characters=payload.get("active_characters"),
                recent_messages=payload.get("recent_messages"),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/api/v1/rp/respond")
    def respond(payload: Dict[str, Any]):
        try:
            message = payload["message"]
            session_id = payload["session_id"]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}")

        try:
            return rp_router.respond(
                payload.get("novel_id"),
                message=message,
                session_id=session_id,
                worldbook_context=payload.get("worldbook_context"),
                citations=payload.get("citations"),
                unlocked_chapter=payload.get("unlocked_chapter"),
                active_characters=payload.get("active_characters"),
                recent_messages=payload.get("recent_messages"),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/api/v1/rp/session/{session_id}")
    def get_session(session_id: str, novel_id: Optional[str] = None):
        try:
            return rp_router.get_session(novel_id, session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if frontend_dist.exists():
        index_file = frontend_dist / "index.html"

        @app.get("/", include_in_schema=False)
        def serve_frontend_root():
            return FileResponse(index_file)

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_frontend(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")

            requested = (frontend_dist / full_path).resolve()
            if requested.is_relative_to(frontend_dist) and requested.is_file():
                return FileResponse(requested)

            return FileResponse(index_file)

    return app


if __name__ == "__main__":
    # Lightweight CLI demo for environments without web server setup.
    service = RPQueryService.from_config_file("config.yaml")
    demo = service.query_context(
        message="许七安和朱县令是什么关系？",
        session_id="demo-session",
        unlocked_chapter=13,
    )
    print(json.dumps(demo, ensure_ascii=False, indent=2))
