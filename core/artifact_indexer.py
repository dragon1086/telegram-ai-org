"""봇 산출물 → Gemini Flash 추출 → 메타데이터 인덱싱 파이프라인.

저장 완료 시점(notify_task_done 훅)에 산출물 전문을 Gemini Flash로 전달해
key entities / decisions / tags 를 추출하고,
~/.ai-org/metadata/artifact_index.jsonl 에 append 한다.

설계 원칙:
- write-time indexing: 저장 시 1회만 호출
- 실패 시 스킵 (메인 흐름 차단 금지)
- Gemini Flash (gemini-2.5-flash) 사용 — 저비용·고속
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 인덱스 파일 경로
_DEFAULT_INDEX_PATH = Path("~/.ai-org/metadata/artifact_index.jsonl").expanduser()

# Gemini 추출 프롬프트
_EXTRACT_PROMPT = """\
다음 봇 산출물 텍스트를 읽고, 아래 JSON 형식으로만 응답하라. 다른 텍스트는 절대 포함하지 말 것.

{{
  "entities": ["핵심 개념·기술·시스템 이름 목록 (최대 10개)"],
  "decisions": ["확정된 결정사항 목록 (최대 5개, 없으면 빈 배열)"],
  "tags": ["검색용 키워드 태그 목록 (최대 10개)"],
  "summary": "산출물 핵심 내용 한 줄 요약 (최대 100자)"
}}

