# Comic Character Concept Real-time Task Visualization Dashboard
# Wireframe Specification v2.0

**Document ID**: T-aiorg-comic-dashboard-wireframes-v2
**Created**: 2026-04-01
**Author**: Design Room (디자인실)
**Status**: Production-ready spec
**Scope**: 3-panel real-time task dashboard for AI agent operations

---

## Table of Contents

1. [Layout Architecture](#1-layout-architecture)
2. [Panel 1: 티켓 처리 현황 (Ticket Status)](#2-panel-1-티켓-처리-현황)
3. [Panel 2: 완료 작업 (Completed Tasks)](#3-panel-2-완료-작업)
4. [Panel 3: 원격 접근 패널 (Remote Access)](#4-panel-3-원격-접근-패널)
5. [Navigation & Layout](#5-navigation--layout)
6. [Loading States](#6-loading-states)
7. [Error States](#7-error-states)
8. [Responsive Behavior](#8-responsive-behavior)
9. [Design Tokens Reference](#9-design-tokens-reference)
10. [Accessibility Summary](#10-accessibility-summary)

---

## 1. Layout Architecture

### 1.1 Three-Panel Arrangement Strategy

The dashboard uses a **tab-based navigation** on mobile (375px), a **stacked two-column grid** on tablet (768px), and a **three-column simultaneous view** on desktop (1280px+).

```
DESKTOP 1280px — Three columns, always visible
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ███ telegram-ai-org DASHBOARD  ●LIVE  [⚙ Settings]  [🔔 3]  [Rocky ▾]       │
├────────────────────┬────────────────────┬──────────────────────────────────────┤
│  PANEL 1           │  PANEL 2           │  PANEL 3                             │
│  티켓 처리 현황      │  완료 작업          │  원격 접근 패널                        │
│  Ticket Status     │  Completed Tasks   │  Remote Access                       │
│  (flex: 1)         │  (flex: 1)         │  (flex: 1)                           │
│                    │                    │                                      │
│  [scrollable]      │  [scrollable]      │  [scrollable]                        │
│                    │                    │                                      │
└────────────────────┴────────────────────┴──────────────────────────────────────┘

TABLET 768px — Panels 1+2 stacked left, Panel 3 right
┌──────────────────────────────┬─────────────────────────────┐
│  PANEL 1  (top, 50%)         │  PANEL 3                    │
│  티켓 처리 현황                │  원격 접근 패널               │
├──────────────────────────────┤  (full height right)        │
│  PANEL 2  (bottom, 50%)      │                             │
│  완료 작업                    │                             │
└──────────────────────────────┴─────────────────────────────┘

MOBILE 375px — Tabs, single panel view
┌────────────────────────────────────────┐
│  ████ AI-ORG DASHBOARD     [☰]        │
├──────────┬──────────┬──────────────────┤
│ [티켓●3] │ [완료  ] │ [원격  ]         │
├──────────┴──────────┴──────────────────┤
│                                        │
│  Active panel content (scrollable)     │
│                                        │
└────────────────────────────────────────┘
```

### 1.2 Global Header Spec

| Element | Type | Width | Notes |
|---------|------|-------|-------|
| Logo + wordmark | Image + Text | 200px | SVG logo, 18px bold |
| Live indicator | Badge + dot | auto | Pulsing green dot, "LIVE" label |
| Settings button | IconButton | 36x36px | Opens global settings drawer |
| Notification bell | IconButton + Badge | 36x36px | Shows unread count |
| User avatar/name | DropdownTrigger | 120px | Avatar 28px, name truncated |

**Header ARIA**:
```html
<header role="banner" aria-label="AI-ORG Dashboard global navigation">
  <nav aria-label="Primary navigation">
    ...tabs...
  </nav>
</header>
```

---

## 2. Panel 1: 티켓 처리 현황

### 2.1 Desktop Wireframe (1280px, ~80 chars wide)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PANEL 1 — 티켓 처리 현황 · Ticket Status                      [↗ Expand]   │
├──────────────────────────────────────────────────────────────────────────────┤
│  SUMMARY BAR                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ PENDING  │  │ RUNNING  │  │ BLOCKED  │  │  DONE    │                   │
│  │   ●  4   │  │  ▶  7    │  │  ⛔  2   │  │  ✓  23   │                  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘                   │
│                                                                              │
│  CONTROLS                                                                    │
│  [🔍 Search tasks...          ] [Filter ▾] [Sort: Priority ▾] [⟳ Live]    │
│                                                                              │
│  FILTER CHIPS: [All ×] [P0] [P1] [개발실] [운영실] [기획실] [+ More]       │
├──────────────────────────────────────────────────────────────────────────────┤
│  TICKET LIST HEADER                                                          │
│  ┌────┬──────────────────────────────┬──────┬───────┬──────────┬─────────┐ │
│  │Prio│ Task                         │Agent │Status │ Elapsed  │Progress │ │
│  ├────┼──────────────────────────────┼──────┼───────┼──────────┼─────────┤ │
│  │ P0 │ ◉ RETRO-27: YAML 기준 추적   │ 🤖👾 │▶RUN  │ 00:04:22 │████░ 80%│ │
│  │    │   [개발실] threshold tracking │ DEV  │       │ ⏱ 5m ETA│         │ │
│  ├────┼──────────────────────────────┼──────┼───────┼──────────┼─────────┤ │
│  │ P0 │ ◉ RETRO-28: config-watch 훅  │ 🤖🔧 │▶RUN  │ 00:02:11 │██░░░ 40%│ │
│  │    │   [개발실] conftest.py hook   │ DEV  │       │ ⏱ 3m ETA│         │ │
│  ├────┼──────────────────────────────┼──────┼───────┼──────────┼─────────┤ │
│  │ P1 │ ○ RETRO-29: ALERT-04 동기화  │ 🤖📊 │⛔BLKD │ 00:08:45 │█░░░░ 20%│ │
│  │    │   [운영실] alert rule sync    │ OPS  │       │ ⚠ Blocked│        │ │
│  ├────┼──────────────────────────────┼──────┼───────┼──────────┼─────────┤ │
│  │ P1 │ ○ RETRO-30: E2E 로그 헤더    │ 🤖📋 │● PEND │ 00:00:00 │░░░░░  0%│ │
│  │    │   [운영실] log header auto    │ OPS  │       │ Queued   │         │ │
│  ├────┼──────────────────────────────┼──────┼───────┼──────────┼─────────┤ │
│  │ P2 │ ○ RETRO-31: UI severity 자동 │ 🤖🎨 │● PEND │ 00:00:00 │░░░░░  0%│ │
│  │    │   [디자인실] design token    │ DSN  │       │ Queued   │         │ │
│  ├────┼──────────────────────────────┼──────┼───────┼──────────┼─────────┤ │
│  │ P2 │ ○ RETRO-32: WCAG 접근성 가이드│ 🤖🎨 │● PEND │ 00:00:00 │░░░░░  0%│ │
│  │    │   [디자인실] WCAG mapping     │ DSN  │       │ Queued   │         │ │
│  ├────┼──────────────────────────────┼──────┼───────┼──────────┼─────────┤ │
│  │ P3 │ ○ RETRO-33: PRD criteria_ver │ 🤖📝 │● PEND │ 00:00:00 │░░░░░  0%│ │
│  │    │   [기획실] version field      │ PLN  │       │ Queued   │         │ │
│  └────┴──────────────────────────────┴──────┴───────┴──────────┴─────────┘ │
│  [Load 6 more tickets...]                                                    │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ EXPANDED ROW — RETRO-27 (click to expand any row)                    │   │
│  │ ──────────────────────────────────────────────────────────────────── │   │
│  │  Agent: DEV-BOT-01 (개발실)   Goal ID: G-aiorg-dev-027               │   │
│  │  Started: 2026-04-01 09:14:22 KST   Parent: RETRO-series             │   │
│  │  Blockers: none   Dependencies: RETRO-28 (in progress)               │   │
│  │  Last log: "Writing criteria_tracking.yaml schema..."                 │   │
│  │  [▶ View Full Log] [⛔ Cancel] [↑ Escalate P0→Critical]             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Mobile Wireframe (375px, ~40 chars wide)

```
┌────────────────────────────────────────┐
│ 티켓 처리 현황                [⟳] [⋮] │
├────────────────────────────────────────┤
│ ┌────────┬────────┬────────┬─────────┐ │
│ │PEND  4 │ RUN  7 │BLKD  2 │DONE  23 │ │
│ └────────┴────────┴────────┴─────────┘ │
├────────────────────────────────────────┤
│ [🔍 Search...       ] [Filter ▾]      │
│ Chips: [All×] [P0] [P1] [+ 3]         │
├────────────────────────────────────────┤
│ ┌──────────────────────────────────┐   │
│ │ P0  ▶RUNNING                     │   │
│ │ 🤖👾 RETRO-27                   │   │
│ │ [개발실] YAML 기준 추적          │   │
│ │ ████░░ 80%   ⏱ 00:04:22        │   │
│ │               [View] [Stop]      │   │
│ └──────────────────────────────────┘   │
│ ┌──────────────────────────────────┐   │
│ │ P0  ▶RUNNING                     │   │
│ │ 🤖🔧 RETRO-28                   │   │
│ │ [개발실] config-watch 훅         │   │
│ │ ██░░░░ 40%   ⏱ 00:02:11        │   │
│ │               [View] [Stop]      │   │
│ └──────────────────────────────────┘   │
│ ┌──────────────────────────────────┐   │
│ │ P1  ⛔BLOCKED                    │   │
│ │ 🤖📊 RETRO-29                   │   │
│ │ [운영실] ALERT-04 동기화         │   │
│ │ █░░░░░ 20%   ⚠ 00:08:45        │   │
│ │               [View] [Retry]     │   │
│ └──────────────────────────────────┘   │
│ ┌──────────────────────────────────┐   │
│ │ P1  ●PENDING                     │   │
│ │ 🤖📋 RETRO-30                   │   │
│ │ [운영실] E2E 로그 헤더           │   │
│ │ ░░░░░░  0%   Queued             │   │
│ └──────────────────────────────────┘   │
│ [+ 9 more tickets]                     │
└────────────────────────────────────────┘
```

### 2.3 Component Inventory — Panel 1

| Component Name | Type | Size (desktop) | States |
|----------------|------|----------------|--------|
| SummaryCountCard | Card | 110x64px | default, highlight |
| SearchInput | Input | 220px wide | idle, focused, filled |
| FilterDropdown | Dropdown | 110px wide | closed, open, selected |
| SortDropdown | Dropdown | 160px wide | closed, open |
| LiveToggle | Toggle | 80px wide | on (pulsing), off |
| FilterChip | Chip | auto | default, active, hover |
| TicketTableHeader | TableRow | full width | default, sortable hover |
| TicketRow | TableRow | full width | default, hover, expanded, selected |
| PriorityBadge | Badge | 28px | P0 (red), P1 (orange), P2 (yellow), P3 (gray) |
| AgentAvatar | Avatar + Icon | 32x32px | online, busy, offline, blocked |
| StatusBadge | Badge | 64px wide | PENDING, RUNNING, BLOCKED, DONE |
| ElapsedTimer | Text (mono) | 80px | counting, paused, exceeded |
| ProgressBar | Bar | 80px | 0-100%, animated fill |
| ETALabel | Text | 60px | normal, warning (>ETA), critical |
| ExpandedDetail | Card | full width | collapsed, expanded (animated) |
| LoadMoreButton | Button | full width | default, loading |
| EmptyStateMascot | Illustration | 200x180px | visible (no tickets) |

### 2.4 Interaction Spec — Panel 1

| Trigger | Action | Feedback |
|---------|--------|----------|
| Click ticket row | Expand/collapse detail | Smooth 200ms height animation, chevron rotates |
| Click [Filter ▾] | Open filter dropdown | Dropdown slides down, backdrop dims slightly |
| Click filter chip | Toggle filter, refresh list | Chip turns solid color, list fades + reloads |
| Click sort column | Sort by that column asc | Column header shows ▲ icon, rows re-order with transition |
| Click sort again | Reverse sort desc | Column shows ▼ icon |
| Toggle Live ON | Subscribe to WebSocket | Green dot pulses, rows update in real-time |
| Toggle Live OFF | Pause updates | Dot goes gray, "Paused" label appears |
| Hover status badge | Show tooltip with timestamp | Tooltip: "Changed to RUNNING at 09:14:22" |
| Click [Cancel] in detail | Confirm modal, then cancel task | Confirmation dialog → progress bar turns red → row moves to BLOCKED |
| Click [Escalate] | Change priority level | Priority badge animates to new color |
| Click [Load more] | Fetch next page | Spinner in button, new rows append with fade-in |
| RETRO-29 BLOCKED row hover | Highlight blocker chip | "Waiting for: ENV_VARS" tooltip |
| Empty state visible | Show mascot animation | Mascot character bounces in with spring physics |

### 2.5 Data Fields — Panel 1

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| ticket_id | string | GoalTracker | e.g. "RETRO-27" |
| title | string | GoalTracker | Max 60 chars, truncated |
| department | enum | GoalTracker | DEV/OPS/DSN/PLN/GRW/RSH |
| agent_id | string | AgentRegistry | e.g. "DEV-BOT-01" |
| agent_avatar_emoji | string | AgentRegistry | Comic emoji character |
| priority | enum | GoalTracker | P0/P1/P2/P3 |
| status | enum | GoalTracker | PENDING/RUNNING/BLOCKED/DONE |
| started_at | ISO8601 | GoalTracker | null if PENDING |
| elapsed_ms | number | computed | Date.now() - started_at |
| progress_pct | number 0-100 | GoalTracker | Agent self-reported |
| eta_ms | number | GoalTracker | Estimated remaining ms |
| blockers | string[] | GoalTracker | List of blocking item IDs |
| last_log_line | string | LogStream | Latest log entry |
| goal_id | string | GoalTracker | Linked goal ID |
| parent_series | string | GoalTracker | e.g. "RETRO-series" |

### 2.6 ARIA Roles & Labels — Panel 1

```html
<section aria-label="티켓 처리 현황 - Ticket Status Panel" role="region">

  <!-- Summary stats -->
  <dl aria-label="Ticket status summary counts">
    <div>
      <dt>Pending tickets</dt>
      <dd aria-live="polite" aria-atomic="true">4</dd>
    </div>
    <div>
      <dt>Running tickets</dt>
      <dd aria-live="polite" aria-atomic="true">7</dd>
    </div>
    <div>
      <dt>Blocked tickets</dt>
      <dd aria-live="assertive" aria-atomic="true">2</dd>
    </div>
    <div>
      <dt>Done tickets</dt>
      <dd aria-live="polite" aria-atomic="true">23</dd>
    </div>
  </dl>

  <!-- Search & filter -->
  <form role="search" aria-label="Filter tickets">
    <input type="search" aria-label="Search tasks by keyword" />
    <button aria-label="Open filter options" aria-haspopup="listbox" />
    <button aria-label="Sort tickets, currently by Priority descending"
            aria-expanded="false" />
    <button aria-label="Live updates toggle"
            aria-pressed="true"
            aria-describedby="live-status-desc" />
    <span id="live-status-desc" class="sr-only">
      When on, ticket list updates automatically every second
    </span>
  </form>

  <!-- Ticket table -->
  <table role="grid" aria-label="Active ticket list" aria-rowcount="13">
    <thead>
      <tr>
        <th scope="col" aria-sort="none">
          <button aria-label="Sort by Priority">Priority</button>
        </th>
        <th scope="col">Task</th>
        <th scope="col">Agent</th>
        <th scope="col" aria-sort="none">
          <button aria-label="Sort by Status">Status</button>
        </th>
        <th scope="col">Elapsed</th>
        <th scope="col">Progress</th>
      </tr>
    </thead>
    <tbody>
      <tr aria-expanded="true" aria-label="RETRO-27, Priority P0, Running, 80% complete">
        <td>
          <span class="badge" aria-label="Priority P0 - Critical">P0</span>
        </td>
        <td>
          <button aria-expanded="true" aria-controls="retro-27-detail">
            RETRO-27: YAML 기준 추적
          </button>
        </td>
        <td>
          <img src="..." alt="DEV-BOT-01 agent avatar" role="img" />
          DEV
        </td>
        <td>
          <span class="badge status-running" aria-label="Status: Running">▶ RUN</span>
        </td>
        <td>
          <time aria-label="Elapsed time: 4 minutes 22 seconds">00:04:22</time>
        </td>
        <td>
          <div role="progressbar" aria-valuenow="80" aria-valuemin="0" aria-valuemax="100"
               aria-label="Task progress: 80 percent complete">
          </div>
        </td>
      </tr>
    </tbody>
  </table>

</section>
```

---

## 3. Panel 2: 완료 작업

### 3.1 Desktop Wireframe (1280px, ~80 chars wide)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PANEL 2 — 완료 작업 · Completed Tasks                         [↗ Expand]   │
├──────────────────────────────────────────────────────────────────────────────┤
│  STATISTICS STRIP                                                            │
│  ╔═══════════╗  ╔══════════════╗  ╔═════════════╗  ╔═══════════════════╗   │
│  ║ TOTAL     ║  ║  AVG DURATION║  ║ SUCCESS RATE║  ║ TODAY'S COUNT     ║   │
│  ║  ✓  23    ║  ║   ⏱  4m 32s ║  ║  📈  97.8%  ║  ║  🔥  8 tasks     ║   │
│  ╚═══════════╝  ╚══════════════╝  ╚═════════════╝  ╚═══════════════════╝   │
│                                                                              │
│  FILTERS                                                                     │
│  Date: [Today ▾]  Agent: [All Agents ▾]  Type: [All Types ▾]  [⟳ Reset]  │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  TIMELINE VIEW                                                               │
│                                                                              │
│  TODAY — 2026-04-01                                                          │
│  ─────────────────────────────────────────────────────────────────────────  │
│  │                                                                           │
│  ●  09:20:44  RETRO-21  ✓DONE  🤖👾 DEV  ████████ 5m 22s                 │
│  │  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  │ [개발실] 진단→액션 자동 연결 파이프라인 구현           ╔═══════╗ │    │
│  │  │ GoalTracker 등록 완료 G-aiorg_pm_bot-007             ║  WOW! ║ │    │
│  │  │ COLLAB dispatch 완료                                  ╚═══════╝ │    │
│  │  │ Duration: 5m 22s  │  P0  │  Agent: DEV-BOT-01                   │    │
│  │  └──────────────────────────────────────────────────────────────────┘    │
│  │                                                                           │
│  ●  09:15:11  RETRO-22  ✓DONE  🤖📊 OPS  █████████ 6m 08s                │
│  │  [운영실] pre-flight 미통과 시 배포 차단 연동                 ╔═════╗   │
│  │  conftest.py SystemExit, ALERT-04 완료                       ║ POW!║   │
│  │  [▼ Expand]                                                   ╚═════╝   │
│  │                                                                           │
│  ●  09:08:53  RETRO-23  ✓DONE  🤖🎨 DSN  ████████ 4m 45s                 │
│  │  [디자인실] UI 실행 블로킹 패턴 적용                                      │
│  │  COLLAB dispatch 완료                                                     │
│  │  [▼ Expand]                                                               │
│  │                                                                           │
│  ●  09:02:17  RETRO-24  ✓DONE  🤖📝 PLN  ███████ 3m 29s                  │
│  │  [기획실] Prevention PRD v1.0 완성 확인                                   │
│  │  [▼ Expand]                                                               │
│  │                                                                           │
│  ─────────────────────────────────────────────────────────────────────────  │
│  YESTERDAY — 2026-03-31                                                      │
│  ─────────────────────────────────────────────────────────────────────────  │
│  │                                                                           │
│  ●  22:44:10  RETRO-25  ✓DONE  🤖📈 GRW  ████████ 5m 01s                 │
│  │  [성장실] 지표→실행 자동 연결 구현                                         │
│  │  [▼ Expand]                                                               │
│  │                                                                           │
│  ●  21:30:05  RETRO-26  ✓DONE  🤖🔬 RSH  ██████ 2m 55s                   │
│  │  [리서치실] 3단계 근본원인 분석 완료                                       │
│  │  [▼ Expand]                                                               │
│  │                                                                           │
│  ─────────────────────────────────────────────────────────────────────────  │
│                              [Load earlier tasks...]                         │
│                                                                              │
│  ╔════════════════════════════════════════════════════════════════════════╗  │
│  ║  🎉  CELEBRATION ZONE — RETRO-21 completed with flying colors!        ║  │
│  ║  ✨ ★ ✨ ★  All blockers cleared! Agent DEV-BOT-01 is on fire!  ★ ✨ ║  │
│  ╚════════════════════════════════════════════════════════════════════════╝  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Mobile Wireframe (375px, ~40 chars wide)

```
┌────────────────────────────────────────┐
│ 완료 작업                     [⟳] [⋮] │
├────────────────────────────────────────┤
│ ┌──────┬──────┬──────┬───────────────┐ │
│ │ ✓ 23 │4m 32 │97.8% │ 🔥 8 Today  │ │
│ └──────┴──────┴──────┴───────────────┘ │
├────────────────────────────────────────┤
│ [Date: Today ▾] [Agent: All ▾]        │
│ [Type: All ▾]              [⟳ Reset]  │
├────────────────────────────────────────┤
│ TODAY — 2026-04-01                     │
│ ────────────────────────────────────── │
│ │                                      │
│ ●  09:20  RETRO-21  ✓DONE            │
│ │  ┌──────────────────────────────┐   │
│ │  │🤖👾 DEV-BOT-01              │   │
│ │  │[개발실] 진단→액션 파이프라인  │   │
│ │  │GoalTracker G-aiorg_pm_bot-007│   │
│ │  │Duration: 5m 22s   P0        │   │
│ │  │              ╔═══════╗      │   │
│ │  │              ║  WOW! ║      │   │
│ │  │              ╚═══════╝      │   │
│ │  └──────────────────────────────┘   │
│ │                                      │
│ ●  09:15  RETRO-22  ✓DONE            │
│ │  🤖📊 OPS  6m 08s    ╔═════╗      │
│ │  [운영실] 배포 차단    ║POW! ║      │
│ │  [▼ More]             ╚═════╝      │
│ │                                      │
│ ●  09:08  RETRO-23  ✓DONE            │
│ │  🤖🎨 DSN  4m 45s                  │
│ │  [디자인실] UI 블로킹              │
│ │  [▼ More]                           │
│ │                                      │
│ ────────────────────────────────────── │
│ YESTERDAY — 2026-03-31                 │
│ ────────────────────────────────────── │
│ ●  22:44  RETRO-25  ✓DONE            │
│ │  🤖📈 GRW  5m 01s                  │
│ │  [+ 3 more yesterday]               │
│                                        │
│ ╔══════════════════════════════════╗   │
│ ║ 🎉  RETRO-21 완료! WOW!        ║   │
│ ║   DEV-BOT-01 is on fire! ✨    ║   │
│ ╚══════════════════════════════════╝   │
└────────────────────────────────────────┘
```

### 3.3 Component Inventory — Panel 2

| Component Name | Type | Size (desktop) | States |
|----------------|------|----------------|--------|
| StatCard | Card | 160x72px | default, highlighted, animated |
| DateFilterDropdown | Dropdown | 120px | closed, open, selection active |
| AgentFilterDropdown | Dropdown | 140px | closed, open |
| TypeFilterDropdown | Dropdown | 130px | closed, open |
| ResetFiltersButton | Button (ghost) | 80px | default, hover, disabled |
| TimelineSectionHeader | Text divider | full width | default |
| TimelineDot | SVG circle | 12px | done (green), failed (red) |
| TimelineConnector | SVG line | 2px wide | continuous, dashed (gap) |
| CompletedTaskCard | Card | full width | collapsed, expanded |
| AgentAvatarEmoji | Text/Img | 24px | per-agent comic emoji |
| DurationBar | Bar | 80px | proportional to avg duration |
| ComicStamp | Overlay badge | 64x32px | WOW, POW, NICE, FAST, ACE |
| ExpandCollapseButton | IconButton | 24px | collapsed ▼, expanded ▲ |
| CelebrationBanner | Banner | full width | visible (on completion), hidden |
| LoadEarlierButton | Button | full width | default, loading |

### 3.4 Interaction Spec — Panel 2

| Trigger | Action | Feedback |
|---------|--------|----------|
| Click collapsed task card | Expand task detail | Card grows, chevron flips, detail fades in 200ms |
| Click expanded task card | Collapse | Reverse animation |
| Change date filter | Re-fetch tasks for date range | Skeleton cards flash, then populated |
| Change agent filter | Filter timeline rows | Non-matching rows fade to 30% opacity then disappear |
| Click [Reset] | Clear all filters, reload full list | All chips clear, list reloads |
| New task completes (real-time) | Prepend to timeline with animation | Card slides in from top, CelebrationBanner fires for 3s |
| CelebrationBanner visible | Auto-dismiss after 5s | Banner fades out smoothly |
| Hover ComicStamp | Expand tooltip with achievement | "Completed in top 10% speed!" |
| Click [Load earlier] | Fetch previous page | Spinner, rows append below current |
| Hover stat card | Tooltip with breakdown | "23 total: 8 today, 15 older" |
| Failed task (if any) | Show red dot + "FAIL" stamp | Red timeline dot, no celebration |

### 3.5 Data Fields — Panel 2

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| ticket_id | string | GoalTracker | |
| title | string | GoalTracker | |
| department | enum | GoalTracker | |
| agent_id | string | AgentRegistry | |
| agent_avatar_emoji | string | AgentRegistry | |
| priority | enum | GoalTracker | P0-P3 |
| status | enum | GoalTracker | Always DONE in this panel |
| completed_at | ISO8601 | GoalTracker | Timestamp of completion |
| duration_ms | number | computed | completed_at - started_at |
| outcome_summary | string | GoalTracker | 1-2 sentence result |
| comic_stamp | enum | computed | WOW/POW/NICE/FAST/ACE based on duration/priority |
| goal_id | string | GoalTracker | |
| total_completed | number | aggregate | Count stat |
| avg_duration_ms | number | aggregate | Running average |
| success_rate_pct | number | aggregate | Done / (Done+Failed) * 100 |
| today_count | number | aggregate | Completed since midnight KST |

### 3.6 Comic Stamp Assignment Logic

| Condition | Stamp | Color |
|-----------|-------|-------|
| Priority P0 + duration < 3min | WOW! | Gold star burst |
| Priority P0 + completed on time | POW! | Red burst |
| Any priority + duration < avg * 0.5 | FAST! | Blue lightning |
| All blockers cleared | ACE! | Green star |
| Default completion | NICE! | Purple circle |

### 3.7 ARIA Roles & Labels — Panel 2

```html
<section aria-label="완료 작업 - Completed Tasks Panel" role="region">

  <!-- Stats -->
  <dl aria-label="Completion statistics">
    <div><dt>Total completed</dt><dd aria-live="polite">23</dd></div>
    <div><dt>Average duration</dt><dd>4 minutes 32 seconds</dd></div>
    <div><dt>Success rate</dt><dd aria-live="polite">97.8%</dd></div>
    <div><dt>Completed today</dt><dd aria-live="polite">8</dd></div>
  </dl>

  <!-- Filters -->
  <fieldset aria-label="Filter completed tasks">
    <legend class="sr-only">Filter options</legend>
    <select aria-label="Filter by date range">...</select>
    <select aria-label="Filter by agent">...</select>
    <select aria-label="Filter by task type">...</select>
    <button aria-label="Reset all filters">Reset</button>
  </fieldset>

  <!-- Timeline -->
  <ol aria-label="Completed tasks timeline, newest first">
    <li aria-label="RETRO-21 completed at 09:20 on April 1st 2026,
                    Duration 5 minutes 22 seconds, Priority P0">
      <article aria-expanded="true">
        <h3>RETRO-21: 진단→액션 자동 연결 파이프라인 구현</h3>
        <p>Agent: DEV-BOT-01 (개발실)</p>
        <p>Duration: 5 minutes 22 seconds</p>
        <!-- Comic stamp -->
        <span aria-label="Achievement stamp: WOW! — Outstanding performance"
              role="img">WOW!</span>
        <button aria-expanded="true"
                aria-controls="retro-21-detail"
                aria-label="Collapse RETRO-21 details">▲ Collapse</button>
        <div id="retro-21-detail" role="region">
          <!-- expanded content -->
        </div>
      </article>
    </li>
  </ol>

  <!-- Celebration banner -->
  <div role="status" aria-live="polite" aria-atomic="true"
       aria-label="Task completion celebration">
    🎉 RETRO-21 completed with flying colors! Agent DEV-BOT-01 is on fire!
  </div>

</section>
```

---

## 4. Panel 3: 원격 접근 패널

### 4.1 Desktop Wireframe (1280px, ~80 chars wide)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PANEL 3 — 원격 접근 패널 · Remote Access               [⚠ ALERT: 1]  [↗]  │
├──────────────────────────────────────────────────────────────────────────────┤
│  AGENT CONNECTION STATUS                                                     │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ AGENT           STATUS   HEALTH    LAST PING   TASKS  ACTIONS        │   │
│  ├─────────────────────────────────────────────────────────────────────-┤   │
│  │ 🤖👾 DEV-BOT-01  ●ONLINE  ████ 98%  0.3s ago   2 run  [▶][⏸][⛔]  │   │
│  │ 🤖📊 OPS-BOT-01  ●ONLINE  ███░ 87%  0.7s ago   1 run  [▶][⏸][⛔]  │   │
│  │ 🤖🎨 DSN-BOT-01  ●ONLINE  ████ 95%  0.4s ago   0 run  [▶][⏸][⛔]  │   │
│  │ 🤖📝 PLN-BOT-01  ⚫IDLE   ██░░ 62%  4.2s ago   0 run  [▶][⏸][⛔]  │   │
│  │ 🤖📈 GRW-BOT-01  ●ONLINE  ████ 91%  0.5s ago   0 run  [▶][⏸][⛔]  │   │
│  │ 🤖🔬 RSH-BOT-01  ◑ BUSY   ███░ 78%  1.1s ago   1 run  [▶][⏸][⛔]  │   │
│  │ 🤖🔮 PM-BOT-01   ●ONLINE  ████ 99%  0.1s ago   0 run  [▶][⏸][⛔]  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  EMERGENCY CONTROLS                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  ╔═══════════════════════════════════════════════════════════════╗   │   │
│  │  ║  ⚠ EMERGENCY STOP   [████████████ STOP ALL AGENTS ████████]  ║   │   │
│  │  ╚═══════════════════════════════════════════════════════════════╝   │   │
│  │  Hold for 2s to activate · Requires confirmation · Logged to audit    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  MANUAL TRIGGER                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Agent:   [DEV-BOT-01       ▾]   Task: [RETRO-27             ▾]     │   │
│  │  Action:  [run / resume / retry ▾]        [▶ TRIGGER TASK]           │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  LIVE LOG STREAM                                                             │
│  ┌╔═══════════════════════════════════════════════════════════════════╗┐    │
│  ╠╣ $ agent-log-stream --follow --agent=DEV-BOT-01 --tail=50        ╠╣    │
│  ╠╣───────────────────────────────────────────────────────────────────╠╣    │
│  ╠╣ 09:20:44 [DEV-BOT-01] INFO  Task RETRO-27 progress: 80%         ╠╣    │
│  ╠╣ 09:20:43 [DEV-BOT-01] DEBUG Writing criteria_tracking.yaml...   ╠╣    │
│  ╠╣ 09:20:41 [DEV-BOT-01] INFO  Validating YAML schema v1           ╠╣    │
│  ╠╣ 09:20:38 [OPS-BOT-01] WARN  ALERT-04 sync: missing field        ╠╣    │
│  ╠╣ 09:20:35 [DEV-BOT-01] DEBUG Opening file criteria_tracking.yaml ╠╣    │
│  ╠╣ 09:20:32 [PM-BOT-01]  INFO  Morning goals dispatched: 11 tasks  ╠╣    │
│  ╠╣ 09:20:29 [OPS-BOT-01] INFO  pre-flight check: PASS (all 6/6)   ╠╣    │
│  ╠╣ 09:20:26 [DEV-BOT-01] INFO  Task RETRO-28 starting...           ╠╣    │
│  ╠╣ 09:20:22 [RSH-BOT-01] INFO  Research context loaded v1.2.0      ╠╣    │
│  ╠╣ > _ (cursor blinks)                                              ╠╣    │
│  ╚╩═══════════════════════════════════════════════════════════════════╩╝    │
│                                                                              │
│  LOG CONTROLS:  Agent: [All ▾]  Level: [INFO ▾]  [⏸ Pause] [⬇ Download]  │
│                                                                              │
│  CONNECTION HEALTH METRICS                                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  WebSocket: ●CONNECTED  Latency: 42ms  Reconnects: 0  Uptime: 4h12m │   │
│  │  Messages/min: 127   Dropped: 0   Queue depth: 0                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Mobile Wireframe (375px, ~40 chars wide)

```
┌────────────────────────────────────────┐
│ 원격 접근 패널           [⚠1] [⟳] [⋮]│
├────────────────────────────────────────┤
│ AGENT STATUS                           │
│ ┌──────────────────────────────────┐   │
│ │🤖👾 DEV-BOT-01  ●ON  ████ 98%  │   │
│ │  2 tasks running  [▶][⏸][⛔]   │   │
│ └──────────────────────────────────┘   │
│ ┌──────────────────────────────────┐   │
│ │🤖📊 OPS-BOT-01  ●ON  ███░ 87%  │   │
│ │  1 task running   [▶][⏸][⛔]   │   │
│ └──────────────────────────────────┘   │
│ ┌──────────────────────────────────┐   │
│ │🤖🎨 DSN-BOT-01  ●ON  ████ 95%  │   │
│ │  0 tasks          [▶][⏸][⛔]   │   │
│ └──────────────────────────────────┘   │
│ ┌──────────────────────────────────┐   │
│ │🤖📝 PLN-BOT-01  ⚫IDLE ██░░ 62%│   │
│ │  0 tasks          [▶][⏸][⛔]   │   │
│ └──────────────────────────────────┘   │
│ [+ 3 more agents]                      │
├────────────────────────────────────────┤
│ ╔══════════════════════════════════╗   │
│ ║ ⚠ EMERGENCY STOP               ║   │
│ ║ [████ HOLD 2s TO STOP ALL ████] ║   │
│ ╚══════════════════════════════════╝   │
├────────────────────────────────────────┤
│ MANUAL TRIGGER                         │
│ Agent: [DEV-BOT-01 ▾]                 │
│ Task:  [RETRO-27   ▾]                 │
│ Action:[run/resume ▾]  [▶ TRIGGER]    │
├────────────────────────────────────────┤
│ LIVE LOG                               │
│ ┌╔════════════════════════════════╗┐   │
│ ╠╣$ log --agent=DEV-BOT-01       ╠╣   │
│ ╠╣────────────────────────────────╠╣   │
│ ╠╣09:20:44 INFO progress: 80%    ╠╣   │
│ ╠╣09:20:43 DEBUG Writing yaml... ╠╣   │
│ ╠╣09:20:38 WARN missing field    ╠╣   │
│ ╠╣09:20:32 INFO goals: 11 tasks  ╠╣   │
│ ╠╣> _ (blinking cursor)          ╠╣   │
│ ╚╩════════════════════════════════╩╝   │
│ [Agent: All▾] [Level: INFO▾] [⏸][⬇]  │
├────────────────────────────────────────┤
│ WS: ●CONN  42ms  0 drops  4h12m up    │
└────────────────────────────────────────┘
```

### 4.3 Component Inventory — Panel 3

| Component Name | Type | Size (desktop) | States |
|----------------|------|----------------|--------|
| AgentStatusTable | Table | full width | default |
| AgentStatusRow | TableRow | full width | online, idle, busy, offline, error |
| AgentStatusDot | SVG circle | 10px | online (green), idle (gray), busy (amber), offline (red) |
| AgentHealthBar | Progress bar | 60px | 0-100%, color-coded |
| PingLatency | Text (mono) | 50px | normal (<1s), warning (1-3s), critical (>3s) |
| AgentTriggerButton | IconButton | 28px | play ▶, pause ⏸ |
| AgentStopButton | IconButton | 28px | stop ⛔ — per agent |
| EmergencyStopButton | Button (danger) | full width | idle, hold-progress (2s animation), confirming, stopping |
| ManualTriggerAgentSelect | Select | 180px | closed, open |
| ManualTriggerTaskSelect | Select | 180px | closed, open |
| ManualTriggerActionSelect | Select | 150px | closed, open |
| TriggerSubmitButton | Button (primary) | 130px | default, loading, success, error |
| LogStreamTerminal | Code block | full width, 240px height | streaming, paused, loading |
| LogLine | Text row | full width | INFO (white), DEBUG (gray), WARN (yellow), ERROR (red) |
| LogAgentFilter | Select | 120px | closed, open |
| LogLevelFilter | Select | 100px | closed, open |
| LogPauseButton | Button | 80px | streaming, paused |
| LogDownloadButton | Button | 100px | default, downloading |
| ConnectionHealthBar | Info bar | full width | connected, reconnecting, disconnected |
| AlertBadge | Badge | 24px | count (N), zero (hidden) |

### 4.4 Interaction Spec — Panel 3

| Trigger | Action | Feedback |
|---------|--------|----------|
| Click ▶ (per agent) | Dispatch new task to agent | Button spins, agent status flips to BUSY |
| Click ⏸ (per agent) | Pause agent task queue | Agent row dims, status changes to IDLE |
| Click ⛔ (per agent) | Confirm modal → stop one agent | Modal: "Stop DEV-BOT-01? Active task will be interrupted." → confirm → agent goes OFFLINE |
| Hold Emergency Stop (2s) | Progressive fill animation | Button fills red over 2s; release before 2s = cancel |
| Emergency Stop confirmed | Send stop-all signal | All agent rows flash red, status = STOPPED, banner fires |
| Change Manual Trigger agent | Update task select options | Task dropdown repopulates with that agent's pending tasks |
| Click ▶ TRIGGER TASK | Send manual task dispatch | Button → loading → success tick + log line appears |
| Log stream scrolls to bottom | Auto-follow enabled | New lines append, scroll stays at bottom |
| Log stream manually scrolled up | Pause auto-follow | "Paused — scroll to bottom to resume" chip appears |
| Scroll to bottom again | Resume auto-follow | Chip disappears, auto-scroll resumes |
| Click ⏸ pause log | Freeze log output | Buffer incoming lines, show "(paused — N buffered)" |
| Click ▶ resume log | Flush buffer + resume | Lines flush with fast animation |
| Click ⬇ download | Download current log as .txt | Browser file download |
| WebSocket disconnects | Show reconnecting state | Health bar turns amber, "Reconnecting..." text, retry spinner |
| WebSocket reconnects | Restore streaming | Health bar turns green, latency updates |
| Agent goes OFFLINE | Red dot + alert badge +1 | AgentStatusRow row turns red, AlertBadge increments |
| Hover ping latency | Tooltip with history | Mini sparkline of last 60s ping times |

### 4.5 Data Fields — Panel 3

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| agent_id | string | AgentRegistry | e.g. "DEV-BOT-01" |
| agent_name | string | AgentRegistry | Display name |
| agent_emoji | string | AgentRegistry | Comic avatar |
| department | enum | AgentRegistry | DEV/OPS/DSN/PLN/GRW/RSH/PM |
| connection_status | enum | WebSocket | online/idle/busy/offline/error |
| health_pct | number 0-100 | AgentMonitor | Composite health score |
| last_ping_ms | number | WebSocket | Milliseconds since last heartbeat |
| active_task_count | number | GoalTracker | Tasks currently RUNNING |
| log_lines | LogLine[] | LogStream | Streaming array |
| log_line.timestamp | ISO8601 | LogStream | |
| log_line.agent_id | string | LogStream | |
| log_line.level | enum | LogStream | INFO/DEBUG/WARN/ERROR |
| log_line.message | string | LogStream | |
| ws_connected | boolean | WebSocket | |
| ws_latency_ms | number | WebSocket | Round-trip ping |
| ws_reconnect_count | number | WebSocket | Session reconnects |
| ws_uptime_ms | number | computed | Time since connection |
| ws_messages_per_min | number | WebSocket | Throughput |
| ws_dropped_count | number | WebSocket | Messages lost |
| ws_queue_depth | number | WebSocket | Pending message queue |

### 4.6 Emergency Stop Behavior Detail

```
State machine for Emergency Stop button:

  IDLE
    ↓ (user starts holding)
  HOLDING (2s progressive fill, can cancel by releasing)
    ↓ (2s elapsed)
  CONFIRMING (modal dialog)
    ↓ [Confirm]           ↓ [Cancel]
  STOPPING              IDLE
    ↓ (all agents ACK)
  STOPPED (all agents offline)
    → System shows red banner
    → Audit log entry written
    → Notification sent to Rocky
    → Manual restart required
```

### 4.7 ARIA Roles & Labels — Panel 3

```html
<section aria-label="원격 접근 패널 - Remote Access Panel" role="region">

  <!-- Agent status table -->
  <table aria-label="Agent connection status">
    <caption class="sr-only">
      Real-time connection status for all AI agents.
      Updated every second.
    </caption>
    <thead>
      <tr>
        <th scope="col">Agent</th>
        <th scope="col">Connection Status</th>
        <th scope="col">Health Score</th>
        <th scope="col">Last Ping</th>
        <th scope="col">Active Tasks</th>
        <th scope="col">Actions</th>
      </tr>
    </thead>
    <tbody aria-live="polite" aria-relevant="additions text">
      <tr aria-label="DEV-BOT-01, online, health 98%, last ping 0.3 seconds ago, 2 active tasks">
        <td>
          <span role="img" aria-label="DEV-BOT-01 robot developer character">🤖👾</span>
          DEV-BOT-01
        </td>
        <td>
          <span role="status" aria-label="Connection status: Online">
            <span class="status-dot" aria-hidden="true">●</span>
            Online
          </span>
        </td>
        <td>
          <div role="meter" aria-valuenow="98" aria-valuemin="0" aria-valuemax="100"
               aria-label="Health score: 98 percent"></div>
        </td>
        <td aria-label="Last ping: 0.3 seconds ago">0.3s ago</td>
        <td>2 running</td>
        <td>
          <button aria-label="Trigger new task for DEV-BOT-01">▶ Run</button>
          <button aria-label="Pause DEV-BOT-01 task queue">⏸ Pause</button>
          <button aria-label="Stop DEV-BOT-01 — will interrupt active task"
                  aria-describedby="stop-warning">⛔ Stop</button>
        </td>
      </tr>
    </tbody>
  </table>

  <!-- Emergency stop -->
  <div role="region" aria-label="Emergency controls">
    <button
      aria-label="Emergency stop — hold for 2 seconds to stop all agents"
      aria-describedby="emergency-stop-desc"
      aria-pressed="false"
    >STOP ALL AGENTS</button>
    <p id="emergency-stop-desc">
      Hold button for 2 seconds. Requires confirmation.
      All active tasks will be interrupted. Action is logged.
    </p>
  </div>

  <!-- Manual trigger form -->
  <form aria-label="Manually trigger a task for a specific agent">
    <label for="trigger-agent">Select agent</label>
    <select id="trigger-agent">...</select>
    <label for="trigger-task">Select task</label>
    <select id="trigger-task">...</select>
    <label for="trigger-action">Action type</label>
    <select id="trigger-action">...</select>
    <button type="submit" aria-describedby="trigger-desc">Trigger Task</button>
    <p id="trigger-desc" class="sr-only">
      Manually dispatch a task to the selected agent.
    </p>
  </form>

  <!-- Log stream -->
  <section aria-label="Live agent log stream">
    <div role="log" aria-live="polite" aria-atomic="false"
         aria-label="Streaming agent log output, newest entries appended at bottom"
         aria-relevant="additions">
      <!-- Log lines appended here by JS -->
    </div>
    <div role="toolbar" aria-label="Log stream controls">
      <select aria-label="Filter log by agent">...</select>
      <select aria-label="Filter log by level">...</select>
      <button aria-label="Pause log stream" aria-pressed="false">⏸ Pause</button>
      <button aria-label="Download log as text file">⬇ Download</button>
    </div>
  </section>

  <!-- Connection health -->
  <section aria-label="WebSocket connection health metrics">
    <dl>
      <dt>Connection status</dt>
      <dd role="status" aria-live="polite">Connected</dd>
      <dt>Latency</dt>
      <dd aria-live="polite">42 milliseconds</dd>
      <dt>Session reconnects</dt>
      <dd>0</dd>
      <dt>Uptime</dt>
      <dd>4 hours 12 minutes</dd>
    </dl>
  </section>

</section>
```

---

## 5. Navigation & Layout

### 5.1 Desktop Layout — Three Columns

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  GLOBAL HEADER (height: 56px, position: sticky top)                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  [LOGO] telegram-ai-org    ●LIVE  [⚙] [🔔 3]  [Rocky ▾]            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
├────────────────────┬────────────────────┬──────────────────────────────────-┤
│                    │                    │                                    │
│  PANEL 1           │  PANEL 2           │  PANEL 3                          │
│  width: 33.3%      │  width: 33.3%      │  width: 33.3%                     │
│  min-width: 360px  │  min-width: 360px  │  min-width: 360px                 │
│                    │                    │                                    │
│  overflow-y: auto  │  overflow-y: auto  │  overflow-y: auto                 │
│  height: calc(     │  height: calc(     │  height: calc(                    │
│    100vh - 56px)   │    100vh - 56px)   │    100vh - 56px)                  │
│                    │                    │                                    │
└────────────────────┴────────────────────┴────────────────────────────────────┘
```

### 5.2 Panel Resize Handles

On desktop, panels are separated by 1px dividers that become 4px drag handles on hover, allowing users to adjust column widths. Min-width per panel is 280px. A "reset layout" button in header settings reverts to equal thirds.

### 5.3 Collapsible Panels

Each panel header has a `[↗ Expand]` / `[↙ Collapse]` button:
- Expand: Panel takes 50% width, other two share the remaining 50%.
- Collapse: Panel collapses to 48px icon-only sidebar strip.
- Collapsed strip shows panel icon + live count badge.

```
PANEL 1 EXPANDED + PANEL 2+3 COMPRESSED
┌─────────────────────────────────────────┬──────────┬──────────┐
│                                         │ 2 ●7     │ 3 ⚠1    │
│  PANEL 1 (50% width, expanded)          │ (24px)   │ (24px)   │
│                                         │          │          │
└─────────────────────────────────────────┴──────────┴──────────┘
```

### 5.4 Tab Navigation (Mobile)

```
Tab bar: position fixed bottom (mobile), position sticky top under header (tablet-portrait)
Active tab indicator: 2px underline, primary brand color
Badge on tab: live count of active/blocked items

[티켓 ●13] — Panel 1 tab, shows active ticket count
[완료    ] — Panel 2 tab, no badge (historical)
[원격  ⚠1] — Panel 3 tab, shows alert count
```

### 5.5 Keyboard Navigation

| Key | Action |
|-----|--------|
| Tab / Shift+Tab | Move focus between interactive elements |
| Enter / Space | Activate buttons, expand rows |
| Arrow keys | Navigate within table rows |
| Escape | Close dropdowns, collapse expanded rows, dismiss modals |
| Ctrl+1/2/3 | Jump to Panel 1/2/3 (desktop) |
| F5 | Force refresh all panels |
| ? | Open keyboard shortcuts help dialog |

---

## 6. Loading States

### 6.1 Panel 1 — Ticket Status Loading

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PANEL 1 — 티켓 처리 현황                                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│  SUMMARY BAR (skeleton)                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │░░░░░░░░░░│  │░░░░░░░░░░│  │░░░░░░░░░░│  │░░░░░░░░░░│                   │
│  │░░░░░░░░░░│  │░░░░░░░░░░│  │░░░░░░░░░░│  │░░░░░░░░░░│                   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘                   │
│                                                                              │
│  ░░░░░░░░░░░░░░░░░░░░░ [Search skeleton] ░░░░░░░░░░                        │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ ░░░░ │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ ░░░░ │ ░░░░ │ ░░░░░ │ ░░░░░ │   │
│  ├──────┼────────────────────────────────┼──────┼──────┼───────┼───────┤   │
│  │ ░░░░ │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ ░░░░ │ ░░░░ │ ░░░░░ │ ░░░░░ │   │
│  │ ░░░░ │ ░░░░░░░░░░░░░░░░                │ ░░░░ │ ░░░░ │ ░░░░░ │ ░░░░░ │   │
│  ├──────┼────────────────────────────────┼──────┼──────┼───────┼───────┤   │
│  │ ░░░░ │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ ░░░░ │ ░░░░ │ ░░░░░ │ ░░░░░ │   │
│  └──────┴────────────────────────────────┴──────┴──────┴───────┴───────┘   │
│                                                                              │
│               ⟳  Loading tickets from GoalTracker...                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Skeleton animation**: `background: linear-gradient(90deg, #2a2a2a 25%, #3a3a3a 50%, #2a2a2a 75%)` sweeping left-to-right at 1.4s loop.

**Loading timeout**: After 10s with no data, show error state (see section 7).

**aria announcement**: `<div aria-live="polite" role="status">Loading ticket data...</div>` → updates to "Ticket data loaded, 13 active tickets" on success.

### 6.2 Panel 2 — Completed Tasks Loading

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PANEL 2 — 완료 작업                                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│  ░░░░░░░░░ ░░░░░░░░░░░░░░ ░░░░░░░░░░░░░ ░░░░░░░░░░░░░  ← stat cards       │
│                                                                              │
│  TODAY                                                                       │
│  ─────────────────────────────────────────────────────                      │
│  │                                                                           │
│  ● ░░░░░░░░  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  ← skeleton row    │
│  │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                                          │
│  │                                                                           │
│  ● ░░░░░░░░  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                     │
│  │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                                          │
│  │                                                                           │
│  ● ░░░░░░░░  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                     │
│                                                                              │
│               ⟳  Loading completed tasks...                                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 6.3 Panel 3 — Remote Access Loading

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PANEL 3 — 원격 접근 패널                                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│  CONNECTING TO AGENT REGISTRY...                                             │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 🤖 DEV-BOT-01   ◌ Connecting...                                      │   │
│  │ 🤖 OPS-BOT-01   ◌ Connecting...                                      │   │
│  │ 🤖 DSN-BOT-01   ◌ Connecting...                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌╔═════════════════════════════════════════════════════════════════════╗┐   │
│  ╠╣ $ Establishing WebSocket connection to log stream...              ╠╣   │
│  ╠╣ > Authenticating...                                               ╠╣   │
│  ╠╣ > Connecting to ws://aiorg-log-stream:8080/ws ⟳                  ╠╣   │
│  ╚╩═════════════════════════════════════════════════════════════════════╩╝   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 6.4 Partial Load State

When Panel 3 partially connects (some agents online, log stream still connecting):

```
│ 🤖 DEV-BOT-01   ●ONLINE  ████ 98%  ← loaded
│ 🤖 OPS-BOT-01   ●ONLINE  ███░ 87%  ← loaded
│ 🤖 DSN-BOT-01   ◌ Connecting... ← still loading
│ 🤖 PLN-BOT-01   ◌ Connecting... ← still loading
```

---

## 7. Error States

### 7.1 Panel 1 — Ticket Load Error

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PANEL 1 — 티켓 처리 현황                                    [↗ Expand]    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │                    😵 Uh-oh!                                         │   │
│  │                    (mascot character, confused pose)                 │   │
│  │                                                                      │   │
│  │         GoalTracker connection failed                                │   │
│  │         Error: ECONNREFUSED — cannot reach goal-tracker:3000         │   │
│  │                                                                      │   │
│  │         Last successful load: 09:18:44 KST (2 min ago)              │   │
│  │                                                                      │   │
│  │         [⟳ Retry Now]   [📋 Copy Error Details]                    │   │
│  │                                                                      │   │
│  │         Auto-retry in: 00:00:27 ████████████░░░░░░░                 │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ⚠ Showing cached data from 09:18:44 (may be stale)                         │
│  ─────────────────────────────────────────────────────────────────────────   │
│  [stale ticket rows rendered with 50% opacity and "CACHED" watermark]       │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Panel 1 — Empty State (No Active Tickets)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PANEL 1 — 티켓 처리 현황                                    [↗ Expand]    │
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ PENDING 0│  │ RUNNING 0│  │ BLOCKED 0│  │  DONE 23 │                   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘                   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │                    (°‿°)  ← happy mascot character                   │   │
│  │                                                                      │   │
│  │              모든 작업 완료!  All tasks done!                        │   │
│  │                                                                      │   │
│  │      No active tickets. Agents are standing by.                      │   │
│  │      Next scheduled run: morning_goals.py at 09:00 KST tomorrow      │   │
│  │                                                                      │   │
│  │      [▶ Trigger Manual Task]   [📊 View Completed Tasks]             │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 7.3 Panel 2 — History Load Error

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PANEL 2 — 완료 작업                                          [↗ Expand]   │
├──────────────────────────────────────────────────────────────────────────────┤
│  ⚠  Failed to load task history                                             │
│  Error: Database query timeout after 30s                                    │
│                                                                              │
│  Statistics from cache:                                                      │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────┐  ┌───────────────────┐   │
│  │ TOTAL    │  │  AVG DURATION│  │ SUCCESS RATE│  │ TODAY'S COUNT     │   │
│  │  ✓  23   │  │   ⚠ N/A     │  │  ⚠ N/A     │  │  ⚠ N/A           │   │
│  │ (cached) │  │   (failed)   │  │  (failed)   │  │  (failed)         │   │
│  └──────────┘  └──────────────┘  └─────────────┘  └───────────────────┘   │
│                                                                              │
│  [⟳ Retry]  Auto-retry in 00:00:45                                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 7.4 Panel 3 — Agent Offline Error

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PANEL 3 — 원격 접근 패널                            [⚠ ALERT: 3]  [↗]    │
├──────────────────────────────────────────────────────────────────────────────┤
│  AGENT CONNECTION STATUS                                                     │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 🤖👾 DEV-BOT-01  ●ONLINE  ████ 98%  ← OK                           │   │
│  │ 🤖📊 OPS-BOT-01  🔴 OFFLINE ████ 0%  LAST SEEN: 3m ago             │   │
│  │                 ⚠ Reconnection attempts: 12/20                      │   │
│  │                 [🔄 Force Reconnect]  [📋 View Crash Log]           │   │
│  │ 🤖🎨 DSN-BOT-01  🔴 ERROR  ████ 12%  LAST SEEN: 7m ago             │   │
│  │                 ⚠ Error: Out of memory — SIGKILL received           │   │
│  │                 [🔄 Force Restart]  [📋 View Crash Log]             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  LOG STREAM                                                                  │
│  ┌╔═══════════════════════════════════════════════════════════════════╗┐    │
│  ╠╣ 09:17:22 [OPS-BOT-01]  ERROR  Connection lost: SIGTERM           ╠╣    │
│  ╠╣ 09:17:20 [DSN-BOT-01]  FATAL  Out of memory, process killed      ╠╣    │
│  ╠╣ 09:17:18 [DSN-BOT-01]  ERROR  Memory usage: 98% — critical       ╠╣    │
│  ╠╣ > WebSocket: ⚠ RECONNECTING (attempt 13/20)...                   ╠╣    │
│  ╚╩═══════════════════════════════════════════════════════════════════╩╝    │
│  WebSocket: ⚠ RECONNECTING  Latency: N/A  Reconnects: 13  Uptime: 4h09m  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 7.5 Panel 3 — WebSocket Disconnected (Full)

```
┌╔═══════════════════════════════════════════════════════════════════════════╗┐
╠╣  ⚠  LOG STREAM DISCONNECTED                                              ╠╣
╠╣  WebSocket connection closed. Last message: 09:22:11 (1m ago)            ╠╣
╠╣  Reason: 1006 — Abnormal closure                                          ╠╣
╠╣  Buffered messages since disconnect: 47                                   ╠╣
╠╣  Reconnection: Attempt 3/10 — next in 8s ████████░░░░░░░░░░░░          ╠╣
╠╣  [⟳ Reconnect Now]   [📋 Download Buffered Logs]                        ╠╣
╚╩═══════════════════════════════════════════════════════════════════════════╩╝
```

---

## 8. Responsive Behavior

### 8.1 Breakpoint Definitions

| Breakpoint | Viewport Width | Layout Mode | Panel Arrangement |
|------------|----------------|-------------|-------------------|
| XL | ≥1440px | Three-column | 33% + 33% + 34% |
| LG | 1280px–1439px | Three-column | 33% + 33% + 34% |
| MD | 768px–1279px | Two-column | (P1+P2 stacked, 55%) + (P3, 45%) |
| SM | 480px–767px | Single + Tabs | Tab nav, single panel view |
| XS | <480px (375px) | Single + Tabs | Tab nav, full-width single panel |

### 8.2 1280px → 768px Transition

```
1280px (three-column):
┌─────────────┬─────────────┬─────────────┐
│   Panel 1   │   Panel 2   │   Panel 3   │
│    33.3%    │    33.3%    │    33.4%    │
└─────────────┴─────────────┴─────────────┘

768px (two-column, stacked left):
┌───────────────────┬──────────────────┐
│     Panel 1       │                  │
│  (top-left, 50%)  │    Panel 3       │
├───────────────────┤  (right, 100%)   │
│     Panel 2       │                  │
│ (bottom-left, 50%)│                  │
└───────────────────┴──────────────────┘
```

**Transition animation**: 300ms ease-in-out, panels reflow via CSS Grid `grid-template-columns` change.

### 8.3 768px → 375px Transition

```
768px (two-column):
[as above]

480px (single panel + bottom tabs):
┌────────────────────────────────────────┐
│ Global header                          │
├────────────────────────────────────────┤
│                                        │
│ Active panel (full width)              │
│                                        │
│ [scrollable content]                   │
│                                        │
│                                        │
├────────────────────────────────────────┤
│ [티켓 ●7] [완료    ] [원격  ⚠1]      │  ← bottom tab bar
└────────────────────────────────────────┘
```

### 8.4 Component-Level Responsive Changes

| Component | 1280px | 768px | 375px |
|-----------|--------|-------|-------|
| Ticket table | Full table with columns | Collapsed to card layout | Card layout, less info |
| Summary stat cards | 4 cards in a row | 4 cards in a row | 2x2 grid |
| Filter controls | Inline row | 2 rows | Stacked, filter in drawer |
| Agent status table | Full table | Card grid | Card list |
| Log stream height | 240px | 200px | 160px |
| Comic stamps | 64x32px full | 48x24px | 40x20px |
| Emergency stop button | Full width banner | Full width | Full width, larger hit target (48px min) |
| Panel header | Shows title + controls | Shows title + icon controls | Shows short title + icon |

### 8.5 Touch Interaction Adaptations (Mobile)

- All tap targets: minimum 44x44px (iOS HIG / WCAG 2.5.5)
- Swipe left on ticket row: reveal quick actions (Stop / View)
- Swipe between panels: not supported (tabs preferred for clarity)
- Long press on agent stop button (same as 2s hold emergency stop on desktop)
- Pull-to-refresh on each panel: triggers data reload

---

## 9. Design Tokens Reference

### 9.1 Color Palette

```css
/* Status colors */
--color-status-pending:   #8B8FA8;   /* gray */
--color-status-running:   #4CAF50;   /* green */
--color-status-blocked:   #F44336;   /* red */
--color-status-done:      #2196F3;   /* blue */
--color-status-idle:      #607D8B;   /* blue-gray */
--color-status-busy:      #FF9800;   /* amber */

/* Priority colors */
--color-priority-p0:      #FF1744;   /* critical red */
--color-priority-p1:      #FF6D00;   /* high orange */
--color-priority-p2:      #FFD600;   /* medium yellow */
--color-priority-p3:      #9E9E9E;   /* low gray */

/* Comic stamp colors */
--color-stamp-wow:        #FFD700;   /* gold */
--color-stamp-pow:        #FF4444;   /* red */
--color-stamp-nice:       #AA44FF;   /* purple */
--color-stamp-fast:       #44AAFF;   /* blue */
--color-stamp-ace:        #44FF88;   /* green */

/* Log line colors */
--color-log-info:         #E8E8E8;   /* near-white */
--color-log-debug:        #888888;   /* mid-gray */
--color-log-warn:         #FFD600;   /* yellow */
--color-log-error:        #FF5252;   /* red */

/* Surface colors */
--color-surface-panel:    #1A1A2E;   /* dark navy panel bg */
--color-surface-card:     #16213E;   /* slightly lighter card */
--color-surface-terminal: #0D0D0D;   /* near-black terminal */
--color-surface-header:   #0F3460;   /* dark blue header */

/* Comic border */
--color-comic-border:     #E8E8E8;   /* white for terminal comic border */
--color-emergency-bg:     #7B0000;   /* deep red emergency */
--color-emergency-border: #FF1744;   /* bright red emergency border */
```

### 9.2 Typography

```css
--font-family-base:       'Inter', 'Noto Sans KR', sans-serif;
--font-family-mono:       'JetBrains Mono', 'Fira Code', monospace;
--font-family-comic:      'Bangers', 'Impact', sans-serif;  /* for stamps */

--font-size-xs:    11px;   /* metadata, timestamps */
--font-size-sm:    13px;   /* secondary labels */
--font-size-base:  15px;   /* body text */
--font-size-lg:    17px;   /* panel headers */
--font-size-xl:    22px;   /* stat numbers */
--font-size-2xl:   28px;   /* comic stamps */

--font-weight-regular: 400;
--font-weight-medium:  500;
--font-weight-bold:    700;
--font-weight-black:   900;  /* stamps */
```

### 9.3 Spacing & Sizing

```css
--space-1:   4px;
--space-2:   8px;
--space-3:  12px;
--space-4:  16px;
--space-6:  24px;
--space-8:  32px;
--space-12: 48px;

--radius-sm:   4px;
--radius-md:   8px;
--radius-lg:  12px;
--radius-xl:  16px;
--radius-full: 9999px;  /* pills, dots */

--panel-min-width: 280px;
--header-height:    56px;
--tab-bar-height:   56px;  /* mobile */
--log-height-lg:   240px;
--log-height-md:   200px;
--log-height-sm:   160px;
```

### 9.4 Animation Timing

```css
--duration-fast:    150ms;
--duration-base:    200ms;
--duration-slow:    300ms;
--duration-celebration: 500ms;

--easing-standard: cubic-bezier(0.4, 0, 0.2, 1);
--easing-spring:   cubic-bezier(0.175, 0.885, 0.32, 1.275);
--easing-exit:     cubic-bezier(0.4, 0, 1, 1);

/* Skeleton shimmer */
--skeleton-duration: 1.4s;
--skeleton-timing: ease-in-out;
```

---

## 10. Accessibility Summary

### 10.1 WCAG 2.1 AA Compliance Checklist

| Criterion | Implementation | Status |
|-----------|---------------|--------|
| 1.1.1 Non-text content | All icons, avatars, stamps have `aria-label` or `alt` | Required |
| 1.3.1 Info and relationships | Tables use `<th scope>`, forms use `<label>` | Required |
| 1.3.3 Sensory characteristics | Status not conveyed by color alone (icon + text + color) | Required |
| 1.4.1 Use of color | Priority/status have text labels, not just color | Required |
| 1.4.3 Contrast (minimum) | All text ≥4.5:1, large text ≥3:1 on panel backgrounds | Required |
| 1.4.4 Resize text | Layout flows correctly at 200% browser zoom | Required |
| 2.1.1 Keyboard | All interactive elements keyboard accessible | Required |
| 2.1.2 No keyboard trap | Modals trap focus correctly, Escape closes | Required |
| 2.4.3 Focus order | Tab order follows visual reading order (left→right, top→bottom) | Required |
| 2.4.4 Link purpose | All buttons/links have descriptive labels | Required |
| 2.4.7 Focus visible | Focus ring visible on all interactive elements (2px solid outline) | Required |
| 2.5.3 Label in name | Visible labels match accessible names | Required |
| 2.5.5 Target size | All tap targets ≥44x44px on mobile | Required |
| 3.2.2 On input | No unexpected context changes on input | Required |
| 3.3.1 Error identification | Errors identified with text description, not icon alone | Required |
| 4.1.2 Name, role, value | All custom widgets have correct ARIA roles | Required |
| 4.1.3 Status messages | Live regions for ticket updates, log stream, completions | Required |

### 10.2 Key ARIA Live Region Strategy

| Region | `aria-live` | `aria-atomic` | `aria-relevant` | Update trigger |
|--------|-------------|---------------|-----------------|----------------|
| Ticket count badges | `polite` | `true` | - | Count changes |
| BLOCKED count | `assertive` | `true` | - | New blockage |
| Log stream output | `polite` | `false` | `additions` | New log lines |
| Completion celebration | `polite` | `true` | - | Task completes |
| Agent offline alert | `assertive` | `true` | - | Agent goes down |
| WebSocket reconnect | `polite` | `true` | - | Connection state changes |
| Emergency stop status | `assertive` | `true` | - | Emergency triggered |

### 10.3 Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  /* Disable skeleton shimmer animation */
  .skeleton { animation: none; background: #2a2a2a; }

  /* Disable celebration banner pulse */
  .celebration-banner { animation: none; }

  /* Disable status dot pulse */
  .status-dot.online { animation: none; }

  /* Disable comic stamp entrance animation */
  .comic-stamp { animation: none; transform: none; }

  /* Reduce row expand/collapse to instant */
  .ticket-row-detail { transition: none; }
}
```

### 10.4 Screen Reader Announcements for Key Events

| Event | Announcement |
|-------|-------------|
| Ticket status changes from PENDING to RUNNING | "Task RETRO-27 is now running. Agent DEV-BOT-01 assigned." |
| Task becomes BLOCKED | "Alert: Task RETRO-29 is blocked. Reason: waiting for ENV_VARS." |
| Task completes | "Task RETRO-21 completed successfully. Duration: 5 minutes 22 seconds." |
| Agent goes offline | "Alert: OPS-BOT-01 is offline. 1 task interrupted." |
| Emergency stop activated | "Emergency stop activated. All agents stopping. This action is logged." |
| WebSocket reconnected | "Connection restored. Live updates resumed." |
| Filters applied | "Showing 3 tickets matching P0 priority in 개발실." |
| No tickets (empty state) | "No active tickets. All agents standing by." |

---

*End of Wireframe Specification v2.0*
*Document path: `/docs/design/T-aiorg-comic-dashboard-wireframes-v2.md`*
*For design token CSS file, see: `/docs/design/tokens.css`*
*For previous phase wireframes, see: `/docs/design/phase2-wireframes.md`*
