"""건강 리포트 파서 — JSON/dict/텍스트 형식의 리포트를 수신하여
구조화된 ImprovementItem 목록으로 변환한다.

지원 입력 형식:
  1. CodeHealthReport dataclass (core/code_health.py)
  2. dict (JSON-serialized 리포트)
  3. 텍스트 (Telegram 메시지 텍스트 등)

사용법:
    from core.health_report_parser import HealthReportParser
    parser = HealthReportParser()
    items = parser.parse(report)          # CodeHealthReport 또는 dict
    items = parser.parse_text(text)       # 텍스트 형식
    for item in items:
        print(item.file_path, item.severity, item.priority)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

# ------------------------------------------------------------------
# 설정 로드
# ------------------------------------------------------------------

def _load_thresholds() -> dict:
    """improvement_thresholds.yaml 로드. 실패 시 기본값 반환."""
    config_path = Path(__file__).parent.parent / "improvement_thresholds.yaml"
    try:
        import yaml  # type: ignore
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.debug(f"[HealthReportParser] thresholds 로드 실패(기본값 사용): {e}")
        return {}


def _get_threshold(key_path: str, default: Any) -> Any:
    """점(.)으로 구분된 키 경로로 중첩 dict 값 조회."""
    data = _load_thresholds()
    keys = key_path.split(".")
    for k in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(k, default)
    return data


# ------------------------------------------------------------------
# 데이터 스키마
# ------------------------------------------------------------------

@dataclass
class ImprovementItem:
    """파싱 결과 — 개선이 필요한 단일 항목."""

    issue_type: str        # "file_size_critical" | "file_size_warn" | "error_pattern"
    severity: str          # "critical" | "warn" | "info"
    priority: int          # 1(낮음) ~ 10(긴급) — ImprovementBus와 동일 스케일
    suggested_action: str  # 개선 제안 자연어
    file_path: str | None = None     # 대상 파일 경로 (파일 이슈인 경우)
    error_pattern: str | None = None # 반복 에러 패턴 명 (에러 이슈인 경우)
    detail: dict = field(default_factory=dict)  # 추가 근거 데이터
    resolved: bool = False  # 재스캔 후 해소 여부 표시용

    def __repr__(self) -> str:
        target = self.file_path or self.error_pattern or "unknown"
        return f"ImprovementItem({self.severity}/{self.issue_type}, target={target!r}, p={self.priority})"


# ------------------------------------------------------------------
# 메인 파서
# ------------------------------------------------------------------

class HealthReportParser:
    """CodeHealthReport / dict / 텍스트를 ImprovementItem 목록으로 변환."""

    # 기본 임계값 (yaml 로드 실패 시 폴백)
    _DEFAULT_WARN_KB = 80.0
    _DEFAULT_CRITICAL_KB = 150.0
    _DEFAULT_REPEAT_THRESHOLD = 3

    def __init__(self) -> None:
        cfg = _load_thresholds()
        fs = cfg.get("file_size", {})
        ep = cfg.get("error_pattern", {})
        pm = cfg.get("priority_map", {})

        self.warn_kb: float = float(fs.get("warn_kb", self._DEFAULT_WARN_KB))
        self.critical_kb: float = float(fs.get("critical_kb", self._DEFAULT_CRITICAL_KB))
        self.repeat_threshold: int = int(ep.get("repeat_threshold", self._DEFAULT_REPEAT_THRESHOLD))
        self.priority_map: dict = {
            "critical": int(pm.get("critical", 8)),
            "warn": int(pm.get("warn", 4)),
            "info": int(pm.get("info", 1)),
        }

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def parse(self, report: Any) -> list[ImprovementItem]:
        """CodeHealthReport dataclass 또는 dict 형식 파싱."""
        # CodeHealthReport dataclass
        if hasattr(report, "file_entries") and hasattr(report, "top_error_categories"):
            return self._parse_dataclass(report)
        # dict (JSON-deserialized)
        if isinstance(report, dict):
            return self._parse_dict(report)
        # 텍스트 폴백
        if isinstance(report, str):
            return self.parse_text(report)
        logger.warning(f"[HealthReportParser] 알 수 없는 입력 타입: {type(report)}")
        return []

    def parse_text(self, text: str) -> list[ImprovementItem]:
        """Telegram 메시지 텍스트 등 비정형 텍스트 파싱.

        예시 입력:
            🔴 크리티컬 파일:
              • core/telegram_relay.py (205KB) — 분리 권장 (>150KB)
            📋 반복 에러 패턴:
              • approach: 49회
        """
        items: list[ImprovementItem] = []
        items.extend(self._parse_text_file_entries(text))
        items.extend(self._parse_text_error_patterns(text))
        logger.info(f"[HealthReportParser] 텍스트 파싱 완료 — {len(items)}개 항목")
        return items

    # ------------------------------------------------------------------
    # 내부 파싱 로직
    # ------------------------------------------------------------------

    def _parse_dataclass(self, report: Any) -> list[ImprovementItem]:
        """CodeHealthReport dataclass → ImprovementItem 목록."""
        items: list[ImprovementItem] = []

        for entry in getattr(report, "file_entries", []):
            status = getattr(entry, "status", "ok")
            if status == "ok":
                continue
            severity = "critical" if status == "critical" else "warn"
            size_kb = getattr(entry, "size_kb", 0.0)
            file_path = getattr(entry, "path", "unknown")
            items.append(self._make_file_item(file_path, size_kb, severity))

        for cat, count in getattr(report, "top_error_categories", []):
            if count >= self.repeat_threshold:
                items.append(self._make_error_item(cat, count))

        items.sort(key=lambda x: x.priority, reverse=True)
        logger.info(f"[HealthReportParser] dataclass 파싱 완료 — {len(items)}개 항목")
        return items

    def _parse_dict(self, data: dict) -> list[ImprovementItem]:
        """dict (JSON-deserialized CodeHealthReport) → ImprovementItem 목록."""
        items: list[ImprovementItem] = []

        for entry in data.get("file_entries", []):
            status = entry.get("status", "ok")
            if status == "ok":
                continue
            severity = "critical" if status == "critical" else "warn"
            size_kb = float(entry.get("size_kb", 0.0))
            file_path = entry.get("path", "unknown")
            items.append(self._make_file_item(file_path, size_kb, severity))

        for item in data.get("top_error_categories", []):
            # list of [category, count] or {"category": ..., "count": ...}
            if isinstance(item, (list, tuple)) and len(item) == 2:
                cat, count = item[0], int(item[1])
            elif isinstance(item, dict):
                cat, count = item.get("category", "?"), int(item.get("count", 0))
            else:
                continue
            if count >= self.repeat_threshold:
                items.append(self._make_error_item(cat, count))

        items.sort(key=lambda x: x.priority, reverse=True)
        logger.info(f"[HealthReportParser] dict 파싱 완료 — {len(items)}개 항목")
        return items

    def _parse_text_file_entries(self, text: str) -> list[ImprovementItem]:
        """텍스트에서 파일 크기 항목 추출.
        패턴: • some/file.py (NNNkb) — ...
        """
        items: list[ImprovementItem] = []
        # 크리티컬 블록 여부 판단
        is_critical_block = False
        for line in text.splitlines():
            line = line.strip()
            if "크리티컬" in line or "critical" in line.lower():
                is_critical_block = True
            elif "warn" in line.lower() or "경고" in line:
                is_critical_block = False

            # • path (NNNkb) 패턴
            m = re.search(
                r"[•*-]\s*([\w./\-_]+\.py)\s*\((\d+(?:\.\d+)?)\s*[Kk][Bb]\)",
                line,
            )
            if m:
                file_path = m.group(1)
                size_kb = float(m.group(2))
                if size_kb >= self.critical_kb or is_critical_block:
                    severity = "critical"
                elif size_kb >= self.warn_kb:
                    severity = "warn"
                else:
                    severity = "info"
                items.append(self._make_file_item(file_path, size_kb, severity))
        return items

    def _parse_text_error_patterns(self, text: str) -> list[ImprovementItem]:
        """텍스트에서 반복 에러 패턴 추출.
        패턴: • pattern_name: N회
        """
        items: list[ImprovementItem] = []
        in_error_section = False
        for line in text.splitlines():
            line = line.strip()
            if "에러 패턴" in line or "error pattern" in line.lower():
                in_error_section = True
                continue
            if in_error_section and (line.startswith("##") or line.startswith("🔴") or line.startswith("⚠️")):
                in_error_section = False
            if in_error_section:
                # • pattern_name: N회
                m = re.search(r"[•*-]\s*([^:]+):\s*(\d+)\s*회", line)
                if m:
                    pattern = m.group(1).strip()
                    count = int(m.group(2))
                    if count >= self.repeat_threshold:
                        items.append(self._make_error_item(pattern, count))
        return items

    # ------------------------------------------------------------------
    # 팩토리 메서드
    # ------------------------------------------------------------------

    def _make_file_item(self, file_path: str, size_kb: float, severity: str) -> ImprovementItem:
        priority = self.priority_map.get(severity, 4)
        if severity == "critical":
            issue_type = "file_size_critical"
            action = f"{file_path} ({size_kb:.0f}KB) — 모듈 분리 권장 (>{self.critical_kb:.0f}KB)"
        else:
            issue_type = "file_size_warn"
            action = f"{file_path} ({size_kb:.0f}KB) — 성장 추세 모니터링"
        return ImprovementItem(
            issue_type=issue_type,
            severity=severity,
            priority=priority,
            file_path=file_path,
            suggested_action=action,
            detail={"size_kb": size_kb},
        )

    def _make_error_item(self, pattern: str, count: int) -> ImprovementItem:
        priority = min(10, self.priority_map.get("warn", 4) + count)
        return ImprovementItem(
            issue_type="error_pattern",
            severity="warn",
            priority=priority,
            error_pattern=pattern,
            suggested_action=(
                f"'{pattern}' 패턴 {count}회 반복 — 근본 원인 분석 및 자동 수정 시도"
            ),
            detail={"pattern": pattern, "count": count},
        )
