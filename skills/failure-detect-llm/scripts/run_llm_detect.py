#!/usr/bin/env python3
"""failure-detect-llm 스킬 실행기.

ScanDiff JSON을 stdin 또는 파일로 받아 LLMFailureDetector를 실행하고
최종 판정 결과를 JSON으로 출력한다.

사용법:
    # stdin으로 ScanDiff JSON 전달
    echo '{"run_id": "abc123", ...}' | python skills/failure-detect-llm/scripts/run_llm_detect.py

    # 파일로 전달
    python skills/failure-detect-llm/scripts/run_llm_detect.py --diff-file path/to/comparison.json

    # 알고리즘 판정 결과와 함께 전달
    python skills/failure-detect-llm/scripts/run_llm_detect.py \\
        --diff-file comparison.json \\
        --algo-failure true \\
        --algo-reason "회귀: new_count > resolved_count" \\
        --recent-logs "last 100 lines..."
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from dataclasses import dataclass, field

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from loguru import logger
from core.llm_failure_detector import LLMFailureDetector


# ---------------------------------------------------------------------------
# 헬퍼: dict → ScanDiff-like 객체
# ---------------------------------------------------------------------------

@dataclass
class _DiffProxy:
    """dict로부터 ScanDiff 인터페이스를 제공하는 프록시."""
    run_id: str = ""
    baseline_issue_count: int = 0
    post_run_issue_count: int = 0
    resolved_count: int = 0
    new_count: int = 0
    improvement_rate: float = 0.0
    status: str = "unchanged"
    new_items: list = field(default_factory=list)
    unresolved_items: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "_DiffProxy":
        return cls(
            run_id=str(d.get("run_id", "")),
            baseline_issue_count=int(d.get("baseline_issue_count", 0)),
            post_run_issue_count=int(d.get("post_run_issue_count", 0)),
            resolved_count=int(d.get("resolved_count", 0)),
            new_count=int(d.get("new_count", 0)),
            improvement_rate=float(d.get("improvement_rate", 0.0)),
            status=str(d.get("status", "unchanged")),
            new_items=list(d.get("new_items", [])),
            unresolved_items=list(d.get("unresolved_items", [])),
        )


# ---------------------------------------------------------------------------
# 메인 로직
# ---------------------------------------------------------------------------

async def main() -> int:
    parser = argparse.ArgumentParser(description="failure-detect-llm 스킬 실행기")
    parser.add_argument("--diff-file", type=str, help="ScanDiff JSON 파일 경로")
    parser.add_argument(
        "--algo-failure",
        type=str,
        default="false",
        help="알고리즘 판정 결과 (true/false, 기본: false)",
    )
    parser.add_argument(
        "--algo-reason",
        type=str,
        default="",
        help="알고리즘 판정 이유",
    )
    parser.add_argument(
        "--recent-logs",
        type=str,
        default="",
        help="최근 로그 문자열 (선택)",
    )
    parser.add_argument(
        "--trigger-type",
        type=str,
        default="algorithm_uncertain",
        choices=["algorithm_uncertain", "regressed", "repeated_fail"],
        help="호출 트리거 유형",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="불확실 구간이 아니어도 LLM 호출 강제 실행",
    )
    args = parser.parse_args()

    # ScanDiff 로드
    if args.diff_file:
        diff_path = Path(args.diff_file)
        if not diff_path.exists():
            logger.error(f"파일을 찾을 수 없음: {diff_path}")
            return 1
        diff_dict = json.loads(diff_path.read_text(encoding="utf-8"))
    elif not sys.stdin.isatty():
        diff_dict = json.loads(sys.stdin.read())
    else:
        logger.error("--diff-file 또는 stdin으로 ScanDiff JSON을 전달하세요.")
        return 1

    diff = _DiffProxy.from_dict(diff_dict)
    algo_is_failure = args.algo_failure.lower() in ("true", "1", "yes")

    detector = LLMFailureDetector()

    # 불확실 구간 확인
    uncertain = detector.is_uncertain(diff, algo_is_failure)
    if not uncertain and not args.force:
        logger.info(
            f"[failure-detect-llm] 불확실 구간 아님 (is_uncertain=False) "
            f"— 알고리즘 판정 유지 (--force 옵션으로 강제 실행 가능)"
        )
        result = {
            "skipped": True,
            "reason": "not_uncertain_range",
            "algo_is_failure": algo_is_failure,
            "algo_reason": args.algo_reason,
            "final_is_failure": algo_is_failure,
            "final_reason": args.algo_reason,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # LLM 판정
    verdict = await detector.check(
        diff=diff,
        algo_is_failure=algo_is_failure,
        algo_reason=args.algo_reason,
        recent_logs=args.recent_logs,
        trigger_type=args.trigger_type,
    )

    # 하이브리드 최종 판정
    final_failure, final_reason = detector.apply_hybrid(
        algo_is_failure=algo_is_failure,
        algo_reason=args.algo_reason,
        verdict=verdict,
    )

    result = {
        "skipped": False,
        "is_uncertain": uncertain,
        "trigger_type": args.trigger_type,
        "algo_is_failure": algo_is_failure,
        "algo_reason": args.algo_reason,
        "llm_verdict": verdict.to_dict(),
        "final_is_failure": final_failure,
        "final_reason": final_reason,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if final_failure else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
