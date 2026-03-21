#!/usr/bin/env python3
"""라우팅 정확도 측정기 — LLM 호출 없이 순수 키워드 매칭으로 정확도 측정.

사용법:
    python scripts/routing_eval.py              # 전체 결과 출력
    python scripts/routing_eval.py --score-only # 점수만 출력 (0.0~1.0)
    python scripts/routing_eval.py --failures   # 실패 케이스만 출력

autoresearch 루프에서 score_before / score_after 측정에 사용됨.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.routing_keywords import BASE_DEPT_KEYWORDS, BASE_DEPT_ORDER, CORRECT_BOT_MAP  # noqa: E402

TEST_CASES_PATH = ROOT / "evals" / "routing" / "test_cases.json"


def detect_dept(text: str) -> str | None:
    """키워드 매칭으로 가장 적합한 부서 org_id 반환. 없으면 None."""
    text_lower = text.lower()
    for dept_id in BASE_DEPT_ORDER:
        keywords = BASE_DEPT_KEYWORDS.get(dept_id, [])
        if any(kw.lower() in text_lower for kw in keywords):
            return dept_id
    return None


def run_eval(verbose: bool = True, failures_only: bool = False) -> float:
    """테스트 케이스 전체 실행 후 정확도(0.0~1.0) 반환."""
    data = json.loads(TEST_CASES_PATH.read_text(encoding="utf-8"))
    test_cases = data["test_cases"]

    correct = 0
    total = len(test_cases)
    failures: list[dict] = []

    for tc in test_cases:
        inp = tc["input"]
        correct_short = tc["correct_bot"]
        expected_org = CORRECT_BOT_MAP.get(correct_short)

        predicted_org = detect_dept(inp)
        hit = predicted_org == expected_org

        if hit:
            correct += 1
        else:
            failures.append({
                "id": tc["id"],
                "input": inp,
                "expected": correct_short,
                "predicted": predicted_org or "no_match",
            })

    accuracy = correct / total if total > 0 else 0.0

    if verbose:
        if not failures_only:
            print(f"\n=== 라우팅 정확도 평가 ===")
            print(f"총 케이스: {total}")
            print(f"정답: {correct}  오답: {total - correct}")
            print(f"정확도: {accuracy:.1%}  ({accuracy:.4f})")

        if failures:
            print(f"\n--- 실패 케이스 ({len(failures)}개) ---")
            for f in failures:
                print(f"  [{f['id']}] '{f['input']}'")
                print(f"        expected={f['expected']}  predicted={f['predicted']}")

    return accuracy


def main() -> None:
    parser = argparse.ArgumentParser(description="라우팅 정확도 평가")
    parser.add_argument("--score-only", action="store_true", help="점수만 출력")
    parser.add_argument("--failures", action="store_true", help="실패 케이스만 출력")
    args = parser.parse_args()

    if args.score_only:
        score = run_eval(verbose=False)
        print(f"{score:.4f}")
    elif args.failures:
        run_eval(verbose=True, failures_only=True)
    else:
        run_eval(verbose=True)


if __name__ == "__main__":
    main()
