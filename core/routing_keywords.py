"""부서 라우팅 키워드 사전 — autoresearch 자율 최적화 타겟 파일.

이 파일만 수정해서 라우팅 정확도를 개선한다.
pm_orchestrator.py의 _BASE_DEPT_KEYWORDS / _BASE_DEPT_ORDER 를 여기서 관리.

autoresearch 루프:
    score_before = eval → 이 파일 수정 → score_after
    score_after > score_before → git commit
    else → git reset
"""

# 부서별 키워드: 하나라도 포함되면 해당 부서가 dept_hints에 추가됨
BASE_DEPT_KEYWORDS: dict[str, list[str]] = {
    "aiorg_pm_bot": [
        "회의", "미팅", "안건", "okr", "로드맵", "스프린트", "백로그",
        "일정", "마일스톤", "우선순위", "리소스", "배분", "킥오프",
        "회고", "retro", "이해관계자", "역량", "팀 커뮤니케이션",
        "변경 관리", "분기 계획", "성과 지표 정의",
        "위험",
        "요소",
        "식별",
        "대응",
        "빌딩",
        "활동",
        "업무",
        "분담",
        "조율",
        "외부 의존성 관리",
        "프로젝트",
        "범위",
        "예산",
        "추적",
        "출시",
        "수립",
    ],
    "aiorg_product_bot": [
        "기획", "스펙", "요구사항", "prd", "plan", "기능 정의", "유저스토리",
    ],
    "aiorg_research_bot": [
        "리서치", "research", "시장조사", "레퍼런스", "reference",
        "경쟁사", "벤치마킹", "벤치마크", "문서요약", "자료조사",
        "사용자 인터뷰", "인터뷰", "설문", "페르소나", "행동 패턴", "세그먼트", "a/b 테스트 결과", "퍼널 분석", "리텐션 지표",
        "고객 여정", "nps", "코호트", "이탈률", "클릭률",
        "제품-시장 적합성", "인터뷰 데이터",
        "성장 지표 대시보드",
        "시장",
        "트렌드",
        "조사",
        "고객",
        "피드백",
        "카테고리",
        "분류",
        "사용성 테스트 설계",
    ],
    "aiorg_engineering_bot": [
        "개발", "구현", "코딩", "코드", "api", "build", "fix", "버그",
        "파이썬", "python", "스크립트", "함수", "메서드", "알고리즘",
        "프로그래밍", "클래스", "모듈", "데이터베이스", "스키마",
        "typescript", "타입스크립트", "docker", "ci/cd", "sql",
        "redis", "oauth", "jwt", "elasticsearch", "pytest",
        "테스트", "단위 테스트", "메모리 누수", "디버깅", "마이그레이션",
        "rate limit", "인증", "캐싱", "의존성", "패키지",
        "pytest 테스트 실패 분석",
        "websocket",
        "연결",
        "오류",
        "해결",
        "로그 모니터링 설정",
        "환경변수",
        "문제",
        "해결",
        "보안",
        "취약점",
        "패치",
        "마이크로서비스",
        "분리",
        "메시지",
    ],
    "aiorg_design_bot": [
        "디자인", "ui", "ux", "화면", "레이아웃", "design",
        "색상", "팔레트", "프로토타입", "와이어프레임", "아이콘",
        "타이포그래피", "폰트", "브랜드", "반응형", "접근성",
        "인터페이스", "컴포넌트 스타일", "온보딩 플로우",
        "이메일 템플릿", "인포그래픽", "소셜 미디어 그래픽", "오류 화면",
        "사용자",
        "경험",
        "방안",
        "다크모드",
        "지원",
        "사용자",
        "흐름",
        "다이어그램",
        "애니메이션",
        "효과",
        "컴포넌트",
        "라이브러리",
        "구축",
    ],
    "aiorg_growth_bot": [
        "성장", "마케팅", "growth", "marketing", "지표", "대시보드",
        "a/b 테스트", "퍼널", "전환율", "리텐션",
    ],
    "aiorg_ops_bot": [
        "운영", "배포", "인프라", "모니터링", "deploy", "ops",
    ],
}

# 부서 우선순위 (동시 매칭 시 앞쪽이 우선)
BASE_DEPT_ORDER: list[str] = [
    "aiorg_pm_bot",
    "aiorg_product_bot",
    "aiorg_research_bot",
    "aiorg_design_bot",
    "aiorg_engineering_bot",
    "aiorg_growth_bot",
    "aiorg_ops_bot",
]

# 테스트 케이스 정답 매핑 (evals/routing/test_cases.json correct_bot → org_id)
CORRECT_BOT_MAP: dict[str, str] = {
    "pm": "aiorg_pm_bot",
    "product": "aiorg_product_bot",
    "research": "aiorg_research_bot",
    "engineering": "aiorg_engineering_bot",
    "design": "aiorg_design_bot",
    "growth": "aiorg_growth_bot",
    "ops": "aiorg_ops_bot",
}
