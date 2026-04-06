# 비동기 블로킹 패턴 수정 가이드

> **작성일**: 2026-03-31
> **작성 조직**: 리서치실 (T-aiorg_pm_bot-958)
> **근거 보고서**: PM 보고서 message_id:3899 (async-sync-audit-report.md)
> **수정 대상**: 실질 위험 3개 파일 — 코드 변경 없이 분석·가이드만 제공

---

## 요약

| 순위 | 파일 | 위험도 | 핵심 문제 | 수정 방법 |
|------|------|--------|-----------|-----------|
| 1 | `core/attachment_analysis.py` | **CRITICAL** | `async def` 안에서 `subprocess.run(timeout=60)` 동기 블로킹 | `asyncio.create_subprocess_exec` 교체 |
| 2 | `goal_tracker/auto_register.py` | **HIGH** | `loop.run_until_complete()` 잔존 — 실행 중 루프 호출 시 deadlock 위험 | `asyncio.run()` 단순화 |
| 3 | `core/session_manager.py` | **HIGH** | DEPRECATED 동기 헬퍼(`time.sleep`, `subprocess.run`) 미제거, async 컨텍스트에서 호출 중 | DEPRECATED 코드 완전 제거 |

---

## 파일 1: `core/attachment_analysis.py` — CRITICAL

### 블로킹 호출 위치

| 라인 | 코드 | 문제 |
|------|------|------|
| 41–47 | `subprocess.run(cmd, ..., timeout=int(...))` | 동기 블로킹 — 이벤트 루프 최대 60초 점유 |
| 45 | `timeout=int(os.environ.get("ATTACHMENT_VISION_BRIDGE_TIMEOUT_SEC", "60"))` | 기본값 60초, 환경변수로 더 늘릴 수 있음 |

### 호출 경로 (콜스택)

```
async def analyze()          ← 비동기 메서드 (public API)
  → _analyze_image_with_bridge()   ← 동기 메서드
    → _run_bridge()                 ← 동기 메서드
      → subprocess.run(timeout=60) ← ❌ 블로킹 지점
```

### 정확한 문제 패턴

```python
# 현재 코드 (문제)
class AttachmentAnalyzer:
    async def analyze(self, attachment: AttachmentContext) -> str:
        # async 메서드에서 동기 메서드 직접 호출
        summary = self._analyze_image_with_bridge(...)   # ← await 없음
        ...

    def _run_bridge(self, raw_cmd: str, path: Path, mime_type: str) -> str:
        proc = subprocess.run(               # ← 이벤트 루프 점유 시작
            cmd,
            capture_output=True,
            text=True,
            timeout=60,                      # ← 최대 60초 블로킹
            check=False,
        )
```

`async def analyze()`가 외부에서 `await analyzer.analyze(attachment)`로 호출될 때,
내부의 `subprocess.run()`이 완료될 때까지 이벤트 루프 전체가 멈춘다.
이 60초 동안 다른 봇의 메시지 수신·응답·타이머 등 모든 비동기 작업이 중단된다.

### 수정 가이드

**방법 A: `asyncio.create_subprocess_exec` 직접 교체 (권장)**

```python
# _run_bridge를 async로 변경
async def _run_bridge(self, raw_cmd: str, path: Path, mime_type: str) -> str:
    if not raw_cmd or not path.exists():
        return ""
    try:
        cmd = shlex.split(raw_cmd) + [str(path), mime_type]
        timeout = int(os.environ.get("ATTACHMENT_VISION_BRIDGE_TIMEOUT_SEC", "60"))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return ""

        if proc.returncode != 0:
            return ""
        return (stdout.decode() or "").strip()
    except Exception:
        return ""

# 호출부도 await 추가
async def analyze(self, attachment: AttachmentContext) -> str:
    if attachment.kind == "photo":
        summary = await self._analyze_image_with_bridge(...)  # await 추가
    ...
```

**방법 B: `asyncio.to_thread` 래핑 (최소 변경)**

```python
async def _run_bridge_async(self, raw_cmd: str, path: Path, mime_type: str) -> str:
    return await asyncio.to_thread(self._run_bridge, raw_cmd, path, mime_type)
```

> ⚠️ 방법 B는 스레드풀을 소비하므로 동시 첨부 처리량이 많을 경우 스레드 고갈 위험 있음. 방법 A 권장.

---

## 파일 2: `goal_tracker/auto_register.py` — HIGH

