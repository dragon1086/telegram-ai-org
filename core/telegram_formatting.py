"""텔레그램 출력용 경량 포맷팅 유틸리티."""
from __future__ import annotations


_CONTINUATION = "…(이어짐)"  # 청크가 잘릴 때 말미에 붙는 연출 문자열


def split_message(text: str, max_len: int) -> list[str]:
    """긴 메시지를 문단/문장 경계를 우선으로 분할한다.

    2개 이상 청크로 나뉠 때 중간 청크 말미에 '…(이어짐)'을 붙여
    사용자가 내용이 이어짐을 자연스럽게 인지하도록 한다.
    """
    body = (text or "").strip()
    if not body:
        return [""]
    if len(body) <= max_len:
        return [body]

    suffix_len = len(_CONTINUATION)
    # 중간 청크는 suffix 공간을 확보해야 하므로 effective_len을 줄임
    effective_len = max_len - suffix_len

    def _find_breakpoint(chunk: str, limit: int) -> int:
        lower_bound = max(1, int(limit * 0.55))
        for token in ("\n\n", "\n- ", "\n• ", "\n", ". ", "? ", "! ", "; ", ", ", " "):
            idx = chunk.rfind(token, lower_bound, limit + 1)
            if idx != -1:
                return idx + len(token.rstrip())
        return limit

    chunks: list[str] = []
    remaining = body
    while len(remaining) > max_len:
        window = remaining[: effective_len + 1]
        cut = _find_breakpoint(window, effective_len)
        piece = remaining[:cut].rstrip()
        if not piece:
            piece = remaining[:effective_len].rstrip()
            cut = len(piece)
        chunks.append(piece + _CONTINUATION)
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
