"""토론 메시지 파서 — [PROPOSE:], [COUNTER:] 등 태그 감지·파싱."""
from __future__ import annotations

import re
from dataclasses import dataclass

VALID_MSG_TYPES = {"PROPOSE", "COUNTER", "OPINION", "REVISE", "DECISION"}

# [TYPE:topic|content] 형식 — content는 여러 줄 가능
_DISCUSSION_TAG_RE = re.compile(
    r'\[(' + '|'.join(VALID_MSG_TYPES) + r'):([^|\]]+)\|([^\]]+)\]',
    re.DOTALL,
)


@dataclass
class DiscussionTag:
    """파싱된 토론 태그."""
    msg_type: str   # PROPOSE, COUNTER, OPINION, REVISE, DECISION
    topic: str
    content: str


def parse_discussion_tags(text: str) -> list[DiscussionTag]:
    """텍스트에서 모든 토론 태그를 추출.

    Returns:
        파싱된 DiscussionTag 리스트. 토론 태그 없으면 빈 리스트.
    """
    results: list[DiscussionTag] = []
    for match in _DISCUSSION_TAG_RE.finditer(text):
        msg_type = match.group(1).strip()
        topic = match.group(2).strip()
        content = match.group(3).strip()
        results.append(DiscussionTag(msg_type=msg_type, topic=topic, content=content))
    return results


def is_discussion_message(text: str) -> bool:
    """토론 태그가 포함된 메시지인지 판별."""
    return bool(_DISCUSSION_TAG_RE.search(text))


def strip_discussion_tags(text: str) -> str:
    """토론 태그를 제거한 텍스트 반환."""
    return _DISCUSSION_TAG_RE.sub('', text).strip()
