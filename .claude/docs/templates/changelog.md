# Changelog

> Keep a Changelog 형식 준수 (https://keepachangelog.com/ko/1.0.0/)
> 버전은 Semantic Versioning을 따른다 (MAJOR.MINOR.PATCH)
> 저장 위치: 프로젝트 루트 `CHANGELOG.md` 또는 `docs/CHANGELOG.md`

---

## [Unreleased]

### Added

-

### Changed

-

### Fixed

-

### Removed

-

### Security

-

---

## [X.Y.Z] - YYYY-MM-DD

> 릴리즈 요약: (이 버전에서 가장 중요한 변경 1-2줄)

### Added (신규 추가)

> 새로 추가된 기능, 스킬, 봇, 모듈 등을 기록한다.

- **[봇/모듈명]**: 설명 (관련 태스크: T-XXXX)
-

### Changed (변경)

> 기존 동작 방식이 바뀐 항목을 기록한다.

- **[봇/모듈명]**: 변경 전 → 변경 후 (관련 ADR: ADR-NNNN)
-

### Fixed (버그 수정)

> 수정된 버그를 기록한다.

- **[봇/모듈명]**: 증상 설명 → 수정 방법 (관련 인시던트: INC-YYYY-NNNN)
-

### Removed (제거)

> 삭제된 기능, 파일, 설정 등을 기록한다.

- **[봇/모듈명]**: 제거 이유
-

### Security (보안)

> 보안 관련 변경사항을 기록한다.

-

---

## [X.Y.Z-1] - YYYY-MM-DD

### Added

-

### Fixed

-

---

## 버전 관리 정책

| 버전 유형 | 언제 올리나 | 예시 |
|----------|-----------|------|
| **PATCH** (0.0.X) | 버그 수정, 문서 수정 | 1.2.3 → 1.2.4 |
| **MINOR** (0.X.0) | 신규 기능 추가 (하위 호환) | 1.2.3 → 1.3.0 |
| **MAJOR** (X.0.0) | 하위 호환 불가 변경 | 1.2.3 → 2.0.0 |

---

## 링크

[Unreleased]: https://github.com/example/repo/compare/vX.Y.Z...HEAD
[X.Y.Z]: https://github.com/example/repo/compare/vX.Y.Z-1...vX.Y.Z

---

*이 템플릿은 `.claude/docs/templates/changelog.md` 기준.*
*새 버전 릴리즈 시 [Unreleased] 섹션 내용을 새 버전 섹션으로 이동 후 날짜 기입.*
