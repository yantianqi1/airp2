"""Guardrail utilities for spoiler and hallucination control."""
from typing import Dict, List, Optional

from .helpers import parse_chapter_no
from .models import QueryUnderstandingResult, RetrievalCandidate


class Guardrails:
    """Apply spoiler filtering and response constraints."""

    def filter_spoilers(
        self,
        candidates: List[RetrievalCandidate],
        unlocked_chapter: Optional[int],
    ) -> List[RetrievalCandidate]:
        """Remove candidates beyond unlocked chapter boundary."""
        if unlocked_chapter is None:
            return list(candidates)

        filtered = []
        for candidate in candidates:
            if candidate.source_type != "scene":
                filtered.append(candidate)
                continue

            chapter_no = candidate.chapter_no
            if chapter_no is None:
                chapter_no = parse_chapter_no(candidate.chapter)

            # If chapter index is unknown, keep as conservative compatibility behavior.
            if chapter_no is None or chapter_no <= unlocked_chapter:
                filtered.append(candidate)

        return filtered

    def has_enough_evidence(self, citations: List[Dict]) -> bool:
        return len(citations or []) > 0

    def build_insufficient_evidence_reply(self, query: QueryUnderstandingResult) -> str:
        if query.intent == "next_action":
            return "当前知识库没有检索到足够证据支撑下一步建议，请补充角色、地点或章节范围后重试。"
        return "未检索到明确证据，建议补充角色名、地点或更具体的事件关键词。"

    def build_grounding_system_prompt(self) -> str:
        """System prompt that enforces citation-grounded response behavior."""
        return (
            "你是角色扮演剧情助手。\n"
            "规则：\n"
            "1) 只能基于给定 worldbook_context 里的 facts 和 character_state 回答。\n"
            "2) 不得编造未在证据中出现的事实。\n"
            "3) 重要断言必须引用来源。\n"
            "4) 若证据不足，直接说明证据不足，并提出需要补充的信息。"
        )

    def compose_grounding_prompt(self, user_message: str, worldbook_context: Dict) -> str:
        """Compose user prompt for final response generation."""
        return (
            "以下是检索到的 worldbook_context（JSON）：\n"
            f"{worldbook_context}\n\n"
            "请根据以上信息回复玩家，并在末尾附上 citations 数组中的关键来源。\n"
            f"玩家消息：{user_message}"
        )

    def append_citation_footer(self, reply: str, citations: List[Dict]) -> str:
        """Attach compact citation footer if model reply forgot to mention sources."""
        if not citations:
            return reply

        lines = []
        for item in citations[:3]:
            chapter = item.get("chapter") or "unknown"
            scene = item.get("scene_index")
            if scene is None:
                lines.append(f"- {chapter}")
            else:
                lines.append(f"- {chapter} / scene {scene}")

        footer = "\n\n参考来源:\n" + "\n".join(lines)
        if "参考来源" in reply or "citation" in reply.lower():
            return reply
        return reply + footer
