"""PM 간 협업 요청 감지 및 발신."""
from __future__ import annotations

COLLAB_PREFIX = "🙋 도와줄 조직 찾아요!"
COLLAB_DONE_PREFIX = "✅ 협업 완료:"
COLLAB_CLAIM_PREFIX = "🤝 제가 맡을게요!"
_PLACEHOLDER_TASKS = {
    "태스크",
    "task",
    "작업",
    "할 일",
    "구체적 작업 설명",
    "출시 홍보 카피 3개 필요",
}
_PLACEHOLDER_CONTEXTS = {
    "ctx",
    "context",
    "맥락",
    "현재 작업 요약",
    "python jwt 로그인 라이브러리 v1.0, b2b 타겟",
}


def make_collab_request(task: str, from_org: str, context: str = "") -> str:
    """협업 요청 메시지 생성 — 맥락 포함."""
    msg = f"{COLLAB_PREFIX}\n발신: {from_org}\n요청: {task}"
    if context:
        msg += f"\n📎 맥락: {context[:400]}"
    return msg


def make_collab_request_v2(
    task: str,
    from_org: str,
    *,
    context: str = "",
    requester_mention: str = "",
    from_org_mention: str = "",
    target_mentions: list[str] | None = None,
) -> str:
    """협업 요청 메시지 생성 — mention/reply 친화형."""
    msg = f"{COLLAB_PREFIX}\n발신: {from_org}\n요청: {task}"
    if requester_mention:
        msg += f"\n요청자: {requester_mention}"
    if from_org_mention:
        msg += f"\n발신멘션: {from_org_mention}"
    if target_mentions:
        msg += f"\n대상조직: {' '.join(target_mentions)}"
    if context:
        msg += f"\n📎 맥락: {context[:400]}"
    return msg


def make_collab_claim(org_id: str) -> str:
    return f"{COLLAB_CLAIM_PREFIX} ({org_id})"


def make_collab_done(org_id: str, result_summary: str) -> str:
    return f"{COLLAB_DONE_PREFIX} [{org_id}]\n{result_summary[:500]}"


def is_placeholder_collab(task: str, context: str = "") -> bool:
    """프롬프트 예시/플레이스홀더로 보이는 협업 태그는 무시한다."""
    task_norm = " ".join(task.strip().lower().split())
    context_norm = " ".join(context.strip().lower().split())
    return task_norm in _PLACEHOLDER_TASKS or context_norm in _PLACEHOLDER_CONTEXTS


def is_collab_request(text: str) -> bool:
    return text.strip().startswith(COLLAB_PREFIX)


def is_collab_claim(text: str) -> bool:
    return text.strip().startswith(COLLAB_CLAIM_PREFIX)


def is_collab_done(text: str) -> bool:
    return text.strip().startswith(COLLAB_DONE_PREFIX)


def parse_collab_request(text: str) -> dict:
    """협업 요청 파싱."""
    lines = text.strip().splitlines()
    from_org, task, context = "", "", ""
    requester_mention, from_org_mention = "", ""
    target_mentions: list[str] = []
    for line in lines:
        if line.startswith("발신:"):
            from_org = line[3:].strip()
        elif line.startswith("요청:"):
            task = line[3:].strip()
        elif line.startswith("요청자:"):
            requester_mention = line.split(":", 1)[-1].strip()
        elif line.startswith("발신멘션:"):
            from_org_mention = line.split(":", 1)[-1].strip()
        elif line.startswith("대상조직:"):
            target_mentions = [part for part in line.split(":", 1)[-1].strip().split() if part]
        elif line.startswith("📎 맥락:"):
            context = line.split("📎 맥락:", 1)[-1].strip()
    return {
        "from_org": from_org,
        "task": task,
        "context": context,
        "requester_mention": requester_mention,
        "from_org_mention": from_org_mention,
        "target_mentions": target_mentions,
    }