--- 산출물 시작 ---
{artifact_text}
--- 산출물 끝 ---
"""

# 재시도 횟수
_MAX_RETRIES = 2
# 산출물 최대 길이 (Gemini Flash 컨텍스트 제한 여유값)
_ARTIFACT_MAX_CHARS = 8000


class ArtifactIndexer:
    """산출물 텍스트에서 메타데이터를 추출하고 JSONL 인덱스에 저장."""

    def __init__(
        self,
        index_path: str | Path | None = None,
        api_key: str | None = None,
    ) -> None:
        self._index_path = Path(index_path or _DEFAULT_INDEX_PATH)
        self._api_key = (
            api_key
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
        )
        self._client: Any = None
        self._genai_available = False
        self._init_client()

    def _init_client(self) -> None:
        if not self._api_key:
            logger.debug("[ArtifactIndexer] API 키 없음 — Gemini 추출 비활성화")
            return
        try:
            import google.genai as genai  # type: ignore[import]

            self._client = genai.Client(api_key=self._api_key)
            self._genai_available = True
            logger.debug("[ArtifactIndexer] Gemini 클라이언트 초기화 완료")
        except ImportError:
            logger.debug("[ArtifactIndexer] google-genai 패키지 없음 — 추출 비활성화")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def index_artifact(
        self,
        task_id: str,
        org_id: str,
        artifact_text: str,
        artifact_type: str = "task_output",
    ) -> dict | None:
        """산출물 텍스트를 인덱싱한다. 실패 시 None 반환 (메인 흐름 차단 없음).

        Args:
            task_id: 태스크 식별자 (예: T-aiorg_pm_bot-281)
            org_id: 발행 조직 (예: aiorg_engineering_bot)
            artifact_text: 산출물 전문
            artifact_type: 산출물 유형 (task_output, design_doc, report 등)

        Returns:
            저장된 메타데이터 dict 또는 None (실패/스킵 시)
        """
        if not artifact_text or not artifact_text.strip():
            return None

        try:
            extracted = await self._extract_with_retry(artifact_text)
        except Exception as exc:
            logger.warning(f"[ArtifactIndexer] 추출 실패 (스킵): {exc}")
            return None

        record = self._build_record(task_id, org_id, artifact_text, artifact_type, extracted)
        try:
            self._append_to_index(record)
        except Exception as exc:
            logger.warning(f"[ArtifactIndexer] 인덱스 저장 실패 (스킵): {exc}")
            return None

        logger.info(
            f"[ArtifactIndexer] 인덱싱 완료 — task={task_id} org={org_id} "
            f"entities={len(record.get('entities', []))} tags={len(record.get('tags', []))}"
        )
        return record

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _extract_with_retry(self, artifact_text: str) -> dict:
        """Gemini Flash로 entities/decisions/tags 추출. 실패 시 재시도."""
        if not self._genai_available or not self._client:
            # Gemini 없으면 빈 메타데이터 반환
            return {"entities": [], "decisions": [], "tags": [], "summary": ""}

        truncated = artifact_text[:_ARTIFACT_MAX_CHARS]
        prompt = _EXTRACT_PROMPT.format(artifact_text=truncated)

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    self._call_gemini(prompt),
                    timeout=30.0,
                )
                return self._parse_gemini_response(result)
            except asyncio.TimeoutError:
                last_exc = asyncio.TimeoutError("Gemini 응답 timeout (30s)")
                logger.warning(f"[ArtifactIndexer] 추출 시도 {attempt+1} timeout")
                await asyncio.sleep(1)
            except Exception as exc:
                last_exc = exc
                logger.warning(f"[ArtifactIndexer] 추출 시도 {attempt+1} 실패: {exc}")
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(1)

        raise last_exc or RuntimeError("extraction failed")

    async def _call_gemini(self, prompt: str) -> str:
        """Gemini Flash API 비동기 호출."""
        try:
            from google.genai import types  # type: ignore[import]
            response = await self._client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=512,
                ),
            )
            return response.text or ""
        except Exception:
            # types import 없이 fallback
            response = await self._client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            return response.text or ""

    @staticmethod
    def _parse_gemini_response(raw: str) -> dict:
        """Gemini 응답에서 JSON 파싱. 파싱 실패 시 빈 dict."""
        raw = raw.strip()
        # ```json ... ``` 마크다운 블록 제거
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()
        try:
            data = json.loads(raw)
            return {
                "entities": [str(e) for e in data.get("entities", [])][:10],
                "decisions": [str(d) for d in data.get("decisions", [])][:5],
                "tags": [str(t) for t in data.get("tags", [])][:10],
                "summary": str(data.get("summary", ""))[:100],
            }
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.debug(f"[ArtifactIndexer] JSON 파싱 실패: {exc} | raw={raw[:200]}")
            return {"entities": [], "decisions": [], "tags": [], "summary": ""}

    @staticmethod
    def _build_record(
        task_id: str,
        org_id: str,
        artifact_text: str,
        artifact_type: str,
        extracted: dict,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "task_id": task_id,
            "org_id": org_id,
            "artifact_type": artifact_type,
            "indexed_at": now,
            "artifact_length": len(artifact_text),
            "entities": extracted.get("entities", []),
            "decisions": extracted.get("decisions", []),
            "tags": extracted.get("tags", []),
            "summary": extracted.get("summary", ""),
            "meta_generated_by": "gemini-2.5-flash",
            "meta_confidence": 0.85,
        }

    def _append_to_index(self, record: dict) -> None:
        """메타데이터 레코드를 JSONL 파일에 append (원자적 쓰기)."""
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        # 원자적 쓰기: 임시 파일 후 rename 대신 append 모드 사용
        # (JSONL 특성상 append가 안전)
        with self._index_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


# ------------------------------------------------------------------
# 싱글턴 접근자
# ------------------------------------------------------------------

_default_indexer: ArtifactIndexer | None = None


def get_default_indexer() -> ArtifactIndexer:
    """프로세스 내 싱글턴 ArtifactIndexer를 반환한다."""
    global _default_indexer
    if _default_indexer is None:
        _default_indexer = ArtifactIndexer()
    return _default_indexer


async def index_task_artifact(
    task_id: str,
    org_id: str,
    artifact_text: str,
    artifact_type: str = "task_output",
) -> None:
    """편의 함수 — 싱글턴 인덱서로 비동기 인덱싱 실행."""
    indexer = get_default_indexer()
    await indexer.index_artifact(task_id, org_id, artifact_text, artifact_type)
