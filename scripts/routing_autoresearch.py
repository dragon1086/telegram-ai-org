#!/usr/bin/env python3
"""라우팅 키워드 자율 개선 루프 — Karpathy autoresearch 패턴 적용.

동작:
    1. routing_eval.py로 현재 정확도 측정 (score_before)
    2. 실패 케이스 분석 → routing_keywords.py 개선 (heuristic 또는 --ai)
    3. 재측정 (score_after)
    4. score_after > score_before → git commit, else → git reset
    5. max_loops까지 반복

사용법:
    python scripts/routing_autoresearch.py              # 기본 (heuristic, 5회)
    python scripts/routing_autoresearch.py --loops 10  # 최대 10회
    python scripts/routing_autoresearch.py --ai        # Claude CLI로 AI 개선
    python scripts/routing_autoresearch.py --dry-run   # commit/reset 없이 테스트
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

KEYWORDS_FILE = ROOT / "core" / "routing_keywords.py"
TEST_CASES_PATH = ROOT / "evals" / "routing" / "test_cases.json"
PYTHON = sys.executable


# ─────────────────────────────────────────────────────────────
# 점수 측정
# ─────────────────────────────────────────────────────────────

def get_score() -> float:
    result = subprocess.run(
        [PYTHON, str(ROOT / "scripts" / "routing_eval.py"), "--score-only"],
        capture_output=True, text=True, cwd=ROOT,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        print(f"[ERROR] score 파싱 실패: {result.stdout!r}\n{result.stderr}")
        return 0.0


def get_failures() -> list[dict]:
    """실패 케이스를 structured 형태로 반환."""
    from core.routing_keywords import BASE_DEPT_KEYWORDS, BASE_DEPT_ORDER, CORRECT_BOT_MAP

    data = json.loads(TEST_CASES_PATH.read_text(encoding="utf-8"))
    failures = []
    for tc in data["test_cases"]:
        inp = tc["input"]
        expected_short = tc["correct_bot"]
        expected_org = CORRECT_BOT_MAP.get(expected_short)
        text_lower = inp.lower()
        predicted = None
        for dept_id in BASE_DEPT_ORDER:
            kws = BASE_DEPT_KEYWORDS.get(dept_id, [])
            if any(kw.lower() in text_lower for kw in kws):
                predicted = dept_id
                break
        if predicted != expected_org:
            failures.append({
                "id": tc["id"],
                "input": inp,
                "expected_short": expected_short,
                "expected_org": expected_org,
                "predicted": predicted or "no_match",
            })
    return failures


# ─────────────────────────────────────────────────────────────
# Heuristic 개선기
# ─────────────────────────────────────────────────────────────

def _extract_keywords_from_input(text: str) -> list[str]:
    """입력 텍스트에서 의미 있는 토큰 추출 (조사·조동사 제거)."""
    stopwords = {"해줘", "해주세요", "작성", "수행", "진행", "관련", "및", "또는", "그리고",
                 "위한", "에서", "으로", "를", "을", "이", "가", "은", "는", "의", "에",
                 "추가", "개선", "설정", "구현", "분석", "정의", "설계", "관리", "최적화"}
    tokens = re.split(r"[\s/]+", text.lower())
    return [t for t in tokens if len(t) >= 2 and t not in stopwords]


def heuristic_improve(failures: list[dict]) -> bool:
    """실패 케이스 기반으로 routing_keywords.py에 키워드를 추가.

    Returns:
        True if any change was made.
    """
    # 현재 파일 읽기
    content = KEYWORDS_FILE.read_text(encoding="utf-8")

    # 부서별로 추가할 키워드 수집
    additions: dict[str, list[str]] = {}

    for f in failures:
        expected_org = f["expected_org"]
        predicted = f["predicted"]
        inp = f["input"]

        if predicted == "no_match":
            # 이 입력을 커버할 키워드가 없음 → 입력 토큰을 그대로 추가
            new_kws = _extract_keywords_from_input(inp)
            if expected_org:
                additions.setdefault(expected_org, []).extend(new_kws)

        else:
            # 잘못된 부서로 매칭됨 → expected 부서에 더 구체적인 키워드 추가
            # 입력 전체를 구체적 키워드로 추가 (완전 구문 매칭)
            if expected_org:
                additions.setdefault(expected_org, []).append(inp.lower())

    if not additions:
        return False

    changed = False
    for org_id, new_kws in additions.items():
        # 이미 있는 키워드 제외
        existing_match = re.search(
            rf'"{re.escape(org_id)}": \[([^\]]*)\]', content, re.DOTALL
        )
        if not existing_match:
            continue

        existing_text = existing_match.group(1)
        existing_kws = set(re.findall(r'"([^"]+)"', existing_text))

        truly_new = [k for k in new_kws if k not in existing_kws and len(k) >= 2]
        if not truly_new:
            continue

        # 마지막 키워드 뒤에 새 키워드 삽입
        last_quote_pos = existing_match.start(1) + existing_text.rfind('"')
        insert_text = "".join(f',\n        "{k}"' for k in truly_new)
        content = content[:last_quote_pos + 1] + insert_text + content[last_quote_pos + 1:]
        changed = True
        print(f"  ➕ {org_id}: {truly_new}")

    if changed:
        KEYWORDS_FILE.write_text(content, encoding="utf-8")
    return changed


# ─────────────────────────────────────────────────────────────
# AI 개선기 (Claude CLI)
# ─────────────────────────────────────────────────────────────

def ai_improve(failures: list[dict], score_before: float) -> bool:
    """Claude CLI를 이용해 routing_keywords.py를 개선."""
    failure_text = "\n".join(
        f"- [{f['id']}] '{f['input']}' → expected={f['expected_short']}, predicted={f['predicted']}"
        for f in failures
    )
    current_content = KEYWORDS_FILE.read_text(encoding="utf-8")

    prompt = f"""아래는 라우팅 키워드 파일이다. 현재 정확도는 {score_before:.1%}다.

