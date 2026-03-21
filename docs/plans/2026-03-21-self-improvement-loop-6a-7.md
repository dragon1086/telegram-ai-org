# Self-Improvement Loop Phase 6A-7 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the self-improvement loop: signal collection → Telegram reporting → Rocky approval → automated skill/routing/code improvement → commit/push/restart.

**Architecture:**
- Phase 6A: RoutingOptimizer 결과를 일일 cron에 연결 + `/improve-status` 수동 조회 명령
- Phase 6B: RoutingProposal → Telegram 보고 → Rocky 텍스트 승인 → nl_classifier 자동 업데이트
- Phase 6C: SkillAutoImprover — autoresearch (N variants → EvalRunner → keep best)
- Phase 7: SelfCodeImprover — subprocess claude Code → TDD loop → git commit/push/restart

**Tech Stack:** Python 3.12, APScheduler, python-telegram-bot, subprocess (claude CLI), asyncio, pathlib, pytest

**Safety invariants (모든 단계 공통):**
- 같은 파일 자동 수정 24h 내 최대 3회
- 테스트 통과 확인 전 커밋 금지
- Phase 7은 항상 `fix/auto-YYYY-MM-DD-{target}` 브랜치 사용
- priority < 7 신호는 Telegram 제안만, 자동 실행 금지

---

## Phase 6A: Telegram 보고 완성

> 현재 상태: improvement_bus, code_health, skill eval은 `_safe_send` 연결 완료.
> 누락: RoutingOptimizer 일일 실행 + `/improve-status` 수동 조회.

---

### Task 1: RoutingOptimizer를 일일 cron에 추가

**Files:**
- Modify: `core/scheduler.py` (기존 `_improvement_bus_daily` 메서드 근처)

**Step 1: 실패 테스트 작성**

```python
# tests/test_scheduler.py 에 추가 (sys.path.insert 먼저 확인)
def test_routing_optimizer_job_registered():
    """routing_optimizer_daily 잡이 스케줄러에 등록되어 있어야 한다."""
    from core.scheduler import OrgScheduler
    sched = OrgScheduler(send_text=lambda t: None)
    job_ids = sched.get_job_ids()
    assert "routing_optimizer_daily" in job_ids
```

Run: `.venv/bin/pytest tests/test_scheduler.py::test_routing_optimizer_job_registered -v`
Expected: FAIL (job not registered yet)

**Step 2: scheduler.py에 잡 등록 + 메서드 추가**

`_register_jobs()` 내에 추가:
```python
self.scheduler.add_job(
    self._routing_optimizer_daily,
    CronTrigger(hour=3, minute=0, timezone="Asia/Seoul"),
    id="routing_optimizer_daily",
    replace_existing=True,
)
```

새 메서드:
```python
async def _routing_optimizer_daily(self) -> None:
    """매일 03:00 KST — RoutingOptimizer 제안 생성 및 Telegram 보고."""
    logger.info("[OrgScheduler] routing_optimizer_daily 시작")
    try:
        from core.routing_optimizer import RoutingOptimizer
        opt = RoutingOptimizer()
        proposal = opt.generate_proposal()
        if proposal:
            await self._safe_send(opt.format_for_telegram(proposal))
    except Exception as e:
        logger.error(f"[OrgScheduler] routing_optimizer_daily 실패: {e}")
```

