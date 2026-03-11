"""PM 간 협업 요청 감지 및 발신."""
from __future__ import annotations

COLLAB_PREFIX = "🙋 도와줄 조직 찾아요!"
COLLAB_DONE_PREFIX = "✅ 협업 완료:"
COLLAB_CLAIM_PREFIX = "🤝 제가 맡을게요!"


def make_collab_request(task: str, from_org: str, context: str = "") -> str:
    """협업 요청 메시지 생성 — 맥락 포함."""
    msg = f"{COLLAB_PREFIX}\n발신: {from_org}\n요청: {task}"
    if context:
        msg += f"\n📎 맥락: {context[:400]}"
    return msg


def make_collab_claim(org_id: str) -> str:
    return f"{COLLAB_CLAIM_PREFIX} ({org_id})"


def make_collab_done(org_id: str, result_summary: str) -> str:
    return f"{COLLAB_DONE_PREFIX} [{org_id}]\n{result_summary[:500]}"


def is_collab_request(text: str) -> bool:
    return text.strip().startswith(COLLAB_PREFIX)


def is_collab_claim(text: str) -> bool:
    return text.strip().startswith(COLLAB_CLAIM_PREFIX)


def is_collab_done(text: str) -> bool:
    return text.strip().startswith(COLLAB_DONE_PREFIX)


def parse_collab_request(text: str) -> dict:
    """협업 요청 파싱 → {from_org, task, context}."""
    lines = text.strip().splitlines()
    from_org, task, context = "", "", ""
    for line in lines:
        if line.startswith("발신:"):
            from_org = line[3:].strip()
        elif line.startswith("요청:"):
            task = line[3:].strip()
        elif line.startswith("📎 맥락:"):
            context = line.split("📎 맥락:", 1)[-1].strip()
    return {"from_org": from_org, "task": task, "context": context}
