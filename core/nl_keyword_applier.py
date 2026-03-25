"""nl_classifier.py에 키워드를 안전하게 추가."""
from __future__ import annotations

import re
from pathlib import Path

from loguru import logger


class NLKeywordApplier:
    def __init__(self) -> None:
        self._path = Path(__file__).parent / "nl_classifier.py"

    def apply(self, keyword_additions: dict[str, list[str]]) -> str:
        """dept → keywords 맵을 nl_classifier.py에 추가."""
        if not self._path.exists():
            return "nl_classifier.py 없음"
        text = self._path.read_text(encoding="utf-8")
        applied = []
        for dept, keywords in keyword_additions.items():
            for kw in keywords:
                if kw in text:
                    continue
                # dept 블록을 찾아 첫 번째 요소 앞에 삽입
                pattern = rf'("{dept}"[^[]*\[)'
                match = re.search(pattern, text)
                if match:
                    insert_pos = match.end()
                    text = text[:insert_pos] + f'"{kw}", ' + text[insert_pos:]
                    applied.append(f"{dept}: +{kw}")
        if applied:
            self._path.write_text(text, encoding="utf-8")
            logger.info(f"[NLKeywordApplier] 적용: {applied}")
            return "\n".join(applied)
        return "추가할 신규 키워드 없음"