**Step 3: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_scheduler.py::test_routing_optimizer_job_registered -v`
Expected: PASS

**Step 4: Commit**

```bash
git add core/scheduler.py tests/test_scheduler.py
git commit -m "feat: routing_optimizer_daily cron 추가 (03:00 KST)"
```

---

### Task 2: `/improve-status` 수동 조회 명령 추가

**Files:**
- Modify: `core/pm_orchestrator.py` (명령 핸들러 등록 부분)
- 또는 `core/bot_commands.py` (기존 명령 패턴 확인 후 결정)

**Step 1: 기존 명령 패턴 파악**

```bash
grep -n "def.*command\|CommandHandler\|/status\|/retro" core/pm_orchestrator.py | head -20
```

**Step 2: 핸들러 추가**

```python
async def _handle_improve_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """현재 자가개선 시스템 상태 요약 반환."""
    from core.improvement_bus import ImprovementBus
    from core.eval_runner import EvalRunner
    bus = ImprovementBus()
    signals = bus.collect_signals()
    runner = EvalRunner()
    results = runner.score_all_skills()
    lines = [
        "📊 *자가개선 상태*",
        f"수집 신호: {len(signals)}개",
        f"고우선순위(≥7): {sum(1 for s in signals if s.priority >= 7)}개",
        "",
        runner.format_results(results) if results else "스킬 eval 데이터 없음",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
```

CommandHandler 등록:
```python
app.add_handler(CommandHandler("improve_status", self._handle_improve_status))
```

**Step 3: 기능 검증**

```python
# tests/test_improve_status.py
def test_improve_status_handler_exists():
    """_handle_improve_status 메서드가 pm_orchestrator에 있어야 한다."""
    from core.pm_orchestrator import PMOrchestrator
    assert hasattr(PMOrchestrator, "_handle_improve_status")
```

**Step 4: Commit**

```bash
git add core/pm_orchestrator.py tests/test_improve_status.py
git commit -m "feat: /improve_status 수동 조회 명령 추가"
```

---

## Phase 6B: RoutingOptimizer → Rocky 승인 게이트

> RoutingProposal이 생성되면 Telegram으로 보내고, Rocky가 "승인"/"거절"로 응답하면 nl_classifier 자동 업데이트.

---

### Task 3: RoutingApprovalStore — 대기 중인 제안 저장

**Files:**
- Create: `core/routing_approval_store.py`

**Step 1: 실패 테스트 작성**

```python
# tests/test_routing_approval_store.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.routing_approval_store import RoutingApprovalStore

def test_save_and_load(tmp_path):
    store = RoutingApprovalStore(tmp_path / "approvals.json")
    store.save({"dept": "engineering", "keywords": ["버그"]})
    pending = store.load_pending()
    assert pending is not None
    assert pending["dept"] == "engineering"

def test_clear_after_decision(tmp_path):
    store = RoutingApprovalStore(tmp_path / "approvals.json")
    store.save({"keywords": ["test"]})
    store.clear()
    assert store.load_pending() is None
```

**Step 2: 구현**

```python
# core/routing_approval_store.py
"""대기 중인 RoutingProposal 저장소."""
from __future__ import annotations
import json
from pathlib import Path

_DEFAULT_PATH = Path(__file__).parent.parent / "data" / "routing_approval.json"

class RoutingApprovalStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, proposal_dict: dict) -> None:
        self._path.write_text(json.dumps(proposal_dict, ensure_ascii=False, indent=2))

    def load_pending(self) -> dict | None:
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text())
        except Exception:
            return None

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()
```

**Step 3: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_routing_approval_store.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add core/routing_approval_store.py tests/test_routing_approval_store.py
git commit -m "feat: RoutingApprovalStore — 라우팅 제안 대기 상태 저장"
```

---

### Task 4: RoutingOptimizer → proposal 저장 + Telegram 보고

**Files:**
- Modify: `core/scheduler.py` (`_routing_optimizer_daily`)

**Step 1: 제안 저장 로직 추가**

```python
async def _routing_optimizer_daily(self) -> None:
    logger.info("[OrgScheduler] routing_optimizer_daily 시작")
    try:
        from core.routing_optimizer import RoutingOptimizer
        from core.routing_approval_store import RoutingApprovalStore
        opt = RoutingOptimizer()
        proposal = opt.generate_proposal()
        if proposal:
            store = RoutingApprovalStore()
            store.save({
                "keyword_additions": proposal.keyword_additions,
                "rationale": proposal.rationale,
                "current_accuracy": proposal.current_accuracy,
                "estimated_gain": proposal.estimated_gain,
            })
            msg = opt.format_for_telegram(proposal)
            msg += "\n\n*승인하려면:* `/routing_approve`\n*거절하려면:* `/routing_reject`"
            await self._safe_send(msg)
    except Exception as e:
        logger.error(f"[OrgScheduler] routing_optimizer_daily 실패: {e}")
```

**Step 2: Commit**

```bash
git add core/scheduler.py
git commit -m "feat: routing proposal → RoutingApprovalStore 저장 + 승인 안내"
```

---

### Task 5: `/routing_approve` 및 `/routing_reject` 명령 구현

**Files:**
- Modify: `core/pm_orchestrator.py`

**Step 1: nl_classifier 키워드 추가 유틸 구현**

