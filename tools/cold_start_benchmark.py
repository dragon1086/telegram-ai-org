#!/usr/bin/env python3
"""
cold_start_benchmark.py — 모듈별 import 시간 측정 (ms)

Cold-start import time benchmark for telegram-ai-org dependencies.
엔진 SDK 등 무거운 패키지의 import 비용을 측정해 경량화 우선순위를 결정한다.

사용법:
    python tools/cold_start_benchmark.py
    python tools/cold_start_benchmark.py --json
    python tools/cold_start_benchmark.py --include-project
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from typing import Optional

# ─── 측정 대상 모듈 목록 ──────────────────────────────────────────────────────
# (module_name, pip_package_name) 튜플
MODULES_TO_BENCHMARK: list[tuple[str, str]] = [
    # Third-party: 핵심 의존성
    ("telegram", "python-telegram-bot"),
    ("pydantic", "pydantic"),
    ("aiosqlite", "aiosqlite"),
    ("dotenv", "python-dotenv"),
    ("loguru", "loguru"),
    ("yaml", "PyYAML"),
    ("apscheduler", "apscheduler"),
    ("rank_bm25", "rank-bm25"),
    ("mcp", "mcp"),
    # Engine SDK: optional 의존성
    ("anthropic", "anthropic"),
    ("openai", "openai"),
    ("google.genai", "google-genai"),
]

PROJECT_MODULES: list[tuple[str, str]] = [
    ("core", "core"),
    ("telegram_ai_org", "telegram_ai_org"),
]

BenchmarkResult = dict[str, object]


def benchmark_import(module_name: str) -> tuple[float, Optional[str]]:
    """모듈 하나의 import 시간을 측정한다.

    캐시 오염 방지를 위해 측정 전 sys.modules 에서 해당 모듈을 제거한다.

    Returns:
        (time_ms, error_message)
        time_ms = -1.0  import 실패 시
    """
    mods_to_evict = [
        k for k in sys.modules
        if k == module_name or k.startswith(module_name + ".")
    ]
    for mod in mods_to_evict:
        del sys.modules[mod]

    start = time.perf_counter()
    try:
        importlib.import_module(module_name)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return elapsed_ms, None
    except ImportError as exc:
        return -1.0, str(exc)
    except Exception as exc:  # pragma: no cover
        return -1.0, f"ERROR: {exc}"


def run_benchmarks(modules: list[tuple[str, str]]) -> list[BenchmarkResult]:
    """지정된 모듈 목록 전체를 순차 측정한다."""
    results: list[BenchmarkResult] = []
    for module_name, package_name in modules:
        time_ms, err = benchmark_import(module_name)
        results.append(
            {
                "module": module_name,
                "package": package_name,
                "time_ms": round(time_ms, 2),
                "available": time_ms >= 0,
                "error": err,
            }
        )
    return results


def print_table(results: list[BenchmarkResult], title: str = "") -> None:
    """측정 결과를 ASCII 테이블로 출력한다."""
    if title:
        print(f"\n{'=' * 70}")
        print(f"  {title}")
        print(f"{'=' * 70}")

    print(f"{'Module':<35} {'Package':<22} {'ms':>8}  Status")
    print("-" * 70)

    for r in results:
        mod: str = str(r["module"])
        pkg: str = str(r["package"])
        if r["available"]:
            status = "OK"
            time_str = f"{r['time_ms']:>8.1f}"
        else:
            status = f"SKIP  ({r['error']})"[:30]
            time_str = f"{'N/A':>8}"
        print(f"{mod:<35} {pkg:<22} {time_str}  {status}")

    available = [r for r in results if r["available"]]
    if available:
        total = sum(float(str(r["time_ms"])) for r in available)
        print("-" * 70)
        print(f"{'TOTAL (available)':<35} {'':<22} {total:>8.1f}")

        top5 = sorted(available, key=lambda x: float(str(x["time_ms"])), reverse=True)[:5]
        print("\nTop 5 slowest:")
        for r in top5:
            print(f"  {str(r['module']):<35} {float(str(r['time_ms'])):>8.1f} ms")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="모듈 cold-start import 시간 벤치마크 (telegram-ai-org)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    parser.add_argument(
        "--include-project",
        action="store_true",
        help="프로젝트 내부 모듈(core, telegram_ai_org)도 측정",
    )
    args = parser.parse_args()

    all_modules = MODULES_TO_BENCHMARK[:]
    if args.include_project:
        all_modules += PROJECT_MODULES

    results = run_benchmarks(all_modules)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_table(results, "Cold-start Import Benchmark — telegram-ai-org")


if __name__ == "__main__":
    main()
