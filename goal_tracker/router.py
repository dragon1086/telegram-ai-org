"""부서별 라우팅 테이블 — 태스크 설명 → 담당 조직 매핑.

6개 부서 키워드 기반 자동 라우팅:
    개발실   (aiorg_engineering_bot) — 구현/코드/API/버그/개발/테스트
    기획실   (aiorg_product_bot)     — 기획/PRD/요구사항/스펙/정책
    디자인실 (aiorg_design_bot)      — 디자인/UI/UX/와이어프레임
    운영실   (aiorg_ops_bot)         — 배포/인프라/모니터링/DevOps
    성장실   (aiorg_growth_bot)      — 성장/마케팅/지표/분석/전략
    리서치실 (aiorg_research_bot)    — 조사/리서치/레퍼런스/경쟁사

라우팅 우선순위:
    1. 키워드 매칭 점수 높은 부서 우선 (내림차순)
    2. 동점 시 priority 낮은 부서 우선 (우선순위 높은 부서)
    3. 매칭 없으면 fallback_org (기본: aiorg_product_bot)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DeptRoute:
    """부서 라우팅 항목."""

    org_id: str
    dept_name: str
    keywords: list[str]
    priority: int = 5           # 1=최고 우선순위 (낮을수록 높음)
    description: str = ""
    emoji: str = ""


# ── 기본 부서 라우팅 테이블 ──────────────────────────────────────────────────

DEPT_ROUTES: list[DeptRoute] = [
    DeptRoute(
        org_id="aiorg_engineering_bot",
        dept_name="개발실",
        emoji="🔧",
        keywords=[
            "구현", "코드", "api", "API", "버그", "개발", "테스트",
            "backend", "frontend", "TypeScript", "Python",
            "서버", "DB", "데이터베이스", "엔드포인트", "모듈",
            "클래스", "함수", "스크립트", "리팩토링", "마이그레이션",
            "빌드", "컴파일", "패키지", "라이브러리",
        ],
        priority=1,
        description="개발/코딩/API 구현/버그 수정",
    ),
    DeptRoute(
        org_id="aiorg_product_bot",
        dept_name="기획실",
        emoji="📋",
        keywords=[
            "기획", "PRD", "요구사항", "스펙", "정책", "사용자 스토리",
            "기능 정의", "로드맵", "유저 리서치", "제품", "플로우",
            "와이어프레임 기획", "설계서", "사업계획", "기능명세",
        ],
        priority=2,
        description="기획/요구사항 분석/PRD 작성",
    ),
    DeptRoute(
        org_id="aiorg_design_bot",
        dept_name="디자인실",
        emoji="🎨",
        keywords=[
            "디자인", "UI", "UX", "와이어프레임", "프로토타입",
            "화면", "레이아웃", "스타일", "컬러", "타이포그래피",
            "아이콘", "배너", "비주얼", "인터랙션", "애니메이션",
            "Figma", "sketch", "디자인 시스템",
        ],
        priority=3,
        description="UI/UX 디자인/와이어프레임/프로토타입",
    ),
    DeptRoute(
        org_id="aiorg_ops_bot",
        dept_name="운영실",
        emoji="⚙️",
        keywords=[
            "배포", "인프라", "모니터링", "운영", "DevOps",
            "CI/CD", "서버 관리", "도커", "Docker", "쿠버네티스",
            "Kubernetes", "AWS", "GCP", "Azure", "로그",
            "알람", "장애", "복구", "스케일링", "보안 패치",
        ],
        priority=4,
        description="운영/배포/인프라/모니터링",
    ),
    DeptRoute(
        org_id="aiorg_growth_bot",
        dept_name="성장실",
        emoji="📈",
        keywords=[
            "성장", "마케팅", "지표", "분석", "전략",
            "사용자 획득", "리텐션", "KPI", "퍼널", "전환율",
            "광고", "SEO", "SNS", "콘텐츠", "이메일 캠페인",
            "A/B 테스트", "코호트", "DAU", "MAU",
        ],
        priority=5,
        description="성장 전략/마케팅/지표 분석",
    ),
    DeptRoute(
        org_id="aiorg_research_bot",
        dept_name="리서치실",
        emoji="🔍",
        keywords=[
            "조사", "리서치", "레퍼런스", "경쟁사", "시장",
            "벤치마크", "문서 요약", "트렌드", "사례 분석",
            "인터뷰", "설문", "데이터 수집", "논문", "기술 조사",
        ],
        priority=6,
        description="시장조사/레퍼런스조사/문서요약/경쟁사분석",
    ),
]

# org_id 집합 (빠른 유효성 검사용)
VALID_ORG_IDS: set[str] = {r.org_id for r in DEPT_ROUTES}


class DeptRouter:
    """부서별 라우팅 테이블 기반 태스크 자동 라우팅.

    사용 예::

        router = DeptRouter()
        org = router.route("REST API 구현 및 단위 테스트 작성")
        # → "aiorg_engineering_bot"

        orgs = router.route_multi("시장 조사 후 기획서 작성", top_n=2)
        # → ["aiorg_research_bot", "aiorg_product_bot"]
    """

    DEFAULT_FALLBACK = "aiorg_product_bot"

    def __init__(self, routes: list[DeptRoute] | None = None) -> None:
        self._routes: list[DeptRoute] = routes or list(DEPT_ROUTES)
        self._by_org: dict[str, DeptRoute] = {r.org_id: r for r in self._routes}

    # ── 라우팅 ────────────────────────────────────────────────────────────

    def route(
        self,
        task_description: str,
        fallback_org: str = DEFAULT_FALLBACK,
    ) -> str:
        """태스크 설명에 가장 적합한 부서의 org_id 반환.

        알고리즘:
            1. 각 부서의 키워드 매칭 횟수 계산 (대소문자 무시)
            2. 매칭 없으면 fallback_org 반환
            3. 매칭 있으면: 매칭 수 내림차순, priority 오름차순 정렬 후 1위 반환

        Args:
            task_description: 라우팅할 태스크 설명.
            fallback_org: 매칭 없을 때 기본 부서.

        Returns:
            org_id 문자열.
        """
        lower = task_description.lower()
        scores: list[tuple[str, int, int]] = []  # (org_id, match_count, priority)

        for route in self._routes:
            matches = sum(1 for kw in route.keywords if kw.lower() in lower)
            if matches > 0:
                scores.append((route.org_id, matches, route.priority))

        if not scores:
            return fallback_org

        # 매칭 수 내림차순, priority 오름차순 (우선순위 높은 부서)
        best = sorted(scores, key=lambda x: (-x[1], x[2]))[0]
        return best[0]

    def route_multi(
        self,
        task_description: str,
        top_n: int = 2,
    ) -> list[str]:
        """매칭 상위 N개 부서 반환 (복합 태스크 병렬 배분용).

        Args:
            task_description: 라우팅할 태스크 설명.
            top_n: 반환할 최대 부서 수.

        Returns:
            org_id 리스트 (점수 높은 순).
        """
        lower = task_description.lower()
        scores: list[tuple[str, int, int]] = []

        for route in self._routes:
            matches = sum(1 for kw in route.keywords if kw.lower() in lower)
            if matches > 0:
                scores.append((route.org_id, matches, route.priority))

        if not scores:
            return []

        sorted_scores = sorted(scores, key=lambda x: (-x[1], x[2]))
        return [s[0] for s in sorted_scores[:top_n]]

    def route_with_score(self, task_description: str) -> list[tuple[str, int]]:
        """모든 부서의 매칭 점수를 반환 (디버깅/분석용).

        Returns:
            [(org_id, match_count)] 리스트, 점수 내림차순.
        """
        lower = task_description.lower()
        scores: list[tuple[str, int]] = []
        for route in self._routes:
            matches = sum(1 for kw in route.keywords if kw.lower() in lower)
            scores.append((route.org_id, matches))
        return sorted(scores, key=lambda x: -x[1])

    # ── 조회 ──────────────────────────────────────────────────────────────

    def get_route(self, org_id: str) -> DeptRoute | None:
        """org_id로 DeptRoute 조회."""
        return self._by_org.get(org_id)

    def get_dept_name(self, org_id: str) -> str:
        """org_id로 부서 이름 반환. 없으면 org_id 그대로."""
        route = self._by_org.get(org_id)
        return route.dept_name if route else org_id

    def all_org_ids(self) -> list[str]:
        """등록된 모든 org_id 반환."""
        return [r.org_id for r in self._routes]

    def is_valid_org(self, org_id: str) -> bool:
        """유효한 org_id인지 확인."""
        return org_id in self._by_org

    # ── 라우팅 계획 미리보기 (dry-run) ───────────────────────────────────

    def plan(self, subtasks: list[dict]) -> dict[str, list[dict]]:
        """서브태스크 목록의 라우팅 계획 반환 (dispatch 전 미리보기).

        Args:
            subtasks: [{"description": str, "assigned_dept": str | None}, ...] 형식.

        Returns:
            {org_id: [subtask_dict]} 형식의 배분 계획.
        """
        result: dict[str, list[dict]] = {}
        for st in subtasks:
            desc = st.get("description", "")
            dept = st.get("assigned_dept") or self.route(desc)
            result.setdefault(dept, []).append(st)
        return result

    def summarize(self) -> list[dict]:
        """라우팅 테이블 요약 반환."""
        return [
            {
                "org_id": r.org_id,
                "dept_name": r.dept_name,
                "emoji": r.emoji,
                "priority": r.priority,
                "keyword_count": len(r.keywords),
                "description": r.description,
            }
            for r in sorted(self._routes, key=lambda x: x.priority)
        ]