```python
# core/pm_orchestrator.py 내 메서드
async def _handle_routing_approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """대기 중인 라우팅 제안을 nl_classifier에 적용."""
    from core.routing_approval_store import RoutingApprovalStore
    from core.nl_keyword_applier import NLKeywordApplier
    store = RoutingApprovalStore()
    proposal = store.load_pending()
    if not proposal:
        await update.message.reply_text("대기 중인 라우팅 제안 없음.")
        return
    applier = NLKeywordApplier()
    result = applier.apply(proposal["keyword_additions"])
    store.clear()
    await update.message.reply_text(f"✅ 적용 완료:\n{result}")

async def _handle_routing_reject(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from core.routing_approval_store import RoutingApprovalStore
    store = RoutingApprovalStore()
    store.clear()
    await update.message.reply_text("❌ 라우팅 제안 거절됨. 다음 분석 시까지 대기.")
```

**Step 2: NLKeywordApplier 구현**

```python
# core/nl_keyword_applier.py
"""nl_classifier.py에 키워드를 안전하게 추가."""
from __future__ import annotations
import re
from pathlib import Path
from loguru import logger

class NLKeywordApplier:
    def __init__(self) -> None:
        self._path = Path(__file__).parent / "nl_classifier.py"

    def apply(self, keyword_additions: dict[str, list[str]]) -> str:
        """dept → keywords 맵을 nl_classifier.py에 추가."""
        if not self._path.exists():
            return "nl_classifier.py 없음"
        text = self._path.read_text(encoding="utf-8")
        applied = []
        for dept, keywords in keyword_additions.items():
            for kw in keywords:
                # 이미 존재하면 스킵
                if kw in text:
                    continue
                # dept 블록을 찾아 키워드 삽입 (간단 패턴)
                pattern = rf'("{dept}"[^[]*\[)'
                match = re.search(pattern, text)
                if match:
                    insert_pos = match.end()
                    text = text[:insert_pos] + f'"{kw}", ' + text[insert_pos:]
                    applied.append(f"{dept}: +{kw}")
        if applied:
            self._path.write_text(text, encoding="utf-8")
            logger.info(f"[NLKeywordApplier] 적용: {applied}")
        return "\n".join(applied) if applied else "추가할 신규 키워드 없음"
```

**Step 3: 테스트 작성**

```python
# tests/test_nl_keyword_applier.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_apply_new_keyword(tmp_path):
    from core.nl_keyword_applier import NLKeywordApplier
    nl_file = tmp_path / "nl_classifier.py"
    nl_file.write_text('"engineering" ["버그 수정", "코드"]')
    applier = NLKeywordApplier()
    applier._path = nl_file
    result = applier.apply({"engineering": ["타임아웃"]})
    assert "타임아웃" in nl_file.read_text()
    assert "engineering" in result

def test_skip_existing_keyword(tmp_path):
    from core.nl_keyword_applier import NLKeywordApplier
    nl_file = tmp_path / "nl_classifier.py"
    nl_file.write_text('"engineering" ["버그 수정", "타임아웃"]')
    applier = NLKeywordApplier()
    applier._path = nl_file
    result = applier.apply({"engineering": ["타임아웃"]})
    assert result == "추가할 신규 키워드 없음"
```

Run: `.venv/bin/pytest tests/test_nl_keyword_applier.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add core/nl_keyword_applier.py core/pm_orchestrator.py tests/test_nl_keyword_applier.py
git commit -m "feat: 라우팅 승인 게이트 — /routing_approve/reject + NLKeywordApplier"
```

---

## Phase 6C: SkillAutoImprover (autoresearch 루프)

> EvalRunner 점수 < baseline → N개 변형 생성 → 병렬 eval → 최고 점수 keep/revert

---

### Task 6: SkillVariantGenerator — N개 스킬 변형 생성

**Files:**
- Create: `core/skill_auto_improver.py`

**Step 1: 실패 테스트**

```python
# tests/test_skill_auto_improver.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from unittest.mock import patch, MagicMock
from core.skill_auto_improver import SkillAutoImprover

def test_generate_variants_returns_list():
    imp = SkillAutoImprover()
    variants = imp._generate_variants("test content", "low score on edge cases")
    assert isinstance(variants, list)
    assert len(variants) >= 2

def test_no_improvement_returns_none(tmp_path):
    """baseline보다 낮으면 None 반환."""
    imp = SkillAutoImprover()
    with patch.object(imp, "_score_variant", return_value=5.0):
        result = imp.improve("nonexistent-skill-xyz")
    assert result is None
```

