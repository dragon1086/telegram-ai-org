"""LLM 기반 실패 감지 보조 레이어.

알고리즘 방식(FailureCondition.check)이 불확실한 경계 케이스에서
Gemini 2.5 Flash를 호출하여 의미 기반 재검증을 수행한다.

하이브리드 구조:
    [Layer 1] FailureCondition.check() — <1ms
        ├── 명확한 실패/통과 → 즉시 반환
        └── 불확실 구간     → [Layer 2] LLMFailureDetector.check() 호출

판정 우선순위:
    confidence >= 0.85 → LLM 판정 채택 (override_algorithm=True 시 오버라이드)
    0.60 ~ 0.85        → 알고리즘 + LLM 모두 True일 때만 실패
    < 0.60             → 알고리즘 판정 유지

불확실 구간 조건 (is_uncertain):
    - survival_rate 0.70 ~ 0.85 구간
    - 회귀 판정이지만 new_count <= 2 (flaky 가능성)

fallback:
    Gemini API 장애/타임아웃(5s) 시 알고리즘 판정 그대로 유지.

사용법:
    detector = LLMFailureDetector()
    verdict = await detector.check(diff, algo_is_failure=False, algo_reason="")
    final_failure, final_reason = detector.apply_hybrid(
        algo_is_failure, algo_reason, verdict
    )
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

_MODEL = "gemini-2.5-flash"
_TIMEOUT_SEC = 5.0
_MAX_LOG_CHARS = 2000
_MIN_LOG_CHARS = 200  # G1 gotcha: 너무 짧은 로그는 환각 유발

# 불확실 구간 — survival_rate 이 구간에서만 LLM 호출
UNCERTAIN_SURVIVAL_LOW = 0.70
UNCERTAIN_SURVIVAL_HIGH = 0.85


# ---------------------------------------------------------------------------
# 출력 스키마
# ---------------------------------------------------------------------------

@dataclass
class LLMVerdict:
    """LLM 판정 결과.

    Fields:
        is_failure:        최종 실패 여부
        confidence:        확신도 (0.0 ~ 1.0)
        failure_type:      regression | no_improvement | pipeline_error | flaky | null
        override_algorithm: True이면 알고리즘 판정 무시 가능
        reason:            판정 근거 1~3문장
        recommended_action: retry | escalate | ignore | investigate
        evidence:          근거 목록 (최대 3건)
    """
    is_failure: bool
    confidence: float
    failure_type: str
    override_algorithm: bool
    reason: str
    recommended_action: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "is_failure": self.is_failure,
            "confidence": self.confidence,
            "failure_type": self.failure_type,
            "override_algorithm": self.override_algorithm,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# 프롬프트 템플릿
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a failure detection expert for a code self-improvement pipeline. "
    "Analyze the given ScanDiff metrics and determine if the improvement run "
    "should be classified as a failure. "
    "Respond ONLY with a valid JSON object (no markdown, no extra text)."
)

_USER_TEMPLATE = """\
## ScanDiff 지표
```json
{scan_diff_json}
```

## 알고리즘 판정
is_failure: {algo_is_failure}
reason: {algo_reason}

## 최근 로그
{recent_logs}

## 판단 기준
- regression: 신규 이슈가 해소 이슈보다 많고 지속 패턴이 있음
- flaky: CI noise 가능성 — 일시적 증가이므로 실패가 아닐 수 있음
- no_improvement: 해소 없이 baseline 그대로 유지
- pipeline_error: 실행 자체 오류
- null: 실패 패턴 없음

