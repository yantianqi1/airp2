"""RP query service and optional FastAPI endpoints."""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from services.guardrails import Guardrails
from services.query_understanding import QueryUnderstandingService
from services.retrieval_orchestrator import RetrievalOrchestrator
from services.session_state import SessionStateStore
from services.worldbook_builder import WorldbookBuilder
from utils.llm_client import LLMClient


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
        self.session_store = session_store or SessionStateStore(base_dir="/app/data/sessions")
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


def create_app(config_file: str = "config.yaml"):
    """Create FastAPI app lazily so dependency stays optional."""
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import FileResponse
    except ImportError as exc:  # pragma: no cover - optional runtime path
        raise RuntimeError(
            "FastAPI is not installed. Install with `pip install fastapi uvicorn`."
        ) from exc

    service = RPQueryService.from_config_file(config_file)
    app = FastAPI(title="RP Query API", version="1.0.0")

    @app.post("/api/v1/rp/query-context")
    def query_context(payload: Dict[str, Any]):
        try:
            message = payload["message"]
            session_id = payload["session_id"]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}")

        return service.query_context(
            message=message,
            session_id=session_id,
            unlocked_chapter=payload.get("unlocked_chapter"),
            active_characters=payload.get("active_characters"),
            recent_messages=payload.get("recent_messages"),
        )

    @app.post("/api/v1/rp/respond")
    def respond(payload: Dict[str, Any]):
        try:
            message = payload["message"]
            session_id = payload["session_id"]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}")

        return service.respond(
            message=message,
            session_id=session_id,
            worldbook_context=payload.get("worldbook_context"),
            citations=payload.get("citations"),
            unlocked_chapter=payload.get("unlocked_chapter"),
            active_characters=payload.get("active_characters"),
            recent_messages=payload.get("recent_messages"),
        )

    @app.get("/api/v1/rp/session/{session_id}")
    def get_session(session_id: str):
        return service.get_session(session_id)

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