**Step 2: 구현 (claude CLI subprocess 기반)**

```python
# core/skill_auto_improver.py
"""스킬 자동 개선 — autoresearch 루프 (N variants → EvalRunner → keep best)."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass
from loguru import logger

SKILLS_DIR = Path(__file__).parent.parent / "skills"
EVALS_DIR = Path(__file__).parent.parent / "evals" / "skills"
MAX_VARIANTS = 3
MIN_IMPROVEMENT = 0.5  # baseline 대비 최소 개선폭


@dataclass
class ImprovementResult:
    skill_name: str
    original_score: float
    best_score: float
    variant_applied: str
    improved: bool


class SkillAutoImprover:
    """스킬 SKILL.md를 N개 변형 → eval → 최고 점수 keep/revert."""

    def improve(self, skill_name: str) -> ImprovementResult | None:
        from core.eval_runner import EvalRunner
        runner = EvalRunner()
        baseline_result = runner.score_skill(skill_name)
        if baseline_result is None:
            logger.info(f"[SkillAutoImprover] {skill_name}: eval.json 없음, 스킵")
            return None

        skill_path = SKILLS_DIR / skill_name / "SKILL.md"
        if not skill_path.exists():
            logger.warning(f"[SkillAutoImprover] {skill_name}: SKILL.md 없음")
            return None

        original_content = skill_path.read_text(encoding="utf-8")
        original_score = baseline_result.score

        failure_summary = self._get_failure_summary(skill_name)
        variants = self._generate_variants(original_content, failure_summary)

        best_score = original_score
        best_variant = original_content

        for i, variant in enumerate(variants):
            skill_path.write_text(variant, encoding="utf-8")
            score = self._score_variant(skill_name)
            logger.info(f"[SkillAutoImprover] {skill_name} variant {i+1}: {score:.1f}")
            if score > best_score:
                best_score = score
                best_variant = variant

        if best_score >= original_score + MIN_IMPROVEMENT:
            skill_path.write_text(best_variant, encoding="utf-8")
            logger.info(f"[SkillAutoImprover] {skill_name} 개선 적용: {original_score:.1f} → {best_score:.1f}")
            return ImprovementResult(
                skill_name=skill_name,
                original_score=original_score,
                best_score=best_score,
                variant_applied=best_variant[:200],
                improved=True,
            )
        else:
            skill_path.write_text(original_content, encoding="utf-8")
            logger.info(f"[SkillAutoImprover] {skill_name} 개선 없음, 원본 복원")
            return ImprovementResult(
                skill_name=skill_name,
                original_score=original_score,
                best_score=best_score,
                variant_applied="",
                improved=False,
            )

    def _score_variant(self, skill_name: str) -> float:
        from core.eval_runner import EvalRunner
        result = EvalRunner().score_skill(skill_name)
        return result.score if result else 0.0

    def _get_failure_summary(self, skill_name: str) -> str:
        try:
            from core.lesson_memory import LessonMemory
            failures = LessonMemory().get_recent_failures(days=14)
            return f"최근 {len(failures)}개 실패 케이스"
        except Exception:
            return "실패 데이터 없음"

    def _generate_variants(self, content: str, failure_summary: str) -> list[str]:
        """Claude CLI로 N개 변형 생성. CLI 없으면 규칙 기반 fallback."""
        variants = []
        # Variant A: 실패 시나리오 명시 추가
        variants.append(content + f"\n\n## 주의 사항\n{failure_summary}에서 도출된 엣지 케이스를 반드시 처리할 것.")
        # Variant B: 판단 기준 수치화
        variants.append(content.replace("판단", "수치 기반 판단 (점수 7.0 이상 기준)"))
        # Variant C: Claude CLI 기반 (가능 시)
        claude_variant = self._generate_via_claude(content, failure_summary)
        if claude_variant:
            variants.append(claude_variant)
        return variants[:MAX_VARIANTS]

    def _generate_via_claude(self, content: str, failure_summary: str) -> str | None:
        """claude --print으로 변형 생성."""
        prompt = (
            f"다음 스킬 문서를 개선하라. {failure_summary}를 고려하여 "
            f"구체성과 명확성을 높여라. 원본 구조는 유지.\n\n---\n{content[:2000]}"
        )
        try:
            result = subprocess.run(
                ["claude", "--print", "-p", prompt],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None
```

