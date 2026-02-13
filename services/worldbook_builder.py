"""Build worldbook JSON payload from ranked retrieval evidence."""
from typing import Dict, List, Tuple

from .helpers import shorten_text
from .models import QueryUnderstandingResult, RetrievalCandidate, WorldbookContext


class WorldbookBuilder:
    """Assemble facts, character state, and timeline notes for RP grounding."""

    def __init__(self, max_facts: int = 8):
        self.max_facts = max_facts

    def build(
        self,
        candidates: List[RetrievalCandidate],
        query_result: QueryUnderstandingResult,
    ) -> Tuple[Dict, List[Dict]]:
        """Create worldbook context and citations array."""
        selected = candidates[: self.max_facts]
        context = WorldbookContext()
        citations: List[Dict] = []

        for item in selected:
            if item.source_type == "scene":
                fact_text = item.event_summary or item.scene_summary or shorten_text(item.text, 140)
                excerpt = shorten_text(item.text, 180)
                fact = {
                    "fact_text": fact_text,
                    "source_chapter": item.chapter,
                    "source_scene": item.scene_index,
                    "excerpt": excerpt,
                    "confidence": round(item.final_score, 4),
                }
                context.facts.append(fact)
                citations.append(
                    {
                        "source_type": "scene",
                        "source_id": item.source_id,
                        "chapter": item.chapter,
                        "scene_index": item.scene_index,
                        "chapter_title": item.chapter_title,
                        "excerpt": excerpt,
                    }
                )
            elif item.source_type == "profile":
                context.character_state.append(
                    {
                        "character": item.source_id,
                        "summary": shorten_text(item.text, 220),
                        "confidence": round(item.final_score, 4),
                    }
                )
                citations.append(
                    {
                        "source_type": "profile",
                        "source_id": item.source_id,
                        "chapter": None,
                        "scene_index": None,
                        "chapter_title": "",
                        "excerpt": shorten_text(item.text, 120),
                    }
                )

        timeline_sorted = sorted(
            [i for i in selected if i.source_type == "scene"],
            key=lambda x: (x.chapter_no or 10**9, x.scene_index or 0),
        )
        for item in timeline_sorted[: self.max_facts]:
            context.timeline_notes.append(
                {
                    "chapter": item.chapter,
                    "scene_index": item.scene_index,
                    "event": item.event_summary or item.scene_summary or shorten_text(item.text, 100),
                }
            )

        context.forbidden = [
            "禁止编造未在证据中的设定。",
            "若证据不足必须明确说明，不能强行续写事实。",
        ]

        if query_result.constraints.unlocked_chapter is not None:
            context.forbidden.append(
                f"禁止引用 chapter>{query_result.constraints.unlocked_chapter} 的信息（防剧透）。"
            )

        return context.to_dict(), citations
