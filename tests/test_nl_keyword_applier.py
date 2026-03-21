"""NLKeywordApplier 테스트."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_apply_new_keyword(tmp_path):
    from core.nl_keyword_applier import NLKeywordApplier
    nl_file = tmp_path / "nl_classifier.py"
    nl_file.write_text('"engineering": ["버그 수정", "코드"]')
    applier = NLKeywordApplier()
    applier._path = nl_file
    result = applier.apply({"engineering": ["타임아웃"]})
    assert "타임아웃" in nl_file.read_text()
    assert "engineering" in result


def test_skip_existing_keyword(tmp_path):
    from core.nl_keyword_applier import NLKeywordApplier
    nl_file = tmp_path / "nl_classifier.py"
    nl_file.write_text('"engineering": ["버그 수정", "타임아웃"]')
    applier = NLKeywordApplier()
    applier._path = nl_file
    result = applier.apply({"engineering": ["타임아웃"]})
    assert result == "추가할 신규 키워드 없음"


def test_apply_returns_str_on_missing_file(tmp_path):
    from core.nl_keyword_applier import NLKeywordApplier
    applier = NLKeywordApplier()
    applier._path = tmp_path / "nonexistent.py"
    result = applier.apply({"engineering": ["키워드"]})
    assert isinstance(result, str)