**Step 3: 테스트 통과**

Run: `.venv/bin/pytest tests/test_skill_auto_improver.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add core/skill_auto_improver.py tests/test_skill_auto_improver.py
git commit -m "feat: SkillAutoImprover — autoresearch 루프 (N variants → eval → keep best)"
```

---

### Task 7: 스케줄러에 SkillAutoImprover 연결

**Files:**
- Modify: `core/scheduler.py` (`_skill_improve_weekly`)

**Step 1: 기존 메서드 업그레이드**

```python
async def _skill_improve_weekly(self) -> None:
    """매주 일요일 22:00 KST — 스킬 eval + 자동 개선 루프."""
    logger.info("[OrgScheduler] skill_improve_weekly 시작")
    try:
        from core.eval_runner import EvalRunner
        from core.skill_auto_improver import SkillAutoImprover
        runner = EvalRunner()
        results = runner.score_all_skills()
        improver = SkillAutoImprover()
        improvement_lines = []
        for r in results:
            if not r.passed:
                imp_result = improver.improve(r.skill_name)
                if imp_result and imp_result.improved:
                    improvement_lines.append(
                        f"  ✨ {r.skill_name}: {imp_result.original_score:.1f} → {imp_result.best_score:.1f}"
                    )
        msg_parts = [runner.format_results(results)]
        if improvement_lines:
            msg_parts.append("\n🔧 *자동 개선 적용:*\n" + "\n".join(improvement_lines))
        if msg_parts[0] or improvement_lines:
            await self._safe_send("\n".join(msg_parts))
    except Exception as e:
        logger.error(f"[OrgScheduler] skill_improve_weekly 실패: {e}")
```

**Step 2: Commit**

```bash
git add core/scheduler.py
git commit -m "feat: skill_improve_weekly에 SkillAutoImprover 루프 연결"
```

---

## Phase 7: SelfCodeImprover (코드 자가 수정)

> 반복 에러 감지 → 프롬프트 자동 생성 → claude subprocess → TDD → git commit/push/restart

---

### Task 8: SelfCodeImprover 코어 구현

**Files:**
- Create: `core/self_code_improver.py`

**Step 1: 실패 테스트**

```python
# tests/test_self_code_improver.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from unittest.mock import patch
from core.self_code_improver import SelfCodeImprover, FixResult

def test_fix_result_dataclass():
    r = FixResult(
        target="core/foo.py", success=True,
        branch="fix/auto-2026-03-21-foo",
        commit_hash="abc1234", attempts=1,
    )
    assert r.success is True

def test_build_prompt_contains_target():
    imp = SelfCodeImprover(dry_run=True)
    prompt = imp._build_prompt(
        target="core/pm_orchestrator.py",
        error_summary="context_loss 7회 반복",
        related_files=["core/pm_orchestrator.py"],
    )
    assert "core/pm_orchestrator.py" in prompt
    assert "context_loss" in prompt

def test_dry_run_does_not_run_subprocess():
    imp = SelfCodeImprover(dry_run=True)
    with patch("subprocess.run") as mock_run:
        result = imp.fix(
            target="core/foo.py",
            error_summary="test error",
            related_files=["core/foo.py"],
        )
    mock_run.assert_not_called()
    assert result is None  # dry_run은 None 반환
```

**Step 2: 구현**