### 블로킹 호출 위치

| 라인 | 코드 | 문제 |
|------|------|------|
| 216 | `loop = asyncio.get_event_loop()` | Python 3.10+ 실행 중 루프 없을 때 DeprecationWarning |
| 228–230 | `return loop.run_until_complete(...)` | 루프가 실행 중일 때 호출되면 `RuntimeError: This event loop is already running` → deadlock |

### 호출 경로 (콜스택)

```
auto_register_from_report_sync()    ← 동기 래퍼 (외부 호출)
  → asyncio.get_event_loop()        ← deprecated pattern
  → loop.run_until_complete(...)    ← ❌ 실행 중 루프에서 호출 시 deadlock
```

### 정확한 문제 패턴

```python
# 현재 코드 (문제 있는 부분)
def auto_register_from_report_sync(report_text, report_type, **kwargs):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 이 경로는 thread + asyncio.run() 으로 우회 → 정상
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, ...)
                return future.result()
        else:
            return loop.run_until_complete(...)   # ← ❌ 패턴 잔존
    except RuntimeError:
        return asyncio.run(...)                   # fallback
```

**문제 시나리오**:
1. `loop.is_running()` 체크가 False를 반환하지만 실제로는 루프가 실행 중인 경우 (멀티스레드 환경)
2. `asyncio.get_event_loop()`가 Python 3.10+에서 새 루프 대신 예외 발생
3. 외부 라이브러리 (예: `nest_asyncio` 미적용 환경)에서 호출 시

### 수정 가이드

```python
def auto_register_from_report_sync(
    report_text: str,
    report_type: str,
    **kwargs,
) -> AutoRegisterResult:
    """동기 환경에서 auto_register_from_report 호출 편의 래퍼.

    실행 중인 루프가 있으면 별도 스레드에서 새 루프로 실행.
    없으면 asyncio.run()으로 직접 실행 (loop.run_until_complete 제거).
    """
    coro = auto_register_from_report(report_text, report_type, **kwargs)

    try:
        loop = asyncio.get_running_loop()  # 실행 중 루프가 있으면 반환, 없으면 RuntimeError
    except RuntimeError:
        # 실행 중인 루프 없음 → asyncio.run() 사용 (가장 안전)
        return asyncio.run(coro)

    # 실행 중인 루프 있음 → 별도 스레드에서 새 루프 생성
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
```

**핵심 변경점**:
- `asyncio.get_event_loop()` → `asyncio.get_running_loop()` (Python 3.7+ 표준 패턴)
- `loop.run_until_complete()` 완전 제거
- `asyncio.run()` 단일화 (루프 없을 때)

---

## 파일 3: `core/session_manager.py` — HIGH

### 블로킹 호출 위치

| 라인 | 메서드 | 코드 | 문제 |
|------|--------|------|------|
| 54–59 | `_run_tmux()` | `subprocess.run(["tmux", *args], timeout=10)` | 동기 블로킹 — async 메서드에서 반복 호출 |
| 144 | `_wait_for_prompt()` | `time.sleep(0.5)` 폴링 루프 | 이벤트 루프 차단 |
| 280 | `_wait_for_output()` | `subprocess.check_output(["tmux", ...], timeout=5)` | **async 메서드 내부에서** 직접 동기 블로킹 |

### 호출 경로 (콜스택)

```
# 경로 1: time.sleep 블로킹
async def send_message()
  → ensure_session()            ← DEPRECATED 동기 메서드
    → _wait_for_prompt()        ← 동기 폴링 (time.sleep(0.5) 반복)

# 경로 2: subprocess 블로킹 (async 내부)
async def _wait_for_output()   ← async 메서드
  → subprocess.check_output()  ← ❌ 동기 블로킹 (라인 280)

# 경로 3: _run_tmux 반복 호출
async def run_shell_command()
  → _ensure_shell_session_name() → _run_tmux()  ← subprocess.run(timeout=10)
  → send_keys → _run_tmux()
async def send_message()
  → ensure_session() → _run_tmux() × N회
```

### 정확한 문제 패턴

