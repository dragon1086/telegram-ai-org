"""tools/criteria_loader.py — criteria_tracking.yaml 로드 및 버전 검증 유틸.

PRD 참조: docs/RETRO-33-criteria-tracking-pipeline-prd.md §5.2
관련 태스크: RETRO-27

사용 예::

    from tools.criteria_loader import CriteriaLoader

    loader = CriteriaLoader()
    threshold = loader.get_threshold("exit_code_143")
    # {"block_threshold": 3, "warn_threshold": 1, "criteria_version": "1.0.0"}

    loader.validate_version("1.0.0")  # OK
    loader.validate_version("2.0.0")  # → ValidationError
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# 예외 클래스
# ---------------------------------------------------------------------------

class CriteriaFileNotFoundError(FileNotFoundError):
    """criteria_tracking.yaml 파일이 존재하지 않을 때 (V-01).

    pre-flight 체크에서 SystemExit로 전환해야 하면 caller에서 처리한다.
    """


class ValidationError(ValueError):
    """기준 버전 불일치 또는 스키마 검증 실패 시 발생."""


# ---------------------------------------------------------------------------
# CriteriaLoader
# ---------------------------------------------------------------------------

class CriteriaLoader:
    """criteria_tracking.yaml 로드 및 검증 유틸리티.

    Parameters
    ----------
    base_dir:
        YAML 파일을 탐색할 기준 디렉토리.
        기본값은 이 파일의 부모 디렉토리(프로젝트 루트).
    """

    _DEFAULT_FILENAME = "criteria_tracking.yaml"

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is None:
            # tools/ 디렉토리의 부모 = 프로젝트 루트
            base_dir = Path(__file__).resolve().parent.parent
        self._base_dir = Path(base_dir)
        self._data: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, path: str | Path | None = None) -> dict[str, Any]:
        """YAML 파일을 로드하고 파싱된 dict를 반환한다.

        Parameters
        ----------
        path:
            절대/상대 경로. 생략 시 ``base_dir/criteria_tracking.yaml`` 사용.

        Returns
        -------
        dict
            전체 YAML 내용.

        Raises
        ------
        CriteriaFileNotFoundError
            파일이 존재하지 않을 때 (V-01).
        """
        resolved = self._resolve_path(path)
        if not resolved.exists():
            raise CriteriaFileNotFoundError(
                f"[V-01] criteria_tracking.yaml not found: {resolved}\n"
                "pre-flight 실패 — 파일을 생성하거나 경로를 확인하세요."
            )
        with resolved.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        self._data = data
        return data

    def get_threshold(self, key: str) -> dict[str, Any]:
        """지정한 threshold 항목에서 핵심 필드를 반환한다.

        Parameters
        ----------
        key:
            thresholds 섹션의 키 (예: ``"exit_code_143"``).

        Returns
        -------
        dict
            ``{"block_threshold": N, "warn_threshold": N, "criteria_version": "x.y.z",
               "description": "...", "unit": "...", "prd_policy_ref": "..."}``

        Raises
        ------
        KeyError
            해당 key가 thresholds 섹션에 없을 때.
        CriteriaFileNotFoundError
            load() 를 호출하기 전에 get_threshold()를 호출했을 때.
        """
        data = self._ensure_loaded()
        thresholds = data.get("thresholds", {})
        if key not in thresholds:
            available = list(thresholds.keys())
            raise KeyError(
                f"threshold key '{key}' not found. "
                f"Available keys: {available}"
            )
        entry = thresholds[key]
        return {
            "block_threshold": entry["block_threshold"],
            "warn_threshold": entry.get("warn_threshold"),
            "criteria_version": entry.get("criteria_version"),
            "description": entry.get("description", ""),
            "unit": entry.get("unit", ""),
            "prd_policy_ref": entry.get("prd_policy_ref", ""),
        }

    def validate_version(self, expected_version: str) -> bool:
        """metadata.criteria_version과 expected_version의 일치 여부를 검증한다.

        Parameters
        ----------
        expected_version:
            검증할 기준 버전 문자열 (예: ``"1.0.0"``).

        Returns
        -------
        bool
            일치하면 ``True``.

        Raises
        ------
        ValidationError
            버전이 일치하지 않을 때.
        CriteriaFileNotFoundError
            load() 전에 호출됐을 때.
        """
        data = self._ensure_loaded()
        actual = data.get("metadata", {}).get("criteria_version", "")
        if actual != expected_version:
            raise ValidationError(
                f"[V-02] criteria_version mismatch: "
                f"expected='{expected_version}', actual='{actual}'\n"
                f"YAML을 업데이트하거나 expected_version을 수정하세요."
            )
        return True

    def get_research_basis(self, key: str) -> list[dict[str, Any]]:
        """지정한 threshold의 근거 레퍼런스 목록을 반환한다.

        Parameters
        ----------
        key:
            thresholds 섹션의 키 (예: ``"exit_code_143"``).

        Returns
        -------
        list[dict]
            ``[{"id": "...", "title": "...", "weight": "..."}, ...]``
            research_basis 섹션이 없으면 빈 리스트 반환.
        """
        data = self._ensure_loaded()
        thresholds = data.get("thresholds", {})
        if key not in thresholds:
            raise KeyError(f"threshold key '{key}' not found.")
        basis = thresholds[key].get("research_basis", {})
        return list(basis.get("refs", []))

    def get_metadata(self) -> dict[str, Any]:
        """metadata 섹션 전체를 반환한다."""
        data = self._ensure_loaded()
        return dict(data.get("metadata", {}))

    def get_integration(self, dept: str) -> dict[str, Any]:
        """integrations 섹션에서 특정 부서 설정을 반환한다.

        Parameters
        ----------
        dept:
            부서 키 (``"development"``, ``"operations"``, ``"growth"``,
            ``"design"``, ``"research"``).
        """
        data = self._ensure_loaded()
        integrations = data.get("integrations", {})
        if dept not in integrations:
            raise KeyError(f"integration dept '{dept}' not found.")
        return dict(integrations[dept])

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_path(self, path: str | Path | None) -> Path:
        if path is None:
            return self._base_dir / self._DEFAULT_FILENAME
        p = Path(path)
        if p.is_absolute():
            return p
        return self._base_dir / p

    def _ensure_loaded(self) -> dict[str, Any]:
        """_data가 없으면 기본 경로로 load() 자동 호출."""
        if self._data is None:
            self.load()
        return self._data  # type: ignore[return-value]
