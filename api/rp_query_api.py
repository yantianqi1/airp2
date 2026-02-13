"""RP query service and optional FastAPI endpoints."""
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from services.guardrails import Guardrails
from services.auth_service import Actor, AuthService
from services.db import Database
from services.novels_service import NovelsService
from services.pipeline_jobs import PipelineJobsService
from services.pipeline_runner import PipelineRunner, PipelineRunSpec
from services.query_understanding import QueryUnderstandingService
from services.retrieval_orchestrator import RetrievalOrchestrator
from services.session_state import SessionStateStore
from services.storage_layout import StorageLayout
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
        session_store: Optional[SessionStateStore] = None,
    ) -> Dict[str, Any]:
        store = session_store or self.session_store
        state = store.load(session_id, default_unlocked=unlocked_chapter or 0)
        store.apply_runtime_updates(
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

        store.append_turn(state, role="user", content=message)
        store.remember_entities(state, understanding.entities)
        store.save(state)

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
        session_store: Optional[SessionStateStore] = None,
    ) -> Dict[str, Any]:
        if worldbook_context is None or citations is None:
            context_resp = self.query_context(
                message=message,
                session_id=session_id,
                unlocked_chapter=unlocked_chapter,
                active_characters=active_characters,
                recent_messages=recent_messages,
                session_store=session_store,
            )
            worldbook_context = context_resp["worldbook_context"]
            citations = context_resp["citations"]

        citations = citations or []
        store = session_store or self.session_store
        state = store.load(session_id, default_unlocked=unlocked_chapter or 0)
        store.apply_runtime_updates(
            state,
            unlocked_chapter=unlocked_chapter,
            active_characters=active_characters,
        )

        # Avoid duplicate user turns when query_context has already recorded the same message.
        last_turn = state.turns[-1] if state.turns else {}
        if not (last_turn.get("role") == "user" and last_turn.get("content") == message):
            store.append_turn(state, role="user", content=message)

        if not self.guardrails.has_enough_evidence(citations):
            fallback_reply = "未检索到明确证据，请补充人物、地点或章节范围后重试。"
            store.append_turn(state, role="assistant", content=fallback_reply)
            store.save(state)
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

        store.append_turn(state, role="assistant", content=final_reply)
        store.save(state)

        return {
            "assistant_reply": final_reply,
            "citations": citations,
            "worldbook_context": worldbook_context,
        }

    def get_session(self, session_id: str, session_store: Optional[SessionStateStore] = None) -> Dict[str, Any]:
        store = session_store or self.session_store
        state = store.load(session_id)
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

    def __init__(self, base_config: Dict[str, Any], novels: Optional[NovelsService] = None):
        self.base_config = base_config
        self.novels = novels
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
        if self.novels is None:
            return self._get_default()

        paths = self.novels.paths(novel_id)
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
            }
        )
        config["paths"] = config_paths

        return RPQueryService(config=config)

    def get_service(self, novel_id: Optional[str]) -> RPQueryService:
        novel_id = str(novel_id or "").strip()
        if not novel_id:
            return self._get_default()

        with self._lock:
            cached = self._services.get(novel_id)
            if cached is not None:
                return cached

        # Ensure novel exists (outside lock to avoid blocking other callers).
        if self.novels is not None:
            self.novels.get(novel_id)

        service = self._build_service_for_novel(novel_id)
        with self._lock:
            self._services[novel_id] = service
        return service

    def query_context(self, novel_id: Optional[str], **kwargs: Any) -> Dict[str, Any]:
        return self.get_service(novel_id).query_context(**kwargs)

    def respond(self, novel_id: Optional[str], **kwargs: Any) -> Dict[str, Any]:
        return self.get_service(novel_id).respond(**kwargs)

    def get_session(self, novel_id: Optional[str], session_id: str, **kwargs: Any) -> Dict[str, Any]:
        return self.get_service(novel_id).get_session(session_id, **kwargs)


