"""Rule-based query understanding for RP retrieval."""
import json
import os
import re
from typing import Dict, List, Optional, Tuple

from .helpers import normalize_entities, tokenize_keywords
from .models import QueryConstraints, QueryUnderstandingResult
from .session_state import SessionState


LOCATION_PATTERN = re.compile(
    r"[\u4e00-\u9fff]{1,10}(?:城|府|宫|寺|山|谷|楼|馆|堂|门|营|州|郡|村|镇|客栈|书院|牢房|驿站)"
)


class QueryUnderstandingService:
    """Extract intent/entities/constraints from conversation input."""

    def __init__(self, config: Dict):
        self.config = config
        self.profiles_dir = config.get("paths", {}).get("profiles_dir", "data/profiles")
        self.annotated_dir = config.get("paths", {}).get("annotated_dir", "data/annotated")

        self.intent_rules: List[Tuple[str, List[str]]] = [
            ("character_relation", ["关系", "什么关系", "谁和谁", "是否认识", "立场"]),
            ("location_query", ["在哪", "哪里", "地点", "去过", "位于", "方位"]),
            ("canon_check", ["设定", "依据", "证据", "原文", "真实吗", "是否属实"]),
            ("next_action", ["下一步", "接下来", "怎么办", "如何行动", "建议"]),
            ("story_recap", ["回顾", "总结", "之前", "经过", "复盘", "发生了什么"]),
        ]

        self.character_names, self.alias_to_canonical = self._load_character_dictionary()

    def understand(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        session_state: Optional[SessionState] = None,
        unlocked_chapter: Optional[int] = None,
        active_characters: Optional[List[str]] = None,
    ) -> QueryUnderstandingResult:
        """Parse one user query into a structured representation."""
        history = history or []
        session_state = session_state or SessionState(session_id="")
        text = str(message or "").strip()

        intent = self._detect_intent(text)
        entities = self._extract_entities(text, history, session_state, active_characters)
        locations = self._extract_locations(text)
        event_keywords = tokenize_keywords(text)

        effective_unlocked = unlocked_chapter
        if effective_unlocked is None:
            effective_unlocked = session_state.max_unlocked_chapter

        constraints = QueryConstraints(
            unlocked_chapter=effective_unlocked,
            active_characters=normalize_entities(active_characters or session_state.active_characters),
            location_hints=locations,
        )

        normalized_query = text
        if history:
            recent_messages = [item.get("content", "") for item in history[-3:]]
            normalized_query = "\n".join([*recent_messages, text]).strip()

        return QueryUnderstandingResult(
            intent=intent,
            normalized_query=normalized_query,
            entities=entities,
            locations=locations,
            event_keywords=event_keywords,
            constraints=constraints,
        )

    def _detect_intent(self, text: str) -> str:
        lowered = text.lower()
        for intent, keywords in self.intent_rules:
            for keyword in keywords:
                if keyword in text or keyword in lowered:
                    return intent
        return "story_recap"

    def _extract_entities(
        self,
        text: str,
        history: List[Dict[str, str]],
        session_state: SessionState,
        active_characters: Optional[List[str]],
    ) -> List[str]:
        matched = []

        for alias, canonical in self.alias_to_canonical.items():
            if alias and alias in text:
                matched.append(canonical)

        if not matched:
            # Fallback to direct canonical name match.
            for name in self.character_names:
                if name and name in text:
                    matched.append(name)

        if not matched and active_characters:
            matched.extend(active_characters)

        if not matched and session_state.active_characters:
            matched.extend(session_state.active_characters)

        if not matched and history:
            history_text = "\n".join(item.get("content", "") for item in history[-4:])
            for alias, canonical in self.alias_to_canonical.items():
                if alias and alias in history_text:
                    matched.append(canonical)

        return normalize_entities(matched)

    def _extract_locations(self, text: str) -> List[str]:
        return normalize_entities(LOCATION_PATTERN.findall(text))

    def _load_character_dictionary(self) -> Tuple[List[str], Dict[str, str]]:
        names = []
        alias_map: Dict[str, str] = {}

        # Profiles directory -> canonical names.
        if os.path.isdir(self.profiles_dir):
            for filename in os.listdir(self.profiles_dir):
                if not filename.endswith(".md"):
                    continue
                canonical = os.path.splitext(filename)[0].strip()
                if canonical:
                    names.append(canonical)
                    alias_map[canonical] = canonical

        # Optional alias map exported by step3.
        name_map_file = os.path.join(self.annotated_dir, "character_name_map.json")
        if os.path.exists(name_map_file):
            try:
                with open(name_map_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for canonical, aliases in data.items():
                        canonical_name = str(canonical).strip()
                        if not canonical_name:
                            continue
                        names.append(canonical_name)
                        alias_map[canonical_name] = canonical_name
                        if isinstance(aliases, list):
                            for alias in aliases:
                                alias_name = str(alias).strip()
                                if alias_name:
                                    alias_map[alias_name] = canonical_name
            except Exception:
                # Keep service resilient if user-edited map has bad format.
                pass

        names = normalize_entities(names)
        for name in names:
            alias_map.setdefault(name, name)

        return names, alias_map
