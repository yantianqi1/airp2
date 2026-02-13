"""Character profile retrieval from markdown files."""
import os
from typing import Dict, List

from ..helpers import normalize_entities, shorten_text
from ..models import RetrievalCandidate


class ProfileRetriever:
    """Retrieve static role profiles as supplemental evidence."""

    def __init__(self, config: Dict):
        self.config = config
        self.profiles_dir = config["paths"].get("profiles_dir", "data/profiles")

    def query(self, entities: List[str], top_k: int = 10) -> List[RetrievalCandidate]:
        entities = normalize_entities(entities)
        if not entities:
            return []

        if not os.path.isdir(self.profiles_dir):
            return []

        files = [name for name in os.listdir(self.profiles_dir) if name.endswith(".md")]
        results: List[RetrievalCandidate] = []

        for entity in entities:
            matched_file = self._match_profile_file(entity, files)
            if not matched_file:
                continue

            profile_path = os.path.join(self.profiles_dir, matched_file)
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue

            results.append(
                RetrievalCandidate(
                    source_type="profile",
                    source_id=os.path.splitext(matched_file)[0],
                    text=content,
                    metadata={
                        "excerpt": shorten_text(content, 180),
                        "profile_path": profile_path,
                    },
                    semantic_score=0.50,
                    characters=[os.path.splitext(matched_file)[0]],
                )
            )

            if len(results) >= top_k:
                break

        return results

    def _match_profile_file(self, entity: str, files: List[str]) -> str:
        direct = f"{entity}.md"
        if direct in files:
            return direct

        for name in files:
            stem = os.path.splitext(name)[0]
            if entity in stem or stem in entity:
                return name

        return ""