def create_app(config_file: str = "config.yaml"):
    """Create FastAPI app lazily so dependency stays optional."""
    try:
        from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
        from fastapi.middleware.cors import CORSMiddleware
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

    db_path = str(base_config.get("paths", {}).get("db_path") or os.path.join(data_root, "airp2.sqlite3"))
    db = Database(path=db_path)
    db.init_schema()

    layout = StorageLayout(data_root=data_root, vector_db_root=vector_db_root, logs_root=logs_root)
    novels = NovelsService(db=db, layout=layout)

    auth_cfg = dict(base_config.get("auth", {}) or {})
    auth = AuthService(
        db=db,
        cookie_name=str(auth_cfg.get("cookie_name", "airp_sid")),
        user_session_days=int(auth_cfg.get("user_session_days", 30) or 30),
        guest_session_days=int(auth_cfg.get("guest_session_days", 30) or 30),
    )

    rp_router = MultiNovelRPQueryService(base_config=base_config, novels=novels)
    runner = PipelineRunner(base_config=base_config, novels=novels, layout=layout)

    def _on_job_update(job):
        try:
            if job.status in {"queued", "running"}:
                novels.set_processing(job.novel_id, job.job_id)
            elif job.status == "succeeded":
                novels.set_ready(job.novel_id, job.job_id, job.result or {})
                rp_router.invalidate(job.novel_id)
            elif job.status == "failed":
                novels.set_failed(job.novel_id, job.job_id, job.error)
                rp_router.invalidate(job.novel_id)
        except Exception:
            pass

    jobs = PipelineJobsService(
        db=db,
        runner=runner,
        novels=novels,
        max_concurrent_jobs=1,
        on_job_update=_on_job_update,
    )
    app = FastAPI(title="RP Query API", version="1.0.0")

    web_cfg = dict(base_config.get("web", {}) or {})
    cors_origins = list(web_cfg.get("cors_origins") or [])
    if not cors_origins:
        cors_origins = ["http://localhost:5173"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    cookie_secure = bool(auth_cfg.get("cookie_secure", False))
    cookie_samesite = str(auth_cfg.get("cookie_samesite", "lax") or "lax")

    def _set_session_cookie(response: Response, token: str, max_age_days: int) -> None:
        response.set_cookie(
            key=auth.cookie_name,
            value=str(token),
            httponly=True,
            samesite=cookie_samesite,
            secure=cookie_secure,
            path="/",
            max_age=int(max_age_days) * 24 * 60 * 60,
        )

    def _delete_session_cookie(response: Response) -> None:
        response.delete_cookie(key=auth.cookie_name, path="/")

    def get_or_create_actor(request: Request, response: Response) -> Actor:
        token = request.cookies.get(auth.cookie_name)
        actor = auth.actor_from_token(token)
        if actor is None:
            new_token, session = auth.create_guest_session()
            _set_session_cookie(response, new_token, auth.guest_session_days)
            return Actor(type="guest", guest_id=session.get("guest_id"))
        auth.touch_session(token)
        return actor

    def require_user(actor: Actor = Depends(get_or_create_actor)) -> Actor:
        if not actor.is_user:
            raise HTTPException(status_code=401, detail="login required")
        return actor

    def _session_store(actor: Actor, novel_id: Optional[str]) -> SessionStateStore:
        if actor.is_user:
            base_dir = layout.sessions_scope_dir(user_id=actor.user_id, novel_id=novel_id or None)
        else:
            guest_id = actor.guest_id or "anonymous"
            base_dir = layout.sessions_scope_dir(guest_id=guest_id, novel_id=novel_id or None)
        os.makedirs(base_dir, exist_ok=True)
        return SessionStateStore(base_dir=base_dir)

    def _assert_can_read(actor: Actor, novel_id: str) -> None:
        actor_user_id = actor.user_id if actor.is_user else None
        try:
            allowed = novels.can_read(actor_user_id=actor_user_id, novel_id=novel_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        if not allowed:
            raise HTTPException(status_code=404, detail="novel not found")

    def _assert_owner(actor: Actor, novel_id: str):
        if not actor.is_user:
            raise HTTPException(status_code=401, detail="login required")
        try:
            return novels.assert_owner(actor.user_id or "", novel_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except PermissionError:
            raise HTTPException(status_code=403, detail="forbidden")

    @app.post("/api/v1/auth/register")
    def register(payload: Dict[str, Any], response: Response):
        try:
            username = payload["username"]
            password = payload["password"]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}")
        try:
            user = auth.register(username=username, password=password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        token, _session = auth.create_user_session(user["id"])
        _set_session_cookie(response, token, auth.user_session_days)
        return {"mode": "user", "user": {"id": user["id"], "username": user["username"]}}

    @app.post("/api/v1/auth/login")
    def login(payload: Dict[str, Any], response: Response):
        try:
            username = payload["username"]
            password = payload["password"]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}")
        user = auth.authenticate(username=username, password=password)
        if not user:
            raise HTTPException(status_code=401, detail="invalid username or password")
        token, _session = auth.create_user_session(user["id"])
        _set_session_cookie(response, token, auth.user_session_days)
        return {"mode": "user", "user": {"id": user["id"], "username": user["username"]}}

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, response: Response):
        token = request.cookies.get(auth.cookie_name)
        if token:
            auth.revoke_session(token)
        _delete_session_cookie(response)
        return {"ok": True}

    @app.get("/api/v1/auth/me")
    def me(actor: Actor = Depends(get_or_create_actor)):
        if actor.is_user:
            return {"mode": "user", "user": {"id": actor.user_id, "username": actor.username}}
        return {"mode": "guest", "guest_id": actor.guest_id}

    @app.post("/api/v1/auth/guest")
    def ensure_guest(actor: Actor = Depends(get_or_create_actor)):
        # Calling this endpoint allows frontend to explicitly ensure a guest cookie exists.
        return {"mode": "guest", "guest_id": actor.guest_id}

    @app.get("/api/v1/novels")
    def list_novels(actor: Actor = Depends(require_user)):
        return novels.list_by_owner(actor.user_id or "")

    @app.post("/api/v1/novels")
    def create_novel(payload: Dict[str, Any], actor: Actor = Depends(require_user)):
        title = str(payload.get("title", "") or "")
        return novels.create(owner_user_id=actor.user_id or "", title=title)

    @app.get("/api/v1/public/novels")
    def list_public_novels():
        return novels.list_public()

    @app.get("/api/v1/public/novels/{novel_id}")
    def get_public_novel(novel_id: str):
        try:
            record = novels.get(novel_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        if record.visibility != "public":
            raise HTTPException(status_code=404, detail="novel not found")
        return record.to_public_dict()

    @app.get("/api/v1/novels/{novel_id}")
    def get_novel(novel_id: str, actor: Actor = Depends(get_or_create_actor)):
        try:
            record = novels.get(novel_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        if actor.is_user and actor.user_id == record.owner_user_id:
            return record.to_entry_dict()
        if record.visibility == "public":
            return record.to_public_dict()
        raise HTTPException(status_code=404, detail="novel not found")

    @app.patch("/api/v1/novels/{novel_id}")
    def update_novel(novel_id: str, payload: Dict[str, Any], actor: Actor = Depends(require_user)):
        try:
            return novels.update(
                owner_user_id=actor.user_id or "",
                novel_id=novel_id,
                title=payload.get("title"),
                visibility=payload.get("visibility"),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except PermissionError:
            raise HTTPException(status_code=403, detail="forbidden")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.delete("/api/v1/novels/{novel_id}")
    def delete_novel(novel_id: str, delete_vector_db: bool = False, actor: Actor = Depends(require_user)):
        try:
            novels.delete(actor.user_id or "", novel_id, delete_vector_db=bool(delete_vector_db))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except PermissionError:
            raise HTTPException(status_code=403, detail="forbidden")
        return {"deleted": True, "novel_id": novel_id}

    @app.post("/api/v1/novels/{novel_id}/upload")
    async def upload_novel(novel_id: str, actor: Actor = Depends(require_user), file: UploadFile = File(...)):
        _assert_owner(actor, novel_id)

        filename = str(getattr(file, "filename", "") or "")
        if not filename.lower().endswith(".txt"):
            raise HTTPException(status_code=400, detail="only .txt files are supported")

        paths = novels.paths(novel_id)
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

        novels.update_source_meta(actor.user_id or "", novel_id, meta)
        rp_router.invalidate(novel_id)

        return {"uploaded": True, "novel_id": novel_id, "source": meta}

    @app.get("/api/v1/novels/{novel_id}/source")
    def get_novel_source(novel_id: str, actor: Actor = Depends(require_user)):
        entry = _assert_owner(actor, novel_id).to_entry_dict()

        paths = novels.paths(novel_id)
        if not os.path.exists(paths["source_file"]):
            raise HTTPException(status_code=404, detail="source not uploaded")

        return entry.get("source", {}) or {}

    @app.get("/api/v1/novels/{novel_id}/pipeline/chapter-index")
    def get_pipeline_chapter_index(novel_id: str, actor: Actor = Depends(require_user)):
        _assert_owner(actor, novel_id)

        paths = novels.paths(novel_id)
        index_file = os.path.join(paths["chapters_dir"], "chapter_index.json")
        if not os.path.exists(index_file):
            raise HTTPException(status_code=404, detail="chapter index not found (run step1 first)")

        try:
            with open(index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"failed to read chapter index: {exc}")

    @app.post("/api/v1/novels/{novel_id}/pipeline/run")
    def run_pipeline(novel_id: str, payload: Dict[str, Any], actor: Actor = Depends(require_user)):
        _assert_owner(actor, novel_id)

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

        paths = novels.paths(novel_id)
        os.makedirs(paths["log_dir"], exist_ok=True)
        job_id = uuid.uuid4().hex
        log_path = os.path.join(paths["log_dir"], f"job_{job_id}.log")

        try:
            job = jobs.start(novel_id=novel_id, spec=spec, log_path=log_path, job_id=job_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        return job.to_dict()

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str, actor: Actor = Depends(require_user)):
        try:
            job = jobs.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        if job.owner_user_id and job.owner_user_id != (actor.user_id or ""):
            raise HTTPException(status_code=404, detail="job not found")
        return job.to_dict()

    @app.get("/api/v1/jobs/{job_id}/logs")
    def get_job_logs(job_id: str, lines: int = 200, actor: Actor = Depends(require_user)):
        lines = max(1, min(int(lines or 200), 2000))
        try:
            job = jobs.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        if job.owner_user_id and job.owner_user_id != (actor.user_id or ""):
            raise HTTPException(status_code=404, detail="job not found")
        text = jobs.tail_logs(job_id, lines=lines)
        return {"job_id": job_id, "lines": lines, "text": text}

    @app.post("/api/v1/rp/query-context")
    def query_context(payload: Dict[str, Any], actor: Actor = Depends(get_or_create_actor)):
        try:
            message = payload["message"]
            session_id = payload["session_id"]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}")

        novel_id = payload.get("novel_id")
        if novel_id:
            _assert_can_read(actor, str(novel_id))

        store = _session_store(actor, str(novel_id) if novel_id else None)
        try:
            return rp_router.query_context(
                novel_id,
                message=message,
                session_id=session_id,
                unlocked_chapter=payload.get("unlocked_chapter"),
                active_characters=payload.get("active_characters"),
                recent_messages=payload.get("recent_messages"),
                session_store=store,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/api/v1/rp/respond")
    def respond(payload: Dict[str, Any], actor: Actor = Depends(get_or_create_actor)):
        try:
            message = payload["message"]
            session_id = payload["session_id"]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}")

        novel_id = payload.get("novel_id")
        if novel_id:
            _assert_can_read(actor, str(novel_id))
        store = _session_store(actor, str(novel_id) if novel_id else None)

        # Guest/no-novel mode: allow LLM chat without RAG evidence.
        if not novel_id:
            llm_client = LLMClient(base_config)
            state = store.load(session_id, default_unlocked=int(payload.get("unlocked_chapter") or 0))
            recent = payload.get("recent_messages")
            history = recent if isinstance(recent, list) else state.turns[-10:]
            store.append_turn(state, role="user", content=str(message))
            system_prompt = "你是 AIRP 的聊天助手。无需引用证据，回答要清晰、有帮助。"
            user_prompt = "对话上下文：\n"
            for turn in history[-10:]:
                role = str(turn.get("role") or "")
                content = str(turn.get("content") or "")
                if role and content:
                    user_prompt += f"- {role}: {content}\n"
            user_prompt += f"\n用户：{message}\n助手："
            try:
                reply = llm_client.call(prompt=user_prompt, system_prompt=system_prompt, temperature=0.7)
            except Exception as exc:
                reply = f"请求失败：{exc}"
            final = str(reply)
            store.append_turn(state, role="assistant", content=final)
            store.save(state)
            return {
                "assistant_reply": final,
                "citations": [],
                "worldbook_context": {"facts": [], "character_state": [], "timeline_notes": [], "forbidden": []},
            }

        try:
            return rp_router.respond(
                novel_id,
                message=message,
                session_id=session_id,
                worldbook_context=payload.get("worldbook_context"),
                citations=payload.get("citations"),
                unlocked_chapter=payload.get("unlocked_chapter"),
                active_characters=payload.get("active_characters"),
                recent_messages=payload.get("recent_messages"),
                session_store=store,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/api/v1/rp/session/{session_id}")
    def get_session(session_id: str, novel_id: Optional[str] = None, actor: Actor = Depends(get_or_create_actor)):
        if novel_id:
            _assert_can_read(actor, str(novel_id))
        store = _session_store(actor, str(novel_id) if novel_id else None)
        try:
            return rp_router.get_session(novel_id, session_id, session_store=store)
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