```python
# core/self_code_improver.py
"""코드 자가 수정 — subprocess claude → TDD → git commit/push/restart."""
from __future__ import annotations
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger

REPO_ROOT = Path(__file__).parent.parent
MAX_ATTEMPTS = 3
RATE_LIMIT_FILE = REPO_ROOT / "data" / "self_fix_rate.json"


@dataclass
class FixResult:
    target: str
    success: bool
    branch: str
    commit_hash: str
    attempts: int
    error_message: str = ""


class SelfCodeImprover:
    """반복 에러 신호 → claude subprocess → TDD 루프 → git commit/push/restart."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    def fix(self, target: str, error_summary: str, related_files: list[str]) -> FixResult | None:
        if self.dry_run:
            logger.info(f"[SelfCodeImprover] dry_run: {target}")
            return None

        if not self._check_rate_limit(target):
            logger.warning(f"[SelfCodeImprover] rate limit: {target} 24h 내 3회 초과")
            return None

        branch = f"fix/auto-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{Path(target).stem}"
        self._run_git(["checkout", "-b", branch])

        prompt = self._build_prompt(target, error_summary, related_files)

        for attempt in range(1, MAX_ATTEMPTS + 1):
            logger.info(f"[SelfCodeImprover] {target} 시도 {attempt}/{MAX_ATTEMPTS}")
            claude_ok = self._run_claude(prompt)
            if not claude_ok:
                continue
            test_passed, test_output = self._run_tests()
            if test_passed:
                commit_hash = self._commit_and_push(branch, target, attempt)
                self._record_rate_limit(target)
                self._restart_if_needed(target)
                return FixResult(
                    target=target, success=True,
                    branch=branch, commit_hash=commit_hash, attempts=attempt,
                )
            # 실패 시 에러 피드백 포함하여 프롬프트 보강
            prompt = self._build_prompt(target, error_summary, related_files, test_output)

        # 모두 실패 → 원복
        self._run_git(["checkout", "main"])
        self._run_git(["branch", "-D", branch])
        logger.error(f"[SelfCodeImprover] {target} 자동 수정 실패 — 원복 완료")
        return FixResult(
            target=target, success=False,
            branch=branch, commit_hash="", attempts=MAX_ATTEMPTS,
            error_message="max attempts reached",
        )

    def _build_prompt(
        self,
        target: str,
        error_summary: str,
        related_files: list[str],
        test_output: str = "",
    ) -> str:
        file_list = "\n".join(f"  - {f}" for f in related_files)
        feedback = f"\n\n이전 시도 실패 출력:\n{test_output[:1000]}" if test_output else ""
        return (
            f"[자가수정 태스크]\n"
            f"에러 패턴: {error_summary}\n\n"
            f"수정 지침:\n"
            f"1. 근본 원인 가설 명시\n"
            f"2. 최소 변경 원칙 (public API 유지)\n"
            f"3. 실패 재현 테스트 먼저 작성 (TDD)\n"
            f"4. pytest 전체 통과 확인\n"
            f"5. ruff check 통과\n\n"
            f"관련 파일:\n{file_list}"
            f"{feedback}"
        )

    def _run_claude(self, prompt: str) -> bool:
        try:
            result = subprocess.run(
                ["claude", "--print", "--dangerously-skip-permissions", "-p", prompt],
                cwd=str(REPO_ROOT),
                capture_output=True, text=True, timeout=300,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"[SelfCodeImprover] claude 실행 실패: {e}")
            return False

    def _run_tests(self) -> tuple[bool, str]:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=short"],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=120,
        )
        passed = result.returncode == 0
        return passed, result.stdout + result.stderr

    def _commit_and_push(self, branch: str, target: str, attempt: int) -> str:
        self._run_git(["add", "-A"])
        msg = f"fix: 자동 수정 — {target} (시도 {attempt}회)\n\nCo-Authored-By: SelfCodeImprover <bot@internal>"
        self._run_git(["commit", "-m", msg])
        self._run_git(["push", "origin", branch])
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        return result.stdout.strip()

    def _restart_if_needed(self, target: str) -> None:
        """core/ 파일 수정 시 봇 재기동."""
        if target.startswith("core/"):
            logger.info("[SelfCodeImprover] core 변경 감지 → 재기동 신호 발송")
            restart_flag = REPO_ROOT / "data" / ".restart_requested"
            restart_flag.parent.mkdir(parents=True, exist_ok=True)
            restart_flag.touch()

    def _check_rate_limit(self, target: str) -> bool:
        import json
        from datetime import timedelta
        RATE_LIMIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if RATE_LIMIT_FILE.exists():
            try:
                data = json.loads(RATE_LIMIT_FILE.read_text())
            except Exception:
                pass
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=24)).isoformat()
        recent = [t for t in data.get(target, []) if t > cutoff]
        return len(recent) < 3

    def _record_rate_limit(self, target: str) -> None:
        import json
        RATE_LIMIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if RATE_LIMIT_FILE.exists():
            try:
                data = json.loads(RATE_LIMIT_FILE.read_text())
            except Exception:
                pass
        data.setdefault(target, []).append(datetime.now(timezone.utc).isoformat())
        RATE_LIMIT_FILE.write_text(json.dumps(data, indent=2))

    def _run_git(self, args: list[str]) -> None:
        subprocess.run(["git"] + args, cwd=str(REPO_ROOT), check=False)
```