다음 JSON 형식으로만 응답하세요:
{{"is_failure": true/false, "confidence": 0.0-1.0, "failure_type": "regression|no_improvement|pipeline_error|flaky|null", "override_algorithm": true/false, "reason": "판정 근거 1~3문장", "recommended_action": "retry|escalate|ignore|investigate", "evidence": ["근거1", "근거2"]}}
"""


# ---------------------------------------------------------------------------
# 메인 클래스
# ---------------------------------------------------------------------------

class LLMFailureDetector:
    """Gemini 2.5 Flash 기반 실패 감지 보조 레이어.

    FailureCondition.check()의 알고리즘 판정이 불확실한 경계 케이스에서만
    호출된다. 명확한 실패/통과 케이스는 알고리즘이 처리하고, 이 클래스는
    borderline 케이스에만 개입한다.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = (
            api_key
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
        )
        self._client: Any = None
        self._available = False
        self._seen_run_ids: set[str] = set()  # G4: run_id 중복 호출 방지
        self._init_client()

    # ------------------------------------------------------------------
    # 초기화
    # ------------------------------------------------------------------

    def _init_client(self) -> None:
        if not self._api_key:
            logger.debug("[LLMFailureDetector] API 키 없음 — LLM 판정 비활성화")
            return
        try:
            import google.genai as genai  # type: ignore[import]
            self._client = genai.Client(api_key=self._api_key)
            self._available = True
            logger.debug("[LLMFailureDetector] Gemini 클라이언트 초기화 완료")
        except ImportError:
            logger.debug("[LLMFailureDetector] google-genai 패키지 없음 — 비활성화")

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def is_uncertain(self, diff: Any, algo_is_failure: bool) -> bool:
        """불확실 구간 판별 — True이면 LLM 호출이 유효하다.

        Args:
            diff: ScanDiff 인스턴스
            algo_is_failure: FailureCondition.check()의 결과

        Returns:
            True이면 LLM 재검증 필요
        """
        # 파이프라인 오류는 알고리즘 판정이 확실함
        if getattr(diff, "status", "") == "error":
            return False

        baseline = getattr(diff, "baseline_issue_count", 0)
        if baseline > 0:
            post_run = getattr(diff, "post_run_issue_count", 0)
            survival = post_run / baseline
            if UNCERTAIN_SURVIVAL_LOW < survival <= UNCERTAIN_SURVIVAL_HIGH:
                return True

        # 회귀 판정이지만 new_count 가 2 이하이면 flaky 가능성 존재
        new_count = getattr(diff, "new_count", 0)
        resolved_count = getattr(diff, "resolved_count", 0)
        if algo_is_failure and new_count <= 2 and new_count > resolved_count:
            return True

        return False

    async def check(
        self,
        diff: Any,
        algo_is_failure: bool,
        algo_reason: str,
        recent_logs: str = "",
        trigger_type: str = "algorithm_uncertain",
    ) -> LLMVerdict:
        """LLM 판정 수행.

        Args:
            diff: ScanDiff 인스턴스
            algo_is_failure: 알고리즘 판정 결과
            algo_reason: 알고리즘 판정 이유
            recent_logs: 최근 로그 (선택, 최대 2000자)
            trigger_type: 호출 유형 (로그용)

        Returns:
            LLMVerdict — fallback 시 algo 판정 그대로 래핑
        """
        run_id = getattr(diff, "run_id", "unknown")

        # G4: 동일 run_id 중복 방지
        if run_id in self._seen_run_ids:
            logger.debug(f"[LLMFailureDetector] 중복 run_id={run_id} — fallback 반환")
            return self._fallback_verdict(algo_is_failure, algo_reason)

        # G1: 로그 너무 짧으면 LLM 생략 (환각 방지)
        if recent_logs and len(recent_logs) < _MIN_LOG_CHARS:
            logger.debug("[LLMFailureDetector] 로그 너무 짧음 — LLM 생략")
            return self._fallback_verdict(algo_is_failure, algo_reason)

        if not self._available or not self._client:
            logger.debug("[LLMFailureDetector] 클라이언트 없음 — fallback")
            return self._fallback_verdict(algo_is_failure, algo_reason)

        try:
            raw = await asyncio.wait_for(
                self._call_gemini(diff, algo_is_failure, algo_reason, recent_logs),
                timeout=_TIMEOUT_SEC,  # G3: 타임아웃 필수
            )
            verdict = self._parse_verdict(raw, algo_is_failure, algo_reason)
            self._seen_run_ids.add(run_id)
            logger.info(
                f"[LLMFailureDetector] 판정 완료 — "
                f"run_id={run_id} trigger={trigger_type} "
                f"is_failure={verdict.is_failure} confidence={verdict.confidence:.2f} "
                f"type={verdict.failure_type}"
            )
            return verdict

        except asyncio.TimeoutError:
            logger.warning(
                f"[LLMFailureDetector] Gemini API 타임아웃 ({_TIMEOUT_SEC}s) "
                f"— fallback to algorithm"
            )
        except Exception as exc:
            logger.warning(f"[LLMFailureDetector] API 오류 — fallback: {exc}")

        return self._fallback_verdict(algo_is_failure, algo_reason)

    def apply_hybrid(
        self,
        algo_is_failure: bool,
        algo_reason: str,
        verdict: LLMVerdict,
    ) -> tuple[bool, str]:
        """알고리즘 + LLM 판정을 합산하여 최종 결과 반환.

        판정 우선순위:
            confidence >= 0.85 AND override_algorithm → LLM 채택
            0.60 <= confidence < 0.85               → AND 조건 (둘 다 True만 실패)
            confidence < 0.60                       → 알고리즘 유지

        Args:
            algo_is_failure: FailureCondition.check() 결과
            algo_reason: 알고리즘 판정 이유
            verdict: LLMVerdict 인스턴스

        Returns:
            (is_failure, reason) 튜플
        """
        if verdict.confidence >= 0.85 and verdict.override_algorithm:
            return verdict.is_failure, f"[LLM 채택 confidence={verdict.confidence:.2f}] {verdict.reason}"

        if verdict.confidence >= 0.60:
            combined = algo_is_failure and verdict.is_failure
            reason = (
                f"[알고리즘+LLM 합산 confidence={verdict.confidence:.2f}] "
                f"algo={algo_is_failure} llm={verdict.is_failure} → {combined}"
            )
            return combined, reason

        # confidence < 0.60: 알고리즘 판정 유지
        return algo_is_failure, algo_reason

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    async def _call_gemini(
        self,
        diff: Any,
        algo_is_failure: bool,
        algo_reason: str,
        recent_logs: str,
    ) -> str:
        """Gemini 2.5 Flash API 비동기 호출."""
        diff_dict = {
            "run_id": getattr(diff, "run_id", ""),
            "baseline_issue_count": getattr(diff, "baseline_issue_count", 0),
            "post_run_issue_count": getattr(diff, "post_run_issue_count", 0),
            "resolved_count": getattr(diff, "resolved_count", 0),
            "new_count": getattr(diff, "new_count", 0),
            "improvement_rate": getattr(diff, "improvement_rate", 0.0),
            "status": getattr(diff, "status", "unknown"),
            "new_items": getattr(diff, "new_items", [])[:5],
            "unresolved_items": getattr(diff, "unresolved_items", [])[:5],
        }

        user_content = _USER_TEMPLATE.format(
            scan_diff_json=json.dumps(diff_dict, ensure_ascii=False, indent=2),
            algo_is_failure=algo_is_failure,
            algo_reason=algo_reason,
            recent_logs=(recent_logs[:_MAX_LOG_CHARS] if recent_logs else "(없음)"),
        )

        prompt = _SYSTEM_PROMPT + "\n\n" + user_content

        try:
            from google.genai import types  # type: ignore[import]
            response = await self._client.aio.models.generate_content(
                model=_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=300,
                ),
            )
        except Exception:
            response = await self._client.aio.models.generate_content(
                model=_MODEL,
                contents=prompt,
            )

        return response.text or ""

    def _parse_verdict(
        self,
        raw: str,
        algo_is_failure: bool,
        algo_reason: str,
    ) -> LLMVerdict:
        """Gemini 응답 JSON → LLMVerdict 파싱. 실패 시 fallback."""
        raw = raw.strip()
        # 마크다운 코드블록 제거
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()

        try:
            data = json.loads(raw)
            return LLMVerdict(
                is_failure=bool(data.get("is_failure", algo_is_failure)),
                confidence=float(data.get("confidence", 0.5)),
                failure_type=str(data.get("failure_type", "null")),
                override_algorithm=bool(data.get("override_algorithm", False)),
                reason=str(data.get("reason", "")),
                recommended_action=str(data.get("recommended_action", "investigate")),
                evidence=list(data.get("evidence", [])),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(f"[LLMFailureDetector] 응답 파싱 실패: {exc} — fallback")
            return self._fallback_verdict(algo_is_failure, algo_reason)

    @staticmethod
    def _fallback_verdict(is_failure: bool, reason: str) -> LLMVerdict:
        """API 실패/타임아웃/중복 시 알고리즘 판정으로 fallback."""
        return LLMVerdict(
            is_failure=is_failure,
            confidence=0.0,
            failure_type="null",
            override_algorithm=False,
            reason=f"[fallback] {reason}",
            recommended_action="investigate" if is_failure else "ignore",
            evidence=["LLM API 불가 — 알고리즘 판정 유지"],
        )