```python
# 문제 1: async 메서드에서 동기 time.sleep (라인 144)
def _wait_for_prompt(self, session_name: str, timeout: float = PROMPT_TIMEOUT) -> bool:
    import time
    start = time.time()
    while time.time() - start < timeout:
        pane = self._run_tmux(...)      # subprocess.run() 블로킹
        if "❯" in pane:
            return True
        time.sleep(0.5)                 # ← ❌ 이벤트 루프 차단
    return False

# 문제 2: async 메서드 내 동기 subprocess (라인 278-283)
async def _wait_for_output(self, output_file, ...):
    while True:
        await asyncio.sleep(0.5)        # ← 여기는 OK
        ...
        # 10초마다 tmux 세션 생존 확인
        if session_name and _dead_check_counter % 20 == 0:
            try:
                subprocess.check_output(    # ← ❌ async 내부에서 동기 블로킹
                    ["tmux", "has-session", "-t", session_name],
                    stderr=subprocess.DEVNULL, timeout=5,
                )
```

### 수정 가이드

**방법: DEPRECATED tmux 동기 헬퍼 완전 제거 + async 래퍼 교체**

```python
# 수정 1: _run_tmux → async 버전으로 교체
async def _run_tmux_async(self, *args: str) -> str:
    """비동기 tmux 명령 실행."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "tmux", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            return ""
        return (stdout + stderr).decode().strip()
    except (FileNotFoundError, OSError):
        return ""

# 수정 2: _wait_for_prompt → async 버전
async def _wait_for_prompt_async(self, session_name: str, timeout: float = PROMPT_TIMEOUT) -> bool:
    """claude 프롬프트 나올 때까지 비동기 폴링."""
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < timeout:
        pane = await self._run_tmux_async("capture-pane", "-t", session_name, "-p")
        if "❯" in pane or "bypass" in pane.lower():
            return True
        await asyncio.sleep(0.5)       # ← time.sleep → await asyncio.sleep
    return False

# 수정 3: _wait_for_output 내부 subprocess.check_output 제거
async def _wait_for_output(self, output_file, progress_callback=None, session_name=None):
    _dead_check_counter = 0
    while True:
        await asyncio.sleep(0.5)
        ...
        if session_name and _dead_check_counter % 20 == 0:
            # subprocess.check_output → _run_tmux_async 교체
            out = await self._run_tmux_async("has-session", "-t", session_name)
            is_dead = bool(out)  # has-session 실패 시 오류 메시지 출력
            if is_dead:
                ...
```

> **핵심**: `_run_tmux()` (동기) 메서드 자체는 `_tmux_available()`, `session_exists()` 등 동기 공개 메서드에서만 사용 가능. async 컨텍스트(send_message, run_shell_command, _wait_for_output 등)에서는 반드시 `_run_tmux_async()`로 교체해야 함.

---

## 우선순위별 수정 순서

```
즉시 (이번 스프린트):
  1. core/attachment_analysis.py  — _run_bridge() async 전환 (영향 범위: 첨부 분석 기능)
  2. goal_tracker/auto_register.py — loop.run_until_complete() 제거 (영향 범위: GoalTracker 자동 등록)

이번 스프린트 내:
  3. core/session_manager.py — DEPRECATED tmux 동기 헬퍼 완전 제거
     (영향 범위: tmux 기반 Claude 세션 — SDK runner 전환 완료 후 삭제 가능)
```

---

## 검증 방법 (수정 후 확인)

```python
# attachment_analysis.py 검증
import asyncio, time

async def test_no_block():
    analyzer = AttachmentAnalyzer()
    start = time.monotonic()
    # 병렬로 다른 코루틴이 실행되는지 확인
    results = await asyncio.gather(
        analyzer.analyze(test_attachment),
        asyncio.sleep(1),  # 이게 블로킹되지 않아야 함
    )
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"이벤트 루프 블로킹 의심: {elapsed:.1f}s"

# auto_register.py 검증
async def test_sync_wrapper():
    # async 컨텍스트에서 sync 래퍼 호출 시 deadlock 없어야 함
    result = await asyncio.to_thread(
        auto_register_from_report_sync, "테스트 텍스트", "daily_retro"
    )
    assert result is not None
```

---

## 참고: 수정 대상 외 안전한 동기 코드

아래 동기 코드는 **이벤트 루프와 무관**하므로 수정 불필요:
- `write_memory_to_claude_md()` — 파일 I/O만 수행, 이벤트 루프 진입 없음
- `inject_context()` — tmux send-keys만 호출 (1회성, timeout 없음)
- `build_performance_context()` — 순수 문자열 조합 (staticmethod)
- `generate_mcp_config()` — 파일 쓰기만 수행

---

*참조: async-sync-audit-report.md, T-aiorg_pm_bot-935-telegram-report.md*
