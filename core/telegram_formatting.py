"""텔레그램 출력용 경량 포맷팅 유틸리티."""
from __future__ import annotations


def split_message(text: str, max_len: int) -> list[str]:
    """긴 메시지를 문단/문장 경계를 우선으로 분할한다."""
    body = (text or "").strip()
    if not body:
        return [""]
    if len(body) <= max_len:
        return [body]

    def _find_breakpoint(chunk: str) -> int:
        lower_bound = max(1, int(max_len * 0.55))
        for token in ("\n\n", "\n- ", "\n• ", "\n", ". ", "? ", "! ", "; ", ", ", " "):
            idx = chunk.rfind(token, lower_bound, max_len + 1)
            if idx != -1:
                return idx + len(token.rstrip())
        return max_len

    chunks: list[str] = []
    remaining = body
    while len(remaining) > max_len:
        window = remaining[: max_len + 1]
        cut = _find_breakpoint(window)
        piece = remaining[:cut].rstrip()
        if not piece:
            piece = remaining[:max_len].rstrip()
            cut = len(piece)
        chunks.append(piece)
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
