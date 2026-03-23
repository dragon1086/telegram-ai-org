"""ArtifactIndexer 단위 테스트.

검증 항목:
1. Gemini 응답 JSON 파싱 정확도
2. JSONL 인덱스 저장 및 필드 확인
3. Gemini 없는 환경에서 빈 메타데이터 처리
4. API 실패 시 스킵 동작
5. 긴 산출물 2000자 truncation
6. 샘플 실 데이터 entities/tags 추출 품질 검증
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.artifact_indexer import ArtifactIndexer


# ------------------------------------------------------------------
# 공통 픽스처
# ------------------------------------------------------------------

@pytest.fixture
def tmp_index(tmp_path):
    """임시 JSONL 인덱스 파일 경로."""
    return tmp_path / "artifact_index.jsonl"


@pytest.fixture
def indexer_no_gemini(tmp_index):
    """Gemini API 키 없는 인덱서 (추출 비활성화)."""
    return ArtifactIndexer(index_path=tmp_index, api_key=None)


@pytest.fixture
def indexer_with_gemini(tmp_index):
    """Gemini API 키가 있는 인덱서 (mock 사용)."""
    return ArtifactIndexer(index_path=tmp_index, api_key="fake-api-key")


# ------------------------------------------------------------------
# 파싱 테스트
# ------------------------------------------------------------------

class TestParseGeminiResponse:
    def test_valid_json(self):
        raw = json.dumps({
            "entities": ["Gemini Flash", "메타데이터", "YAML"],
            "decisions": ["blk-1 선택", "valid_until 필드 필수화"],
            "tags": ["memory", "indexing", "gemini"],
            "summary": "봇 산출물 메타데이터 추출 파이프라인 설계 완료",
        })
        result = ArtifactIndexer._parse_gemini_response(raw)
        assert result["entities"] == ["Gemini Flash", "메타데이터", "YAML"]
        assert result["decisions"] == ["blk-1 선택", "valid_until 필드 필수화"]
        assert result["tags"] == ["memory", "indexing", "gemini"]
        assert "봇 산출물" in result["summary"]

    def test_markdown_code_block_stripped(self):
        """```json ... ``` 마크다운 블록 제거."""
        raw = '```json\n{"entities": ["A"], "decisions": [], "tags": ["x"], "summary": "s"}\n```'
        result = ArtifactIndexer._parse_gemini_response(raw)
        assert result["entities"] == ["A"]

    def test_invalid_json_returns_empty(self):
        result = ArtifactIndexer._parse_gemini_response("이건 JSON이 아닙니다")
        assert result["entities"] == []
        assert result["decisions"] == []
        assert result["tags"] == []
        assert result["summary"] == ""

    def test_entities_capped_at_10(self):
        raw = json.dumps({
            "entities": [f"e{i}" for i in range(20)],
            "decisions": [],
            "tags": [],
            "summary": "",
        })
        result = ArtifactIndexer._parse_gemini_response(raw)
        assert len(result["entities"]) == 10

    def test_decisions_capped_at_5(self):
        raw = json.dumps({
            "entities": [],
            "decisions": [f"d{i}" for i in range(10)],
            "tags": [],
            "summary": "",
        })
        result = ArtifactIndexer._parse_gemini_response(raw)
        assert len(result["decisions"]) == 5

    def test_summary_capped_at_100(self):
        raw = json.dumps({
            "entities": [],
            "decisions": [],
            "tags": [],
            "summary": "A" * 200,
        })
        result = ArtifactIndexer._parse_gemini_response(raw)
        assert len(result["summary"]) == 100


# ------------------------------------------------------------------
# 인덱스 저장 테스트
# ------------------------------------------------------------------

class TestIndexStorage:
    def test_record_written_to_jsonl(self, indexer_no_gemini, tmp_index):
        """Gemini 없어도 JSONL에 레코드가 저장되어야 함."""
        record = ArtifactIndexer._build_record(
            task_id="T-test-001",
            org_id="aiorg_engineering_bot",
            artifact_text="테스트 산출물",
            artifact_type="task_output",
            extracted={"entities": ["테스트"], "decisions": [], "tags": ["test"], "summary": "요약"},
        )
        indexer_no_gemini._append_to_index(record)

        assert tmp_index.exists()
        lines = tmp_index.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        loaded = json.loads(lines[0])
        assert loaded["task_id"] == "T-test-001"
        assert loaded["org_id"] == "aiorg_engineering_bot"
        assert loaded["entities"] == ["테스트"]
        assert loaded["tags"] == ["test"]

    def test_multiple_records_appended(self, indexer_no_gemini, tmp_index):
        """여러 레코드가 순서대로 append 되어야 함."""
        for i in range(3):
            record = ArtifactIndexer._build_record(
                task_id=f"T-test-{i:03d}",
                org_id="aiorg_engineering_bot",
                artifact_text=f"산출물 {i}",
                artifact_type="task_output",
                extracted={"entities": [], "decisions": [], "tags": [], "summary": ""},
            )
            indexer_no_gemini._append_to_index(record)

        lines = tmp_index.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        for i, line in enumerate(lines):
            data = json.loads(line)
            assert data["task_id"] == f"T-test-{i:03d}"

    def test_record_has_required_fields(self, tmp_index):
        record = ArtifactIndexer._build_record(
            task_id="T-x",
            org_id="org",
            artifact_text="abc",
            artifact_type="report",
            extracted={"entities": [], "decisions": [], "tags": [], "summary": ""},
        )
        required = ["task_id", "org_id", "artifact_type", "indexed_at",
                    "artifact_length", "entities", "decisions", "tags",
                    "summary", "meta_generated_by", "meta_confidence"]
        for field in required:
            assert field in record, f"필드 누락: {field}"


# ------------------------------------------------------------------
# 비동기 index_artifact 테스트
# ------------------------------------------------------------------

class TestIndexArtifactAsync:
    @pytest.mark.asyncio
    async def test_no_gemini_returns_record_with_empty_extraction(self, indexer_no_gemini, tmp_index):
        """Gemini 없어도 레코드 자체는 저장되고 None이 아닌 dict 반환."""
        result = await indexer_no_gemini.index_artifact(
            task_id="T-001",
            org_id="aiorg_engineering_bot",
            artifact_text="설계 완료: YAML frontmatter 기반 메타데이터 저장",
        )
        assert result is not None
        assert result["task_id"] == "T-001"
        assert result["entities"] == []

    @pytest.mark.asyncio
    async def test_empty_text_returns_none(self, indexer_no_gemini):
        """빈 산출물 텍스트는 None 반환 (스킵)."""
        result = await indexer_no_gemini.index_artifact(
            task_id="T-002",
            org_id="org",
            artifact_text="",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_none(self, indexer_no_gemini):
        result = await indexer_no_gemini.index_artifact(
            task_id="T-003",
            org_id="org",
            artifact_text="   \n\t  ",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_gemini_mock_extraction(self, indexer_with_gemini, tmp_index):
        """Gemini mock을 사용해 실제 추출 흐름 검증."""
        mock_response_json = json.dumps({
            "entities": ["reply_to_message", "Gemini Flash", "메타데이터"],
            "decisions": ["blk-1 선택", "write-time indexing 적용"],
            "tags": ["telegram", "metadata", "indexing", "gemini"],
            "summary": "봇 답장 컨텍스트 주입 및 메타데이터 인덱싱 구현",
        })

        # Gemini 클라이언트 mock
        indexer_with_gemini._genai_available = True
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = mock_response_json
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
        indexer_with_gemini._client = mock_client

        result = await indexer_with_gemini.index_artifact(
            task_id="T-mock-001",
            org_id="aiorg_engineering_bot",
            artifact_text="Phase 2 구현 완료: reply_to_message 파싱 및 메타데이터 인덱싱",
        )
        assert result is not None
        assert "reply_to_message" in result["entities"]
        assert "blk-1 선택" in result["decisions"]
        assert "telegram" in result["tags"]
        assert "봇 답장 컨텍스트" in result["summary"]

        # JSONL 저장 확인
        lines = tmp_index.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        saved = json.loads(lines[0])
        assert saved["meta_generated_by"] == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_gemini_api_error_returns_none(self, indexer_with_gemini, tmp_index):
        """Gemini API 실패 시 None 반환 (스킵, JSONL 저장 안 함)."""
        indexer_with_gemini._genai_available = True
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(side_effect=Exception("API Error"))
        indexer_with_gemini._client = mock_client

        result = await indexer_with_gemini.index_artifact(
            task_id="T-fail",
            org_id="org",
            artifact_text="실패 테스트 산출물 텍스트",
        )
        # 실패 시 None 반환
        assert result is None
        # JSONL에 아무것도 저장되지 않아야 함
        assert not tmp_index.exists() or tmp_index.read_text().strip() == ""

    @pytest.mark.asyncio
    async def test_artifact_text_truncated_for_gemini(self, indexer_with_gemini, tmp_index):
        """8000자 초과 산출물은 8000자로 잘려서 Gemini에 전달되어야 함."""
        indexer_with_gemini._genai_available = True
        captured_prompts = []

        async def capture_prompt(model, contents, **kwargs):
            captured_prompts.append(contents)
            resp = MagicMock()
            resp.text = json.dumps({
                "entities": [], "decisions": [], "tags": [], "summary": "ok"
            })
            return resp

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = capture_prompt
        indexer_with_gemini._client = mock_client

        long_artifact = "X" * 20000
        await indexer_with_gemini.index_artifact(
            task_id="T-long",
            org_id="org",
            artifact_text=long_artifact,
        )
        assert len(captured_prompts) == 1
        # 프롬프트 내 8000자 제한 확인
        assert "X" * 8001 not in captured_prompts[0]


# ------------------------------------------------------------------
# 샘플 데이터 품질 검증 (Gemini 없이 파싱 로직만)
# ------------------------------------------------------------------

class TestSampleDataQuality:
    def test_real_world_artifact_parsing(self):
        """실제 봇 산출물과 유사한 텍스트를 파싱해 필드 구조 검증."""
        simulated_gemini_output = json.dumps({
            "entities": [
                "reply_to_message", "ArtifactIndexer", "Gemini Flash",
                "JSONL", "notify_task_done", "telegram_relay.py"
            ],
            "decisions": [
                "write-time indexing 방식 채택",
                "실패 시 스킵 정책 적용",
                "Gemini Flash (gemini-2.5-flash) 사용",
            ],
            "tags": ["telegram", "metadata", "indexing", "python", "async", "gemini"],
            "summary": "봇 산출물 자동 메타데이터 추출 파이프라인 구현 완료",
        })

        result = ArtifactIndexer._parse_gemini_response(simulated_gemini_output)

        assert len(result["entities"]) == 6
        assert len(result["decisions"]) == 3
        assert len(result["tags"]) == 6
        assert len(result["summary"]) > 0
        assert result["summary"].endswith("완료")
