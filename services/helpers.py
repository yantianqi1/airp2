"""Shared helper functions for RP query services."""
import re
from typing import Iterable, List, Optional


STOP_WORDS = {
    "的", "了", "是", "在", "我", "你", "他", "她", "它", "我们", "你们", "他们",
    "她们", "它们", "和", "与", "及", "或", "并", "就", "都", "也", "很", "还", "吗",
    "呢", "啊", "吧", "么", "如何", "怎么", "什么", "哪个", "哪些", "这个", "那个", "这里",
    "那里", "一下", "一下子", "请", "帮", "一下", "继续", "现在", "之前", "之后",
}


def parse_chapter_no(chapter_value) -> Optional[int]:
    """Parse chapter number from payload value."""
    if chapter_value is None:
        return None

    if isinstance(chapter_value, int):
        return chapter_value

    text = str(chapter_value)
    if text.isdigit():
        return int(text)

    matched = re.search(r"(\d+)", text)
    if not matched:
        return None

    try:
        return int(matched.group(1))
    except ValueError:
        return None


def shorten_text(text: str, limit: int = 160) -> str:
    """Return shortened single-line excerpt."""
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)] + "..."


def tokenize_keywords(text: str) -> List[str]:
    """Extract coarse keywords from Chinese/ASCII mixed query text."""
    if not text:
        return []

    tokens = []

    # Chinese chunks
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if chunk not in STOP_WORDS:
            tokens.append(chunk)

    # ASCII words
    for chunk in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,}", text):
        lowered = chunk.lower()
        if lowered not in STOP_WORDS:
            tokens.append(lowered)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)

    return deduped


def normalize_entities(values: Iterable[str]) -> List[str]:
    """Deduplicate and normalize entity strings."""
    seen = set()
    entities = []
    for value in values or []:
        if value is None:
            continue
        item = str(value).strip()
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        entities.append(item)
    return entities