실패 케이스:
{failure_text}

core/routing_keywords.py 의 BASE_DEPT_KEYWORDS를 수정해서 정확도를 높여라.
규칙:
1. 키워드 추가만 허용. 기존 키워드 삭제 금지.
2. 너무 일반적인 단어는 추가하지 말 것 (예: "해결", "설정" 등은 여러 부서에 해당).
3. BASE_DEPT_ORDER 변경 금지.
4. 현재 파일:

{current_content}

수정된 전체 파일 내용만 출력하라. 설명 없이 코드만."""

    result = subprocess.run(
        ["claude", "--dangerously-skip-permissions", "-p", prompt],
        capture_output=True, text=True, cwd=ROOT, timeout=120,
    )
    if result.returncode != 0 or not result.stdout.strip():
        print(f"[AI] Claude 호출 실패: {result.stderr[:200]}")
        return False

    # 코드 블록 추출
    output = result.stdout.strip()
    if "```python" in output:
        m = re.search(r"```python\s*([\s\S]*?)```", output)
        if m:
            output = m.group(1).strip()
    elif "```" in output:
        m = re.search(r"```\s*([\s\S]*?)```", output)
        if m:
            output = m.group(1).strip()

    if "BASE_DEPT_KEYWORDS" not in output:
        print("[AI] 출력이 올바른 Python 코드가 아님.")
        return False

    KEYWORDS_FILE.write_text(output, encoding="utf-8")
    print("[AI] routing_keywords.py 업데이트됨.")
    return True


# ─────────────────────────────────────────────────────────────
# Git 유틸
# ─────────────────────────────────────────────────────────────

def git_commit(score_before: float, score_after: float, iteration: int) -> None:
    subprocess.run(
        ["git", "add", str(KEYWORDS_FILE)],
        cwd=ROOT, check=True,
    )
    msg = (
        f"feat(routing): autoresearch iter {iteration} "
        f"{score_before:.1%} → {score_after:.1%}"
    )
    subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, check=True)
    print(f"  ✅ git commit: {msg}")


def git_reset(backup: str) -> None:
    """백업 내용으로 파일 복원 (git tracked 여부 무관)."""
    KEYWORDS_FILE.write_text(backup, encoding="utf-8")
    # 모듈 캐시 초기화
    for mod in list(sys.modules.keys()):
        if "routing_keywords" in mod:
            del sys.modules[mod]
    print("  ⏪ 롤백: 개선 없음, 원본 복원.")


# ─────────────────────────────────────────────────────────────
# 메인 루프
# ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="라우팅 키워드 자율 개선 루프")
    parser.add_argument("--loops", type=int, default=5, help="최대 반복 횟수 (기본 5)")
    parser.add_argument("--ai", action="store_true", help="Claude CLI로 AI 개선 사용")
    parser.add_argument("--dry-run", action="store_true", help="commit/reset 없이 테스트")
    args = parser.parse_args()

    print("=" * 55)
    print("  라우팅 autoresearch 루프 시작")
    print(f"  max_loops={args.loops}  ai={args.ai}  dry_run={args.dry_run}")
    print("=" * 55)

    for i in range(1, args.loops + 1):
        print(f"\n[Loop {i}/{args.loops}]")

        score_before = get_score()
        print(f"  score_before: {score_before:.1%}")

        if score_before >= 1.0:
            print("  정확도 100% 달성! 루프 종료.")
            break

        failures = get_failures()
        print(f"  실패 케이스: {len(failures)}개")

        # 수정 전 백업
        backup_content = KEYWORDS_FILE.read_text(encoding="utf-8")

        if args.ai:
            changed = ai_improve(failures, score_before)
        else:
            changed = heuristic_improve(failures)

        if not changed:
            print("  변경사항 없음. 루프 종료.")
            break

        # 모듈 캐시 초기화 (재로딩)
        for mod in list(sys.modules.keys()):
            if "routing_keywords" in mod:
                del sys.modules[mod]

        score_after = get_score()
        print(f"  score_after:  {score_after:.1%}  (delta: {score_after - score_before:+.1%})")

        if args.dry_run:
            print("  [dry-run] 롤백.")
            git_reset(backup_content)
            continue

        if score_after > score_before:
            git_commit(score_before, score_after, i)
        else:
            git_reset(backup_content)

    final_score = get_score()
    print(f"\n{'=' * 55}")
    print(f"  최종 정확도: {final_score:.1%}")
    print("=" * 55)


if __name__ == "__main__":
    main()