**Step 3: 테스트 통과**

Run: `.venv/bin/pytest tests/test_self_code_improver.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add core/self_code_improver.py tests/test_self_code_improver.py
git commit -m "feat: SelfCodeImprover — subprocess claude TDD 루프 + rate limit"
```

---

### Task 9: ImprovementBus._dispatch에 SelfCodeImprover 연결

**Files:**
- Modify: `core/improvement_bus.py` (`_dispatch`)

**Step 1: dispatch 로직 확장**

```python
def _dispatch(self, signal: ImprovementSignal) -> str | None:
    label = f"[{signal.kind.value}] {signal.target} (priority={signal.priority})"
    logger.info(f"[ImprovementBus] {label}: {signal.suggested_action}")

    if self.dry_run:
        return f"[dry_run] {label}"

    # priority >= 8이고 code 타겟이면 자동 수정 시도
    if signal.priority >= 8 and signal.target.startswith("code:"):
        from core.self_code_improver import SelfCodeImprover
        target_file = signal.target.replace("code:", "")
        improver = SelfCodeImprover()
        result = improver.fix(
            target=target_file,
            error_summary=signal.suggested_action,
            related_files=[target_file],
        )
        if result and result.success:
            return f"[auto_fixed] {label} branch={result.branch}"

    return label
```

**Step 2: 기존 테스트 유지 확인**

Run: `.venv/bin/pytest tests/test_improvement_bus.py -v`
Expected: 기존 6개 PASS

**Step 3: Commit**

```bash
git add core/improvement_bus.py
git commit -m "feat: ImprovementBus._dispatch → priority>=8 코드 신호 자동 수정 연결"
```

---

### Task 10: 재기동 watchdog 구현

**Files:**
- Create: `scripts/restart_watchdog.py`

**Step 1: 구현**

```python
#!/usr/bin/env python3
"""재기동 플래그 감지 → 봇 재시작."""
import subprocess
import sys
import time
from pathlib import Path

RESTART_FLAG = Path(__file__).parent.parent / "data" / ".restart_requested"
REPO_ROOT = Path(__file__).parent.parent

def main() -> None:
    print("[restart_watchdog] 시작")
    while True:
        if RESTART_FLAG.exists():
            print("[restart_watchdog] 재기동 플래그 감지 → 봇 재시작")
            RESTART_FLAG.unlink()
            subprocess.run(["bash", str(REPO_ROOT / "scripts" / "start_all.sh")])
        time.sleep(10)

if __name__ == "__main__":
    main()
```

**Step 2: Commit**

```bash
git add scripts/restart_watchdog.py
git commit -m "feat: restart_watchdog — 재기동 플래그 감지 + start_all.sh 트리거"
```

---

### Task 11: 전체 품질 게이트 + 머지

**Step 1: 전체 테스트 실행**

Run: `.venv/bin/pytest -q --tb=short`
Expected: 기존 4개 pre-existing 실패만 유지, 신규 실패 없음

**Step 2: Ruff**

Run: `.venv/bin/ruff check core/skill_auto_improver.py core/self_code_improver.py core/nl_keyword_applier.py core/routing_approval_store.py`
Expected: 오류 없음

**Step 3: 머지 + 푸시**

```bash
git checkout main
git merge feat/self-improvement-loop-6a-7 --no-ff -m "feat: 자가개선 루프 완성 — Phase 6A~7"
git push origin main
```

---

## 구현 체크리스트 요약

| Phase | 파일 | 테스트 | 기능 |
|-------|------|--------|------|
| 6A | scheduler.py | test_scheduler.py | routing_optimizer cron + /improve_status |
| 6B | routing_approval_store.py, nl_keyword_applier.py, pm_orchestrator.py | test_routing_approval_store.py, test_nl_keyword_applier.py | 승인 게이트 |
| 6C | skill_auto_improver.py, scheduler.py | test_skill_auto_improver.py | autoresearch 루프 |
| 7 | self_code_improver.py, improvement_bus.py, restart_watchdog.py | test_self_code_improver.py | 코드 자가 수정 |
