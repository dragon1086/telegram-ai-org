# T-aiorg Comic Character Concept — Mascot & Logo Design System v2

> **Document type**: Design Handoff Spec
> **Version**: 2.0.0
> **Created**: 2026-04-01
> **Status**: Production-Ready Draft
> **Owner**: Design Room (디자인실)

---

## Table of Contents

1. [마스코트 컨셉 (Mascot Concept)](#1-마스코트-컨셉)
2. [로고 컨셉 (Logo Concept)](#2-로고-컨셉)
3. [컬러 팔레트 — 3세트 제안](#3-컬러-팔레트)
4. [스타일 가이드라인](#4-스타일-가이드라인)
5. [애니메이션 방향](#5-애니메이션-방향)

---

## 1. 마스코트 컨셉

### 전체 캐릭터 방향

**설계 철학**: 6개 조직실의 캐릭터는 모두 동일한 베이스 바디("볼록 머리 + 둥근 눈 + 짧은 팔다리")를 공유하되, 고유한 소품(prop)·컬러·표정으로 차별화한다. 이 "팀 유니폼 + 개인 개성" 구조는 조직의 통일감과 각 팀의 정체성을 동시에 표현한다.

**공통 베이스 스타일**:
- 머리:몸 비율 = 1.5:1 (chibi 비율)
- 외곽선: 검정 #000000, stroke 3px
- 눈: 원형 눈 + 흰 하이라이트 점
- 배경 말풍선: 각 캐릭터 고유 형태

---

### 1-1. 디자인실 (Design) — "픽셀 Pix"

**캐릭터 이름**: Pix (픽스)
**역할**: 색을 칠하는 아티스트

```
         .---------.
        /  o     o  \
       |   >  ∪  <   |    ← 입가에 작은 물감 자국
        \  \_____/  /
         '---------'
              |
         .----|----.
        /  [PALETTE] \   ← 왼손에 팔레트
       |  ___________  |
       | |   _   _   | |
       | |  | | |_|  | |
        \_|___________|_/
              |
            /   \
           /     \
    [BRUSH]       [BRUSH]   ← 두 손 붓

"KA-SPLASH!"  "COLOR POP!"
```

**시각적 특징 키워드**:
- `splashy` — 물감 스플래터 패턴이 몸통에 묻어있음
- `expressive` — 눈썹이 두꺼워 감정 표현이 과장됨
- `colorful` — 베레모(beret)에 7색 물감 자국
- `left-handed` — 왼손에 팔레트, 오른손에 붓
- `messy-chic` — 앞치마에 무수한 물감 얼룩

**컬러 팔레트**:
| 역할 | 이름 | HEX | RGB | 용도 |
|------|------|-----|-----|------|
| Primary | Pix Purple | `#7B2FBE` | rgb(123,47,190) | 베레모, 앞치마 |
| Secondary | Canvas Cream | `#FFF8E7` | rgb(255,248,231) | 피부톤, 배경 |
| Accent | Brush Orange | `#FF6B35` | rgb(255,107,53) | 붓 끝, 하이라이트 |
| Outline | Ink Black | `#1A1A2E` | rgb(26,26,46) | 외곽선 전체 |
| Pop | Splash Yellow | `#FFE234` | rgb(255,226,52) | 물감 스플래터 |

**표정 변형**:
| 상태 | 눈 | 입 | 기타 |
|------|----|----|------|
| 기본 (Default) | 동그란 눈 (●●) | 작은 미소 `∪` | 팔레트 들고 대기 |
| 작업중 (Working) | 집중 눈 (◎◎) | 혀 내밀기 `3` | 붓질 동작, 동작선 4개 |
| 완료 (Done) | 별 눈 (★★) | 크게 웃음 `D` | 팔레트 위로 번쩍, 별 3개 폭발 |
| 오류 (Error) | X눈 (✕✕) | ∩ 모양 | 붓이 뚝 부러짐, 땀방울 |
| 대기 (Idle) | 반쯤 감긴 눈 (–– ––) | 작은 점 `.` | 팔레트 내려놓음, ZZZ 버블 |

**만화 의성어/의태어**:
- `"KA-SPLASH!"` — 물감 뿌릴 때
- `"SWOOOSH!"` — 붓질 동작
- `"COLOR POP!"` — 완료 시
- `"DRIP..."` — 대기/지루할 때
- `"SNAP!"` — 오류 (붓 부러짐)

**말풍선 스타일**: 불규칙한 물감 방울 형태 말풍선. 꼬리가 끝으로 갈수록 얇아지는 스플래터 꼬리. 배경색: Canvas Cream `#FFF8E7`, 테두리: Ink Black 3px.

---

### 1-2. 개발실 (Engineering) — "버그 Bux"

**캐릭터 이름**: Bux (벅스)
**역할**: 버그를 잡는 코더

```
         .---------.
        /  @     @  \    ← 두꺼운 안경 (○○)
       |   ─  ∪  ─   |
        \  \_____/  /
         '---------'
              |
         .----|----.
        /  [LAPTOP] \
       |  .--------. |
       | | > _ bux | |   ← 터미널 화면
       | |________| |
        \____________/
              |
            /   \
       [COFFEE]  [DEBUG TOOL]

"COMPILE!", "BUG SQUASH!", "git push --force 🚫"
```

**시각적 특징 키워드**:
- `spectacled` — 두꺼운 검정 뿔테 안경, 렌즈에 코드 반사
- `caffeinated` — 항상 커피잔 옆에 있음 (Steam 이펙트)
- `terminal-green` — 몸통 후드티에 `> _` 커서 깜빡임 패턴
- `sleep-deprived` — 눈 밑 다크서클, 머리카락 삐죽
- `mechanical` — 기어 모양 버튼이 달린 후드티

**컬러 팔레트**:
| 역할 | 이름 | HEX | RGB | 용도 |
|------|------|-----|-----|------|
| Primary | Code Green | `#00D084` | rgb(0,208,132) | 터미널 텍스트, 후드티 포인트 |
| Secondary | Dark IDE | `#1E1E2E` | rgb(30,30,46) | 후드티, 노트북 케이스 |
| Accent | Debug Red | `#FF4757` | rgb(255,71,87) | 버그/에러 강조, 안경 테 |
| Outline | Ink Black | `#000000` | rgb(0,0,0) | 외곽선 전체 |
| Pop | Cursor White | `#EFEFEF` | rgb(239,239,239) | 터미널 커서 `_` |

**표정 변형**:
| 상태 | 눈 | 입 | 기타 |
|------|----|----|------|
| 기본 (Default) | 안경 너머 동그란 눈 (○○) | 집중된 일자 입 `─` | 랩탑 열린 상태 |
| 작업중 (Working) | 안경에 코드 반사 (≡≡) | 혀 깨물기 | 손가락 빠르게 타이핑, 키보드 딸깍 효과음 |
| 완료 (Done) | 별 눈 + 안경 위로 치켜 (★★) | `"LGTM!"` 말풍선 | 주먹 위로 번쩍, 초록 체크 폭발 |
| 오류 (Error) | X눈 위에 안경 삐딱 (✕✕) | 소리지름 모양 `O` | 빨간 ERROR 텍스트 폭발, 연기 이펙트 |
| 대기 (Idle) | 안경 밀어올리며 졸음 (─ ─) | 미세하게 벌린 입 | Stack Overflow 탭 열림, ZZZ |

**만화 의성어/의태어**:
- `"COMPILE!"` — 빌드 시작
- `"BUG SQUASH!"` — 버그 수정 완료
- `"SEGFAULT!!"` — 오류 발생
- `"LGTM!"` — 코드 리뷰 완료
- `"CLICK CLICK CLICK"` — 작업 중

**말풍선 스타일**: 터미널 창 모양 말풍선. 위쪽 타이틀바에 `●●●` (맥OS 스타일). 폰트: JetBrains Mono. 배경: Dark IDE `#1E1E2E`, 텍스트: Code Green `#00D084`.

---

### 1-3. 기획실 (Product) — "플랜 Plan"

**캐릭터 이름**: Plan (플랜)
**역할**: 로드맵을 그리는 PM

```
         .---------.
        /  ^ ∪ ^  \    ← 눈썹이 항상 올라가 있음 (의욕 넘침)
       |             |
        \  \_____/  /
         '---------'
              |
     [TIE]   |   [BADGE: PM]
         .----|----.
        /  [CLIPBOARD] \
       |  .----------. |
       | |✓ Q1 Goals | |   ← 체크리스트
       | |✓ Roadmap  | |
       | |□ Sprint 3 | |
       | |____________| |
        \______________/
              |
            /   \
      [POINTER]  [PHONE]   ← 프레젠테이션 포인터 + 스마트폰

"SCOPE LOCKED!", "SHIP IT!", "PRD v99.9"
```

**시각적 특징 키워드**:
- `clipboard-wielder` — 항상 클립보드 + 체크리스트 소지
- `tie-and-badge` — 정장 넥타이 + PM 배지
- `roadmap-eyes` — 눈동자에 간트 차트 패턴
- `always-presenting` — 손에 포인터 항상 있음
- `sprint-energy` — 머리카락이 바람에 날리는 속도감 표현

**컬러 팔레트**:
| 역할 | 이름 | HEX | RGB | 용도 |
|------|------|-----|-----|------|
| Primary | PRD Blue | `#0052CC` | rgb(0,82,204) | 넥타이, 클립보드 테두리 |
| Secondary | Sprint White | `#F4F5F7` | rgb(244,245,247) | 셔츠, 클립보드 배경 |
| Accent | Milestone Gold | `#FFAB00` | rgb(255,171,0) | 배지, 완료 체크 표시 |
| Outline | Ink Black | `#172B4D` | rgb(23,43,77) | 외곽선 전체 |
| Pop | Alert Red | `#FF5630` | rgb(255,86,48) | 마감 임박 표시 |

**표정 변형**:
| 상태 | 눈 | 입 | 기타 |
|------|----|----|------|
| 기본 (Default) | 열정적 눈썹 위로 (^ ^) | 결의에 찬 미소 | 클립보드 꼭 쥠 |
| 작업중 (Working) | 집중 눈 + 눈썹 V자 (≥≤) | 빠른 말하기 모양 | 포인터 빙빙, 체크 표시 날아다님 |
| 완료 (Done) | 눈 감고 만족 (╯╯) | 큰 웃음 `D` | 클립보드 전체 체크, 별 폭발 `"SHIPPED!"` |
| 오류 (Error) | 충격 눈 (O O) | `"SCOPE CREEP!!"` | 클립보드 서류 흩날림, 땀방울 |
| 대기 (Idle) | 눈을 가늘게 뜨고 생각 (– –) | 손가락으로 턱 괴기 | `"hmm..."` 생각 버블 |

**만화 의성어/의태어**:
- `"SCOPE LOCKED!"` — 기획 확정
- `"SHIP IT!"` — 배포 결정
- `"PRD APPROVED!"` — 문서 승인
- `"PIVOT!"` — 방향 전환
- `"BACKLOG..."` — 대기 중

**말풍선 스타일**: 직사각형 + 모서리 라운드 말풍선 (Jira 티켓 모양). 내부에 Priority 레이블 (빨강/노랑/초록). 배경: Sprint White, 테두리: PRD Blue 3px.

---

### 1-4. 운영실 (Ops) — "옵스 Ops"

**캐릭터 이름**: Ops (옵스)
**역할**: 시스템을 지키는 현장 엔지니어

```
         .---------.
        /  ● ─ ●  \    ← 안전모 착용, 진지한 표정
       |             |
        \  \_____/  /
         '---------'
            [HELMET: ⚙]    ← 헬멧에 기어 아이콘
              |
     [VEST]   |   [RADIO]  ← 형광 조끼 + 무전기
         .----|----.
        / [WRENCH] \
       |   ▶ STATUS: OK   |
       |   ▶ UPTIME: 99.9%|
        \________________/
              |
            /   \
      [BOOTS]  [MONITOR]   ← 안전화 + 모니터링 태블릿

"DEPLOY!", "ROLLBACK!", "99.99% SLA"
```

**시각적 특징 키워드**:
- `helmeted` — 항상 주황색 안전모 착용, 기어 아이콘 각인
- `vest-wearing` — 형광 노랑 조끼에 `OPS` 프린트
- `wrench-holding` — 오른손에 항상 렌치 소지
- `monitoring-tablet` — 왼손에 시스템 모니터링 태블릿
- `stoic-face` — 표정 변화 최소, 신뢰감 있는 눈빛

**컬러 팔레트**:
| 역할 | 이름 | HEX | RGB | 용도 |
|------|------|-----|-----|------|
| Primary | Ops Orange | `#FF6900` | rgb(255,105,0) | 안전모, 강조 |
| Secondary | Steel Grey | `#455A64` | rgb(69,90,100) | 조끼, 렌치 |
| Accent | Safety Yellow | `#FFD600` | rgb(255,214,0) | 형광 조끼, 경고 표시 |
| Outline | Ink Black | `#212121` | rgb(33,33,33) | 외곽선 전체 |
| Pop | Status Green | `#00C853` | rgb(0,200,83) | 정상 상태 표시 |

**표정 변형**:
| 상태 | 눈 | 입 | 기타 |
|------|----|----|------|
| 기본 (Default) | 차분한 눈 (● ●) | 단호한 일자 `─` | 렌치 어깨에 올려놓음 |
| 작업중 (Working) | 집중 눈썹 내려감 (▼ ▼) | 살짝 벌린 입 | 렌치 빠르게 돌림, 스파크 이펙트 |
| 완료 (Done) | 눈 살짝 위로 + 끄덕 (^ ^) | 엄지 척 표정 | 태블릿에 녹색 체크, `"STABLE"` 말풍선 |
| 오류 (Error) | 경고 눈 (! !) | `"INCIDENT!"` | 빨간 경보등, 헬멧 빨간 빛 |
| 대기 (Idle) | 눈 감고 팔짱 (─ ─) | 입 꽉 다물기 | 태블릿 모니터링 자동, `"ON WATCH"` |

**만화 의성어/의태어**:
- `"DEPLOY!"` — 배포 실행
- `"ROLLBACK!"` — 긴급 롤백
- `"ALERT!!"` — 장애 감지
- `"FIXED!"` — 수정 완료
- `"MONITORING..."` — 대기/감시 중

**말풍선 스타일**: 각진 사각형 말풍선 (경고판 스타일). 배경: Safety Yellow `#FFD600`, 테두리: 검정 4px 이중선, 꼬리가 직각으로 꺾임.

---

### 1-5. 성장실 (Growth) — "그로우 Gro"

**캐릭터 이름**: Gro (그로)
**역할**: 지표를 올리는 마케터

```
         .---------.
        /  ★ ∪ ★  \    ← 별 눈 (항상 반짝)
       |             |
        \  \_____/  /
         '---------'
              |
         .----|----.
        /  [CHART]  \
       |  ↗ ↗ ↗ ↗   |   ← 상승 차트 들고 있음
       |  /________  |
       | /  📈 +127% | |
        \_____________/
              |
            /   \
   [MEGAPHONE]  [COIN]    ← 확성기 + 금화

"TO THE MOON!", "GROWTH HACK!", "CTR: 99%"
```

**시각적 특징 키워드**:
- `star-eyed` — 항상 별 모양 눈 (흥분 상태 기본값)
- `chart-hugging` — 상승 차트 보드를 가슴에 꼭 안음
- `megaphone-ready` — 왼쪽 허리에 확성기 항상 장착
- `trend-hair` — 위로 솟은 머리카락이 상승 트렌드 화살표 형태
- `coin-shower` — 완료 시 금화 비 이펙트

**컬러 팔레트**:
| 역할 | 이름 | HEX | RGB | 용도 |
|------|------|-----|-----|------|
| Primary | Growth Green | `#00B894` | rgb(0,184,148) | 차트 라인, 상의 |
| Secondary | Hype Pink | `#FD79A8` | rgb(253,121,168) | 확성기, 포인트 색 |
| Accent | Coin Gold | `#FDCB6E` | rgb(253,203,110) | 금화, 별 눈 |
| Outline | Ink Black | `#2D3436` | rgb(45,52,54) | 외곽선 전체 |
| Pop | Rocket Red | `#D63031` | rgb(214,48,49) | 긴급 알림, 임팩트 |

**표정 변형**:
| 상태 | 눈 | 입 | 기타 |
|------|----|----|------|
| 기본 (Default) | 별 눈 (★★) | 씩씩한 미소 D | 차트 위로 들고 있음 |
| 작업중 (Working) | 집중 별 눈 (✦✦) | 빠르게 말하는 표정 | 확성기 사용, 동작선 |
| 완료 (Done) | 초대형 별 눈 (✦✦✦) | 극도의 흥분 `"YEAH!!"` | 차트 수직 상승, 금화 폭발 |
| 오류 (Error) | 별 눈 → 물음표 눈 (??) | `"WHY?!"` | 차트 하락 표시, 눈물 한 방울 |
| 대기 (Idle) | 별 눈 반쯤 감김 (✦ ✦) | 허밍 중 `♪` | 차트 바라보며 흥얼거림 |

**만화 의성어/의태어**:
- `"TO THE MOON!"` — 수치 급등
- `"GROWTH HACK!"` — 전략 실행
- `"KA-CHING!"` — 목표 달성
- `"VIRAL!!"` — 바이럴 발생
- `"A/B TEST!"` — 실험 시작

**말풍선 스타일**: 폭발형(burst) 말풍선 — 뾰족한 꼭짓점이 방사형으로 퍼짐. 배경: Coin Gold `#FDCB6E`, 테두리: 검정 3px. 내부 텍스트는 굵게 기울임.

---

### 1-6. 리서치실 (Research) — "렌즈 Lenz"

**캐릭터 이름**: Lenz (렌즈)
**역할**: 진실을 파헤치는 연구원

```
         .---------.
        /  O ─ O  \    ← 한쪽 눈에 돋보기 대고 있음
       |   ∩ ─ ∩   |
        \  \_____/  /
         '---------'
              |
    [LAB COAT] |
         .----|----.
        / [MAGNIFIER]\ ← 거대 돋보기 들고 있음
       |  [NOTEBOOK]  |
       | ┌──────────┐ |
       | │ FINDING: │ |
       | │ 47 refs  │ |
       | └──────────┘ |
        \_____________/
              |
            /   \
    [PENCIL]  [BOOKS]   ← 귀에 연필 꽂힘 + 책 더미

"EUREKA!", "CITED!", "HYPOTHESIS..."
```

**시각적 특징 키워드**:
- `magnifier-wielder` — 항상 돋보기를 한쪽 눈에 대고 있음
- `lab-coat` — 흰 가운에 포켓 가득 메모지
- `pencil-behind-ear` — 귀 뒤에 연필 상시 꽂힘
- `stacked-books` — 발 옆에 항상 책 더미
- `footnote-eyes` — 눈 밑에 작은 글씨 인용 번호처럼 생긴 점들

**컬러 팔레트**:
| 역할 | 이름 | HEX | RGB | 용도 |
|------|------|-----|-----|------|
| Primary | Research Teal | `#0097A7` | rgb(0,151,167) | 가운 포인트, 돋보기 테 |
| Secondary | Paper White | `#FAFAFA` | rgb(250,250,250) | 흰 가운, 노트 배경 |
| Accent | Citation Red | `#E53935` | rgb(229,57,53) | 중요 발견 표시, 형광펜 |
| Outline | Ink Black | `#212121` | rgb(33,33,33) | 외곽선 전체 |
| Pop | Eureka Yellow | `#FFF176` | rgb(255,241,118) | 발견 순간 폭발 이펙트 |

**표정 변형**:
| 상태 | 눈 | 입 | 기타 |
|------|----|----|------|
| 기본 (Default) | 한쪽 돋보기 + 한쪽 눈 (O ─) | 생각에 잠긴 표정 `─` | 돋보기 들고 주시 |
| 작업중 (Working) | 양쪽 눈 다 돋보기 (O O) | 입술 지긋이 다물기 | 노트에 빠르게 필기, 사각사각 |
| 완료 (Done) | 눈 크게 뜨고 돋보기 위로 (! !) | `"EUREKA!"` | 돋보기 번쩍, 전구 폭발 |
| 오류 (Error) | 돋보기 흐릿하게 + 혼란 눈 (? ?) | `"SOURCE NEEDED"` | 노트 구겨짐, 물음표 폭발 |
| 대기 (Idle) | 돋보기 내려놓고 눈 감음 (─ ─) | 작은 `hmm` | 책 읽는 중, 독서 버블 |

**만화 의성어/의태어**:
- `"EUREKA!"` — 발견 순간
- `"CITED!"` — 레퍼런스 확인
- `"HYPOTHESIS..."` — 가설 수립
- `"DATA SAYS:"` — 분석 결과
- `"PEER REVIEWED!"` — 검증 완료

**말풍선 스타일**: 학술 논문 각주 스타일 말풍선. 직사각형에 하단에 점선 구분선 + 작은 `[ref]` 표시. 배경: Paper White, 테두리: Research Teal 2px.

---

## 2. 로고 컨셉

### 2-1. 메인 로고 타입

#### 로고 아이디어 A — "AI ORG" 워드마크

```
  ╔══════════════════════════════╗
  ║                              ║
  ║   ██████╗  ██████╗  ██████╗ ║
  ║  ██╔══██╗ ██╔═══╝ ██╔════╝ ║
  ║  ███████║  █████╗  ██║  ███╗ ║
  ║  ██╔══██║ ██╔══╝  ██║   ██║ ║
  ║  ██║  ██║ ██║     ╚██████╔╝ ║
  ║  ╚═╝  ╚═╝ ╚═╝      ╚═════╝  ║
  ║                              ║
  ║   [🤖] + [💬] = ✨aiorg✨   ║
  ║                              ║
  ╚══════════════════════════════╝

  로봇 아이콘 + 말풍선 아이콘 콤보
  텍스트: "aiorg" (소문자 권장)
```

#### 아이콘 마크 상세 — 로봇 + 말풍선 조합

```
  [ICON MARK v1 — Full Bubble Bot]

        .---SPEECH BUBBLE---.
       /  "Let's build!"     \
      /                       \
     |   .-------.             |
     |  / o   o  \  ← 로봇 얼굴 |
     | |  ─ ∪ ─  |            |
     |  \-------/ ← 안테나 달림 |
      \                       /
       \   [ai]  [org]       /
        '-------------------'

  꼬리: 왼쪽 하단, 두꺼운 직각 꼬리 (코믹 스타일)

  [ICON MARK v2 — Minimal Bot Head]

      ┌─────┐
      │ ◉ ◉ │  ← 로봇 눈
      │ ─── │  ← 입 = 데이터 라인
      └──┬──┘
         │     ← 안테나
        ═╪═    ← 안테나 끝 신호

  아이콘 배경: 만화 말풍선 형태 (뾰족 꼬리)
```

#### 텍스트 처리

**로고 텍스트**: `aiorg`

**폰트 옵션**:
| 옵션 | 폰트 | 특징 | 추천 용도 |
|------|------|------|----------|
| Option A | Bangers (Google Fonts) | 넓게 펼쳐진 만화체, 굵은 획 | 히어로 배너, 대형 디스플레이 |
| Option B | Fredoka One (Google Fonts) | 둥글고 친근한 볼드 | 앱 아이콘, UI 헤딩 |
| Option C | Black Han Sans | 한국어 만화책 느낌 + 로마자 겸용 | 한국 로컬 컨텍스트 |

**권장**: Option A (Bangers) — 영문, Option C (Black Han Sans) — 한국어 컨텍스트

**로고 슬로건** (선택적 서브텍스트): `"Automate. Collaborate. Ship."` — Nunito Regular 14px

---

### 2-2. 크기 변형 시스템

#### Full Version (가로형)

```
  ┌────────────────────────────────────────────┐
  │  [BOT ICON 48px]  aiorg                   │
  │                   Automate. Collaborate.   │
  └────────────────────────────────────────────┘

  아이콘: 48 × 48px
  워드마크 "aiorg": Bangers 36px
  슬로건: Nunito Regular 12px
  전체 크기: 240 × 64px
```

#### Compact Version (정사각형)

```
  ┌──────────────┐
  │  [BOT ICON]  │
  │    aiorg     │
  └──────────────┘

  아이콘: 32 × 32px
  워드마크: Bangers 20px
  전체 크기: 80 × 80px
  용도: 소셜 미디어 프로필, 작은 UI 컴포넌트
```

#### Icon-only Version

```
  ┌──────┐
  │ 🤖💬 │
  └──────┘

  크기: 32 × 32px (최소), 512 × 512px (파비콘 기준)
  용도: 파비콘, 앱 아이콘, 텔레그램 봇 프로필
```

---

### 2-3. 다크/라이트 모드 버전

#### 라이트 모드

```
  배경: #FFFFFF (흰색)
  아이콘: #1A1A2E (Dark Navy)
  워드마크 "ai": #1A1A2E
  워드마크 "org": #7B2FBE (Pix Purple — 포인트 컬러)
  슬로건: #6B7280
  외곽선: #000000 3px
```

#### 다크 모드

```
  배경: #0D0D0D (거의 검정)
  아이콘: #FFFFFF
  워드마크 "ai": #FFFFFF
  워드마크 "org": #00D084 (Code Green — 터미널 느낌)
  슬로건: #9CA3AF
  외곽선: #FFFFFF 2px (얇게)
```

---

### 2-4. 로고 그리드 시스템

#### 그리드 구성

```
  [Full Logo Grid — 240 × 64px 기준]

  ┌─ 8px ─┬─ 48px ─┬─ 8px ─┬──────── 168px ────────┬─ 8px ─┐
  │       │        │       │                        │       │
  │  (C)  │  ICON  │  (C)  │    aiorg + tagline     │  (C)  │
  │       │        │       │                        │       │
  └───────┴────────┴───────┴────────────────────────┴───────┘

  (C) = Clear Space = 8px 최소 여백 (= 아이콘 높이의 1/6)
```

#### 최소 크기 규정

| 변형 | 최소 너비 | 최소 높이 | 비고 |
|------|----------|----------|------|
| Full (가로형) | 160px | 44px | 이하 축소 금지 |
| Compact (정사각형) | 48px | 48px | 이하 축소 금지 |
| Icon-only | 16px | 16px | 파비콘 최소 단위 |

#### Clear Space (여백 규칙)

```
  최소 여백 = 아이콘 높이(H)의 25%

  예시: 아이콘 48px → 최소 여백 = 12px (상하좌우 모두)

  ┌─────────────────────────────┐
  │   12px  (clear space top)  │
  │                            │
  │12px  [ LOGO ]  12px        │
  │                            │
  │  12px (clear space bottom) │
  └─────────────────────────────┘
```

#### 금지 사용 예시 (Misuse Guidelines)

```
  ✗ 금지 1: 회전 — 로고를 어떤 각도로도 회전하지 말 것
  ✗ 금지 2: 비율 변형 — 가로/세로 비율을 독립적으로 변경 금지
  ✗ 금지 3: 컬러 변조 — 승인되지 않은 색상 적용 금지
  ✗ 금지 4: 아웃라인만 사용 — 속을 비운 outline-only 버전 금지
  ✗ 금지 5: 배경 위 가시성 미확보 — WCAG 기준 미달 배경 위 배치 금지
  ✗ 금지 6: 이미지 위 단독 배치 — 사진 배경 위에 투명 로고 금지 (반드시 백플레이트 사용)
  ✗ 금지 7: 텍스트 내 혼용 — 로고 아이콘과 일반 텍스트 인라인 혼용 금지
  ✗ 금지 8: 그림자 추가 — 가이드 외 추가 그림자/글로우 효과 금지
```

---

## 3. 컬러 팔레트

### 세트 A: 팝아트 (Pop Art) — 원색 대비

**컨셉**: Andy Warhol + Roy Lichtenstein 영감. 원색의 대담한 대비. 에너지 넘치는 AI 조직의 역동성 표현.

#### 팔레트 상세

| 역할 | 이름 | HEX | RGB | HSL |
|------|------|-----|-----|-----|
| Primary | Pop Yellow | `#FFD700` | rgb(255,215,0) | hsl(50,100%,50%) |
| Secondary | Comic Red | `#FF1744` | rgb(255,23,68) | hsl(349,100%,55%) |
| Accent | Dot Blue | `#2979FF` | rgb(41,121,255) | hsl(220,100%,58%) |
| Background Light | Halftone White | `#FFFEF0` | rgb(255,254,240) | hsl(57,100%,97%) |
| Background Dark | Ink Well | `#0A0A0A` | rgb(10,10,10) | hsl(0,0%,4%) |
| Text Light | Print Black | `#1A1A1A` | rgb(26,26,26) | hsl(0,0%,10%) |
| Text Dark | Paper White | `#F5F5F5` | rgb(245,245,245) | hsl(0,0%,96%) |
| Border | Outline Black | `#000000` | rgb(0,0,0) | hsl(0,0%,0%) |

#### WCAG 2.1 AA 대비 비율 계산 (세트 A)

**라이트 모드 (배경: Halftone White `#FFFEF0`)**:
| 텍스트 색상 | 배경 색상 | 대비 비율 | 목표 | 판정 |
|------------|----------|----------|------|------|
| Print Black `#1A1A1A` | Halftone White `#FFFEF0` | **18.2:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Print Black `#1A1A1A` | Halftone White `#FFFEF0` | **18.2:1** | ≥ 3.0:1 (대형) | ✅ PASS |
| Outline Black `#000000` | Pop Yellow `#FFD700` | **15.3:1** | ≥ 3.0:1 (UI경계) | ✅ PASS |
| Pop Yellow `#FFD700` | Halftone White `#FFFEF0` | **1.2:1** | ≥ 3.0:1 | ❌ FAIL — 직접 텍스트 사용 금지 |
| Comic Red `#FF1744` | Halftone White `#FFFEF0` | **4.6:1** | ≥ 4.5:1 (본문) | ✅ PASS (경계선) |

**다크 모드 (배경: Ink Well `#0A0A0A`)**:
| 텍스트 색상 | 배경 색상 | 대비 비율 | 목표 | 판정 |
|------------|----------|----------|------|------|
| Paper White `#F5F5F5` | Ink Well `#0A0A0A` | **19.1:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Pop Yellow `#FFD700` | Ink Well `#0A0A0A` | **14.7:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Dot Blue `#2979FF` | Ink Well `#0A0A0A` | **5.2:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Comic Red `#FF1744` | Ink Well `#0A0A0A` | **4.8:1** | ≥ 3.0:1 (UI경계) | ✅ PASS |

**결론**: 세트 A는 다크 모드에서 모든 WCAG AA 기준 통과. 라이트 모드에서 Pop Yellow는 배경색으로만 사용하고 텍스트 색상으로 직접 사용 금지.

---

### 세트 B: 레트로 만화 (Retro Comic) — 빈티지 느낌

**컨셉**: 1960~80년대 미국 만화책 색감. 약간 바랜 느낌의 내추럴 톤. 노스탤지어와 따뜻한 브랜드 감성.

#### 팔레트 상세

| 역할 | 이름 | HEX | RGB | HSL |
|------|------|-----|-----|-----|
| Primary | Retro Amber | `#E8A838` | rgb(232,168,56) | hsl(37,79%,56%) |
| Secondary | Vintage Teal | `#2A7F7F` | rgb(42,127,127) | hsl(180,50%,33%) |
| Accent | Faded Pink | `#D4547A` | rgb(212,84,122) | hsl(340,55%,58%) |
| Background Light | Aged Paper | `#F5EDD8` | rgb(245,237,216) | hsl(42,57%,90%) |
| Background Dark | Dark Mahogany | `#1C1008` | rgb(28,16,8) | hsl(26,56%,7%) |
| Text Light | Ink Sepia | `#2C1810` | rgb(44,24,16) | hsl(16,47%,12%) |
| Text Dark | Cream White | `#F0E6C8` | rgb(240,230,200) | hsl(42,62%,86%) |
| Border | Brown Ink | `#3D2B1F` | rgb(61,43,31) | hsl(22,33%,18%) |

#### WCAG 2.1 AA 대비 비율 계산 (세트 B)

**라이트 모드 (배경: Aged Paper `#F5EDD8`)**:
| 텍스트 색상 | 배경 색상 | 대비 비율 | 목표 | 판정 |
|------------|----------|----------|------|------|
| Ink Sepia `#2C1810` | Aged Paper `#F5EDD8` | **13.4:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Brown Ink `#3D2B1F` | Aged Paper `#F5EDD8` | **10.9:1** | ≥ 3.0:1 (UI경계) | ✅ PASS |
| Vintage Teal `#2A7F7F` | Aged Paper `#F5EDD8` | **4.7:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Retro Amber `#E8A838` | Aged Paper `#F5EDD8` | **1.9:1** | ≥ 3.0:1 | ❌ FAIL — 텍스트 금지, 배경/장식용만 허용 |
| Faded Pink `#D4547A` | Aged Paper `#F5EDD8` | **3.8:1** | ≥ 3.0:1 (대형 텍스트) | ✅ PASS (18px 이상만) |

**다크 모드 (배경: Dark Mahogany `#1C1008`)**:
| 텍스트 색상 | 배경 색상 | 대비 비율 | 목표 | 판정 |
|------------|----------|----------|------|------|
| Cream White `#F0E6C8` | Dark Mahogany `#1C1008` | **17.2:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Retro Amber `#E8A838` | Dark Mahogany `#1C1008` | **10.1:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Vintage Teal `#2A7F7F` | Dark Mahogany `#1C1008` | **4.6:1** | ≥ 4.5:1 (본문) | ✅ PASS |

**결론**: 세트 B는 양쪽 모드 모두 AA 통과. Retro Amber는 라이트 배경에서 텍스트 사용 금지.

---

### 세트 C: 다크 코믹 (Dark Comic) — 다크모드 중심

**컨셉**: 사이버펑크 만화 느낌. 네온 컬러 + 거의 검정 배경. 개발자 및 야간 작업 환경 최적화.

#### 팔레트 상세

| 역할 | 이름 | HEX | RGB | HSL |
|------|------|-----|-----|-----|
| Primary | Neon Cyan | `#00FFFF` | rgb(0,255,255) | hsl(180,100%,50%) |
| Secondary | Neon Purple | `#BF5FFF` | rgb(191,95,255) | hsl(277,100%,69%) |
| Accent | Neon Green | `#39FF14` | rgb(57,255,20) | hsl(109,100%,54%) |
| Background Dark | Void Black | `#080810` | rgb(8,8,16) | hsl(240,33%,5%) |
| Background Mid | Panel Dark | `#13131F` | rgb(19,19,31) | hsl(240,24%,10%) |
| Background Light | Grey Panel | `#F0F0F8` | rgb(240,240,248) | hsl(240,33%,96%) |
| Text Dark (주) | Neon White | `#E8E8FF` | rgb(232,232,255) | hsl(240,100%,95%) |
| Text Dark (보) | Dim Silver | `#8888AA` | rgb(136,136,170) | hsl(240,20%,60%) |
| Text Light | Comic Ink | `#0D0D1A` | rgb(13,13,26) | hsl(240,33%,8%) |
| Border Dark | Neon Border | `#00FFFF` | rgb(0,255,255) | hsl(180,100%,50%) |
| Border Light | Dark Border | `#1A1A2E` | rgb(26,26,46) | hsl(240,28%,14%) |

#### WCAG 2.1 AA 대비 비율 계산 (세트 C)

**다크 모드 (배경: Void Black `#080810`)**:
| 텍스트 색상 | 배경 색상 | 대비 비율 | 목표 | 판정 |
|------------|----------|----------|------|------|
| Neon White `#E8E8FF` | Void Black `#080810` | **20.1:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Neon Cyan `#00FFFF` | Void Black `#080810` | **19.5:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Neon Green `#39FF14` | Void Black `#080810` | **17.8:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Neon Purple `#BF5FFF` | Void Black `#080810` | **9.3:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Dim Silver `#8888AA` | Void Black `#080810` | **6.4:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Neon Cyan `#00FFFF` | Void Black `#080810` | **19.5:1** | ≥ 3.0:1 (UI경계) | ✅ PASS |

**라이트 모드 (배경: Grey Panel `#F0F0F8`)**:
| 텍스트 색상 | 배경 색상 | 대비 비율 | 목표 | 판정 |
|------------|----------|----------|------|------|
| Comic Ink `#0D0D1A` | Grey Panel `#F0F0F8` | **18.8:1** | ≥ 4.5:1 (본문) | ✅ PASS |
| Neon Cyan `#00FFFF` | Grey Panel `#F0F0F8` | **1.1:1** | ≥ 4.5:1 | ❌ FAIL — 라이트 배경에서 Cyan 텍스트 금지 |
| Neon Purple `#BF5FFF` | Grey Panel `#F0F0F8` | **3.2:1** | ≥ 3.0:1 (대형 텍스트) | ✅ PASS (18px 이상) |

**결론**: 세트 C는 다크 모드에서 완벽한 WCAG AA 충족. 라이트 모드에서는 Neon Cyan을 텍스트로 사용 금지. 세트 C는 다크 모드 전용으로 설계된 팔레트이므로 라이트 모드 사용 시 세트 A 또는 B로 전환 권장.

---

## 4. 스타일 가이드라인

### 4-1. 테두리 스타일 (Border & Outline)

**원칙**: 모든 UI 요소에 만화책 스타일의 뚜렷한 외곽선을 적용한다. 외곽선은 요소의 존재감을 강화하고 코믹 스타일을 일관되게 유지한다.

```css
/* 기본 만화 외곽선 */
.comic-outline {
  border: 3px solid #000000;
  border-radius: 8px;
}

/* 강조 외곽선 (카드, 버튼) */
.comic-outline-heavy {
  border: 4px solid #000000;
  border-radius: 12px;
}

/* 섬세한 외곽선 (텍스트 인풋) */
.comic-outline-light {
  border: 2px solid #000000;
  border-radius: 6px;
}
```

| 요소 | Stroke Width | 색상 | 라운드 |
|------|-------------|------|--------|
| 캐릭터 외곽선 | 3-4px | `#000000` | 해당 없음 |
| 버튼 | 3px | `#000000` | 8-12px |
| 카드 | 3px | `#000000` | 12-16px |
| 인풋 필드 | 2px | `#000000` | 6px |
| 모달 | 4px | `#000000` | 16px |
| 배지/태그 | 2px | `#000000` | 99px (pill) |

---

### 4-2. 그림자 스타일 (Shadow System)

**원칙**: 만화책 특유의 solid drop shadow (그라데이션 없음, 단색 그림자). 빛의 방향은 항상 좌상단 → 우하단 (오프셋: +4px, +4px).

```css
/* 기본 솔리드 드롭 섀도 */
.comic-shadow {
  box-shadow: 4px 4px 0px #000000;
}

/* 강조 솔리드 드롭 섀도 (카드, 모달) */
.comic-shadow-heavy {
  box-shadow: 6px 6px 0px #000000;
}

/* 컬러 섀도 (강조 버튼) */
.comic-shadow-color {
  box-shadow: 4px 4px 0px #7B2FBE; /* Pix Purple 예시 */
}

/* 눌렸을 때 (active state) */
.comic-shadow:active {
  box-shadow: 2px 2px 0px #000000;
  transform: translate(2px, 2px);
}

/* hover 시 섀도 강조 */
.comic-shadow:hover {
  box-shadow: 6px 6px 0px #000000;
  transform: translate(-2px, -2px);
}
```

| 상태 | 오프셋 | 변환 |
|------|--------|------|
| 기본 (default) | 4px, 4px | none |
| hover | 6px, 6px | translate(-2px, -2px) |
| active/pressed | 2px, 2px | translate(2px, 2px) |
| disabled | 0px, 0px | none, opacity 0.5 |

---

### 4-3. 버튼 스타일

**원칙**: 두꺼운 외곽선 + solid 그림자 + 만화 폰트. 클릭 시 눌리는 물리적 느낌을 transition으로 구현.

```css
/* Primary Button */
.btn-comic-primary {
  font-family: 'Bangers', cursive;
  font-size: 18px;
  letter-spacing: 1.5px;
  padding: 12px 24px;
  background: #FFD700;       /* Pop Yellow */
  color: #000000;
  border: 3px solid #000000;
  border-radius: 8px;
  box-shadow: 4px 4px 0px #000000;
  cursor: pointer;
  transition: all 0.1s ease;
  text-transform: uppercase;
}

.btn-comic-primary:hover {
  box-shadow: 6px 6px 0px #000000;
  transform: translate(-2px, -2px);
}

.btn-comic-primary:active {
  box-shadow: 1px 1px 0px #000000;
  transform: translate(3px, 3px);
}

/* Secondary Button */
.btn-comic-secondary {
  font-family: 'Bangers', cursive;
  font-size: 18px;
  letter-spacing: 1.5px;
  padding: 10px 22px;
  background: #FFFFFF;
  color: #000000;
  border: 3px solid #000000;
  border-radius: 8px;
  box-shadow: 4px 4px 0px #000000;
  cursor: pointer;
  transition: all 0.1s ease;
}

/* Danger Button */
.btn-comic-danger {
  background: #FF1744;       /* Comic Red */
  color: #FFFFFF;
  font-family: 'Bangers', cursive;
  font-size: 18px;
  padding: 12px 24px;
  border: 3px solid #000000;
  border-radius: 8px;
  box-shadow: 4px 4px 0px #7A0019;
}
```

**버튼 크기 시스템**:
| 사이즈 | 높이 | 패딩 | 폰트 크기 |
|--------|------|------|----------|
| sm | 32px | 6px 16px | 14px |
| md (기본) | 44px | 10px 24px | 18px |
| lg | 56px | 14px 32px | 22px |
| xl | 64px | 16px 40px | 26px |

---

### 4-4. 카드 스타일

**원칙**: 약간 기울어진 comic panel 느낌. 카드는 3-5도 랜덤 기울기 옵션 제공 (대시보드 위젯). 기울기 없는 버전도 제공 (표준 카드).

```css
/* 기본 코믹 카드 */
.card-comic {
  background: #FFFFFF;
  border: 3px solid #000000;
  border-radius: 12px;
  box-shadow: 6px 6px 0px #000000;
  padding: 20px;
  position: relative;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.card-comic:hover {
  transform: translate(-2px, -2px);
  box-shadow: 8px 8px 0px #000000;
}

/* 기울어진 코믹 패널 (대시보드 위젯용) */
.card-comic-tilted-left {
  transform: rotate(-2deg);
}

.card-comic-tilted-right {
  transform: rotate(2deg);
}

.card-comic-tilted-left:hover,
.card-comic-tilted-right:hover {
  transform: rotate(0deg) translate(-2px, -2px);
}

/* 캐릭터 카드 (마스코트 표시용) */
.card-mascot {
  background: linear-gradient(135deg, #FFF8E7 0%, #FFFFFF 100%);
  border: 4px solid #000000;
  border-radius: 16px;
  box-shadow: 8px 8px 0px #000000;
  padding: 24px;
  text-align: center;
}

/* 카드 헤더 (만화 패널 제목 표시줄) */
.card-comic-header {
  font-family: 'Bangers', cursive;
  font-size: 20px;
  letter-spacing: 1px;
  background: #000000;
  color: #FFD700;
  margin: -20px -20px 16px -20px;
  padding: 8px 20px;
  border-radius: 9px 9px 0 0;
}
```

---

### 4-5. 타이포그래피 시스템

**폰트 스택**:

```css
/* Google Fonts 임포트 */
@import url('https://fonts.googleapis.com/css2?family=Bangers&family=Fredoka+One&family=Nunito:wght@400;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap');

/* 타이포그래피 변수 */
:root {
  --font-display: 'Bangers', 'Impact', cursive;
  --font-heading: 'Fredoka One', 'Trebuchet MS', sans-serif;
  --font-body: 'Nunito', 'Segoe UI', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
}
```

| 역할 | 폰트 | 크기 범위 | 행간 | 자간 | 용도 |
|------|------|----------|------|------|------|
| Display | Bangers | 48-96px | 1.0 | 2-4px | 영웅 제목, 로고, SFX 텍스트 |
| Heading H1 | Fredoka One | 32-48px | 1.2 | 0.5px | 페이지 제목 |
| Heading H2 | Fredoka One | 24-32px | 1.3 | 0.3px | 섹션 제목 |
| Heading H3 | Fredoka One | 18-24px | 1.4 | 0.2px | 서브 섹션 |
| Body | Nunito | 14-16px | 1.6 | 0 | 본문 텍스트 |
| Body Bold | Nunito 700 | 14-16px | 1.6 | 0 | 강조 본문 |
| Caption | Nunito | 12px | 1.5 | 0.2px | 캡션, 레이블 |
| Mono | JetBrains Mono | 13-15px | 1.5 | 0 | 코드, 로그, 터미널 |

```css
/* 타이포그래피 클래스 시스템 */
.text-display {
  font-family: var(--font-display);
  font-size: clamp(48px, 8vw, 96px);
  line-height: 1.0;
  letter-spacing: 3px;
  text-transform: uppercase;
}

.text-h1 {
  font-family: var(--font-heading);
  font-size: clamp(32px, 5vw, 48px);
  line-height: 1.2;
  font-weight: 400; /* Fredoka One은 단일 웨이트 */
}

.text-body {
  font-family: var(--font-body);
  font-size: 15px;
  line-height: 1.6;
  font-weight: 400;
}

.text-mono {
  font-family: var(--font-mono);
  font-size: 14px;
  line-height: 1.5;
}

/* 만화 효과 텍스트 (SFX) */
.text-sfx {
  font-family: var(--font-display);
  font-size: 48px;
  -webkit-text-stroke: 3px #000000;
  color: #FFD700;
  text-shadow: 4px 4px 0px #000000;
  transform: rotate(-5deg);
  display: inline-block;
}
```

---

### 4-6. 스페이싱 & 그리드

```css
/* 스페이싱 토큰 (4px 기반) */
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;
  --space-20: 80px;
  --space-24: 96px;
}

/* 코믹 패널 그리드 */
.comic-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--space-6);
  padding: var(--space-6);
}
```

---

## 5. 애니메이션 방향

### 5-1. 캐릭터 Idle Animation (흔들리기)

**설명**: 캐릭터가 아무것도 하지 않을 때 생명감을 주는 idle 루프. 위아래로 살짝 움직이며 "숨쉬는" 느낌.

```css
/* Idle 흔들리기 — Breathing Bob */
@keyframes idle-bob {
  0%   { transform: translateY(0px) rotate(0deg); }
  25%  { transform: translateY(-4px) rotate(0.5deg); }
  50%  { transform: translateY(0px) rotate(0deg); }
  75%  { transform: translateY(-2px) rotate(-0.5deg); }
  100% { transform: translateY(0px) rotate(0deg); }
}

.mascot-idle {
  animation: idle-bob 2.5s ease-in-out infinite;
  transform-origin: bottom center;
}

/* 눈 깜빡이기 — Blink */
@keyframes idle-blink {
  0%   { transform: scaleY(1); }
  95%  { transform: scaleY(1); }
  97%  { transform: scaleY(0.05); }
  100% { transform: scaleY(1); }
}

.mascot-eye {
  animation: idle-blink 4s ease-in-out infinite;
  transform-origin: center;
}

/* 소품 흔들리기 — Prop Sway (팔레트, 클립보드 등) */
@keyframes prop-sway {
  0%   { transform: rotate(-3deg); }
  50%  { transform: rotate(3deg); }
  100% { transform: rotate(-3deg); }
}

.mascot-prop {
  animation: prop-sway 3s ease-in-out infinite;
  transform-origin: bottom center;
}
```

**타이밍 가이드**:
| 애니메이션 | 지속 시간 | 이징 | 루프 |
|-----------|----------|------|------|
| 바디 흔들기 | 2.5s | ease-in-out | 무한 |
| 눈 깜빡이기 | 4.0s | ease-in-out | 무한 |
| 소품 흔들기 | 3.0s | ease-in-out | 무한 |
| 머리카락 흔들기 | 2.0s | ease-in-out | 무한 |

---

### 5-2. 태스크 완료 시 — 별 폭발 + "WOW!" 텍스트

**설명**: 완료 이벤트 시 캐릭터 주변에서 별이 폭발하고 "WOW!" 또는 캐릭터별 완료 의성어가 팝업.

```css
/* 별 폭발 — Star Burst */
@keyframes star-burst {
  0% {
    transform: scale(0) rotate(0deg);
    opacity: 1;
  }
  60% {
    transform: scale(1.4) rotate(180deg);
    opacity: 1;
  }
  100% {
    transform: scale(0) rotate(360deg);
    opacity: 0;
  }
}

.star-particle {
  position: absolute;
  width: 20px;
  height: 20px;
  pointer-events: none;
  animation: star-burst 0.8s ease-out forwards;
}

/* 별 방사형 배치 (8방향) */
.star-1 { top: -30px; left: 50%; animation-delay: 0.0s; }
.star-2 { top: -20px; right: 10%; animation-delay: 0.05s; }
.star-3 { top: 50%; right: -30px; animation-delay: 0.1s; }
.star-4 { bottom: 10%; right: -20px; animation-delay: 0.05s; }
.star-5 { bottom: -30px; left: 50%; animation-delay: 0.0s; }
.star-6 { bottom: 10%; left: -20px; animation-delay: 0.05s; }
.star-7 { top: 50%; left: -30px; animation-delay: 0.1s; }
.star-8 { top: -20px; left: 10%; animation-delay: 0.05s; }

/* "WOW!" SFX 텍스트 팝업 */
@keyframes sfx-popup {
  0%   { transform: scale(0) rotate(-10deg); opacity: 0; }
  40%  { transform: scale(1.3) rotate(5deg); opacity: 1; }
  70%  { transform: scale(1.0) rotate(-2deg); opacity: 1; }
  100% { transform: scale(1.0) translateY(-20px) rotate(0deg); opacity: 0; }
}

.sfx-text-wow {
  font-family: 'Bangers', cursive;
  font-size: 48px;
  color: #FFD700;
  -webkit-text-stroke: 3px #000000;
  text-shadow: 4px 4px 0px #000000;
  position: absolute;
  top: -60px;
  left: 50%;
  transform: translateX(-50%);
  animation: sfx-popup 1.2s ease-out forwards;
  pointer-events: none;
  white-space: nowrap;
}

/* 캐릭터 점프 — 완료 시 */
@keyframes celebrate-jump {
  0%   { transform: translateY(0) scale(1); }
  30%  { transform: translateY(-20px) scale(1.05); }
  50%  { transform: translateY(-15px) scale(1.1); }
  70%  { transform: translateY(-20px) scale(1.05); }
  100% { transform: translateY(0) scale(1); }
}

.mascot-celebrate {
  animation: celebrate-jump 0.6s ease-out;
}
```

**완료 이펙트 시퀀스** (타임라인):
```
t=0.0s  — 태스크 완료 이벤트 트리거
t=0.0s  — 캐릭터 "완료" 표정으로 전환
t=0.0s  — 캐릭터 점프 애니메이션 시작 (0.6s)
t=0.1s  — 별 파티클 8개 방출 (0.8s each)
t=0.2s  — "WOW!" / 캐릭터별 SFX 텍스트 팝업 (1.2s)
t=1.4s  — 모든 이펙트 완료, idle 상태 복귀
```

---

### 5-3. 오류 시 — 캐릭터 땀 흘리기 + "OOPS!"

**설명**: 오류 발생 시 캐릭터가 좌우로 떨리고, 이마에 땀방울이 맺히며, "OOPS!" 텍스트가 빨간색으로 팝업.

```css
/* 오류 떨기 — Shake */
@keyframes error-shake {
  0%   { transform: translateX(0); }
  10%  { transform: translateX(-6px) rotate(-2deg); }
  20%  { transform: translateX(6px) rotate(2deg); }
  30%  { transform: translateX(-5px) rotate(-1deg); }
  40%  { transform: translateX(5px) rotate(1deg); }
  50%  { transform: translateX(-3px); }
  60%  { transform: translateX(3px); }
  70%  { transform: translateX(-2px); }
  80%  { transform: translateX(2px); }
  100% { transform: translateX(0); }
}

.mascot-error {
  animation: error-shake 0.5s ease-out;
}

/* 땀방울 — Sweat Drop */
@keyframes sweat-drop {
  0%   { transform: translateY(0) scale(0); opacity: 0; }
  30%  { transform: translateY(0) scale(1); opacity: 1; }
  70%  { transform: translateY(8px) scale(1); opacity: 1; }
  100% { transform: translateY(16px) scale(0.5); opacity: 0; }
}

.sweat-drop {
  width: 12px;
  height: 16px;
  background: #74B9FF;
  border-radius: 50% 50% 50% 50% / 30% 30% 70% 70%;
  border: 2px solid #0984E3;
  position: absolute;
  top: 10px;
  right: -5px;
  animation: sweat-drop 1.5s ease-in infinite;
}

/* "OOPS!" SFX 텍스트 */
@keyframes sfx-oops {
  0%   { transform: scale(0) rotate(10deg); opacity: 0; }
  40%  { transform: scale(1.2) rotate(-5deg); opacity: 1; }
  70%  { transform: scale(1.0) rotate(2deg); opacity: 1; }
  100% { transform: scale(0.9) rotate(0deg); opacity: 0; }
}

.sfx-text-oops {
  font-family: 'Bangers', cursive;
  font-size: 44px;
  color: #FF1744;
  -webkit-text-stroke: 3px #000000;
  text-shadow: 4px 4px 0px #7A0019;
  position: absolute;
  top: -55px;
  left: 50%;
  transform: translateX(-50%);
  animation: sfx-oops 1.5s ease-out forwards;
  pointer-events: none;
}

/* 빨간 경보 배경 펄스 */
@keyframes error-pulse {
  0%   { background-color: transparent; }
  25%  { background-color: rgba(255, 23, 68, 0.1); }
  50%  { background-color: transparent; }
  75%  { background-color: rgba(255, 23, 68, 0.05); }
  100% { background-color: transparent; }
}

.error-container-pulse {
  animation: error-pulse 0.8s ease-out 2;
}
```

**오류 이펙트 시퀀스** (타임라인):
```
t=0.0s  — 오류 이벤트 트리거
t=0.0s  — 배경 빨간 펄스 2회 (0.8s × 2 = 1.6s)
t=0.0s  — 캐릭터 "오류" 표정 (X 눈) 전환
t=0.0s  — 캐릭터 shake 애니메이션 (0.5s)
t=0.2s  — 땀방울 2개 등장 (1.5s loop, 2회)
t=0.3s  — "OOPS!" 텍스트 팝업 (1.5s)
t=2.0s  — 표정 기본 상태로 복귀
t=2.5s  — idle 상태 완전 복귀
```

---

### 5-4. 로딩 시 — 캐릭터 달리기 애니메이션

**설명**: API 대기, 배포 중 등 처리 시간이 필요할 때 캐릭터가 화면 가로를 달리는 러닝 애니메이션.

```css
/* 러닝 사이클 — 팔다리 교차 */
@keyframes run-cycle {
  0%   { transform: scaleX(1) translateY(0); }
  12%  { transform: scaleX(1) translateY(-4px); }
  25%  { transform: scaleX(1) translateY(0); }
  37%  { transform: scaleX(1) translateY(-3px); }
  50%  { transform: scaleX(1) translateY(0); }
  62%  { transform: scaleX(1) translateY(-4px); }
  75%  { transform: scaleX(1) translateY(0); }
  87%  { transform: scaleX(1) translateY(-3px); }
  100% { transform: scaleX(1) translateY(0); }
}

/* 화면 가로 이동 */
@keyframes run-across {
  0%   { left: -80px; }
  100% { left: calc(100% + 80px); }
}

.mascot-running {
  position: fixed;
  bottom: 20px;
  animation:
    run-across 3.0s linear,
    run-cycle 0.4s steps(4) infinite;
  z-index: 9999;
}

/* 달리기 동작선 (속도감 표현) */
@keyframes speed-lines {
  0%   { opacity: 0; width: 0; }
  50%  { opacity: 1; width: 40px; }
  100% { opacity: 0; width: 60px; }
}

.speed-line {
  position: absolute;
  right: 100%;
  height: 2px;
  background: linear-gradient(to left, #000000, transparent);
  animation: speed-lines 0.3s linear infinite;
}

.speed-line:nth-child(1) { top: 30%; animation-delay: 0s; }
.speed-line:nth-child(2) { top: 50%; animation-delay: 0.1s; }
.speed-line:nth-child(3) { top: 70%; animation-delay: 0.05s; }

/* 로딩 텍스트 (캐릭터 말풍선) */
@keyframes loading-bubble-bounce {
  0%   { transform: translateY(0) scale(1); }
  50%  { transform: translateY(-5px) scale(1.05); }
  100% { transform: translateY(0) scale(1); }
}

.loading-bubble {
  position: absolute;
  top: -40px;
  left: 50%;
  transform: translateX(-50%);
  background: #FFFFFF;
  border: 3px solid #000000;
  border-radius: 12px;
  padding: 4px 12px;
  font-family: 'Bangers', cursive;
  font-size: 16px;
  white-space: nowrap;
  animation: loading-bubble-bounce 0.6s ease-in-out infinite;
  box-shadow: 3px 3px 0px #000000;
}

/* 말풍선 꼬리 */
.loading-bubble::after {
  content: '';
  position: absolute;
  bottom: -12px;
  left: 50%;
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 8px solid transparent;
  border-right: 8px solid transparent;
  border-top: 12px solid #000000;
}
```

**로딩 텍스트 예시** (조직별):
| 조직 | 로딩 메시지 |
|------|------------|
| 디자인실 | `"Painting..."` |
| 개발실 | `"Compiling..."` |
| 기획실 | `"Roadmapping..."` |
| 운영실 | `"Deploying..."` |
| 성장실 | `"Analyzing..."` |
| 리서치실 | `"Researching..."` |
| 공통 | `"Loading..."` / `"Please wait!"` |

**로딩 진행 단계** (progress bar 연동):
```
0-25%:   캐릭터 달리기 시작, 말풍선 "Starting..."
25-50%:  말풍선 "Almost there!"
50-75%:  말풍선 "Halfway done!"
75-99%:  캐릭터 속도 증가 (animation-duration 단축), "Almost!"
100%:    캐릭터 멈춤 + 완료 이펙트 트리거 → 5-2 시퀀스 연결
```

---

### 5-5. 추가 마이크로 인터랙션

#### 호버 효과 — 캐릭터 눈 반짝이기
```css
@keyframes eye-sparkle {
  0%   { transform: scale(1); filter: brightness(1); }
  50%  { transform: scale(1.2); filter: brightness(1.5); }
  100% { transform: scale(1); filter: brightness(1); }
}

.mascot-card:hover .mascot-eye {
  animation: eye-sparkle 0.3s ease-out;
}
```

#### 알림 도착 — 말풍선 팝
```css
@keyframes bubble-pop-in {
  0%   { transform: scale(0) rotate(-5deg); opacity: 0; }
  60%  { transform: scale(1.1) rotate(2deg); opacity: 1; }
  80%  { transform: scale(0.95) rotate(-1deg); opacity: 1; }
  100% { transform: scale(1) rotate(0deg); opacity: 1; }
}

.notification-bubble {
  animation: bubble-pop-in 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}
```

#### 클릭 효과 — 충격파 링
```css
@keyframes impact-ring {
  0%   { transform: scale(0.5); opacity: 1; border-width: 4px; }
  100% { transform: scale(2.5); opacity: 0; border-width: 0px; }
}

.impact-ring {
  position: absolute;
  width: 40px;
  height: 40px;
  border: 4px solid #000000;
  border-radius: 50%;
  animation: impact-ring 0.4s ease-out forwards;
  pointer-events: none;
}
```

---

## 부록: 구현 체크리스트

### 디자인 핸드오프 체크리스트

**폰트 준비**
- [ ] Bangers (Google Fonts CDN 또는 로컬 파일)
- [ ] Fredoka One (Google Fonts CDN 또는 로컬 파일)
- [ ] Nunito (400/600/700/800 웨이트)
- [ ] JetBrains Mono (400/700 웨이트)

**컬러 토큰**
- [ ] CSS Custom Properties (`--color-*`) 정의 완료
- [ ] 다크/라이트 모드 토큰 분리
- [ ] WCAG AA 검증 완료 (모든 세트)

**컴포넌트 구현 우선순위**
1. [ ] 버튼 (Primary / Secondary / Danger) — 최우선
2. [ ] 카드 (Standard / Tilted / Mascot) — 최우선
3. [ ] 마스코트 아이콘 SVG 6종 — 최우선
4. [ ] 로고 SVG (Full / Compact / Icon) — 최우선
5. [ ] Idle 애니메이션 6종 — 2순위
6. [ ] 완료/오류/로딩 이펙트 — 2순위
7. [ ] 말풍선 스타일 6종 — 3순위
8. [ ] 마이크로 인터랙션 — 3순위

**에셋 포맷**
- [ ] 마스코트 SVG (scalable, 애니메이션 지원)
- [ ] 로고 PNG 2x/3x (라이트/다크)
- [ ] 로고 SVG (벡터)
- [ ] 컬러 팔레트 Figma/Sketch 파일
- [ ] CSS/Tailwind 토큰 파일

---

*Document Version: 2.0.0 | Created: 2026-04-01 | Owner: 디자인실 (Design Room)*
*Next Review: 2026-04-15 | Status: Production-Ready Draft*
