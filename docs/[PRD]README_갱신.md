# [PRD] README 갱신 — 로깅 / 구조 트리 / 권한 신설 + 명령 표기 보강

## 배경

루트 `README.md` 가 PR #11~#28 누적 변경을 미반영해 신규 컨트리뷰터/운영자 진입점 (저장소 첫 인상) 으로서 부정합:

| 항목 | 현재 README | 실제 코드 / 운영 |
| --- | --- | --- |
| §로깅 (line 161-174) | `from app.core.logging import get_logger` (**거짓**, 존재하지 않는 함수) | PR #23 에서 `setup_logging()` + loguru 직접 사용 + stdlib InterceptHandler. `LOG_FORMAT` 환경 변수 토글. |
| §프로젝트 구조 (line 20-57) | `app/core/` 4파일 / `app/api/` 2파일 / `app/di/` 1파일 / `app/user/` 6파일 / `alembic` 누락 | 신규 5개 모듈 (`app/core/datetime.py` PR #12, `app/api/permissions.py` PR #20, `app/di/providers.py` PR #17, `app/user/masking.py` PR #15, `app/core/logging.py` 갱신 PR #23) + `alembic/` 디렉토리 (PR #14) 누락 |
| §권한 (부재) | 없음 | PR #19/#20/#26/#27 로 정책 진실원 RUNBOOK §9 정착. README 에서 권한 단락 인덱스 부재 → 신규 컨트리뷰터가 권한 매트릭스 위치 모름 |
| §의존성 설치 / §데이터베이스 마이그레이션 / §테스트 명령 | `uv pip install -e .` / `alembic` / `pytest` | 프로젝트 관성은 `uv sync --all-extras` / `uv run alembic ...` / `uv run pytest` (handoff §1, RUNBOOK §5 일상 명령 매트릭스) |

남은 결정 사항: §환경 변수 단락의 5개 변수 부재 (BCRYPT_ROUNDS / USER_ADMIN_EMAIL_MASKING / LOG_* 5개) — 본 PR 비목적 (RUNBOOK §2 가 진실원이라 README 에선 인덱스 한 줄로 충분, §환경 변수 단락의 전면 갱신은 별도 후속).

## 목적

1. **§로깅 정합성 복원** — 거짓 `get_logger` 코드 제거. `setup_logging()` + `LOG_FORMAT` 환경 변수 토글 (`text` / `json`) 의 실제 사용법 명시. 운영자가 README 만 보고 따라 해도 동작하는 상태.
2. **§프로젝트 구조 정합성 복원** — 신규 5개 모듈 + `alembic/` 디렉토리 트리에 반영. PR #14/#15/#17/#20/#23 의 결과가 진입점 문서에서 보이게.
3. **§권한 신설** — RUNBOOK §9 의 진실원 위치 명시 + 가드/도메인 메서드 핵심 한 줄 인덱스. README 가 권한 정책의 시작점 (RUNBOOK 깊이 들어가는 입구) 역할.
4. **명령 표기 보강** — `pytest` → `uv run pytest`, `alembic` → `uv run alembic`, 설치 → `uv sync --all-extras`. handoff §1 / RUNBOOK §5 와 일관.

## 비목적

- **§환경 변수 단락 전면 갱신** — RUNBOOK §2 가 진실원. README 는 한 줄 인덱스만으로 충분. 전면 갱신은 별도 후속 (마스터 목록 ⬜).
- **§클린 아키텍처 / §비동기 데이터베이스 처리 / §API 문서 단락 갱신** — 본 PR 비범위. 변경 없음.
- **README 전면 재구성 (목차 추가 / 톤 변경 등)** — 본 PR 은 누적 정합성 회복에 한정.
- **CLAUDE.md / AGENTS.md 같은 다른 README 류 신설** — 없음.

## 성공 기준

| 기준 | 검증 |
| --- | --- |
| `grep -n "get_logger" README.md` → 0 hit | grep |
| `setup_logging` / `LOG_FORMAT` README 에 명시 | grep `setup_logging\|LOG_FORMAT` ≥ 2 |
| 구조 트리에 5개 신규 모듈 + `alembic/` 표시 | grep `datetime.py\|permissions.py\|providers.py\|masking.py\|alembic/` ≥ 5 |
| §권한 단락 신설 + RUNBOOK §9 링크 + 가드 3개 명명 명시 | grep `require_admin\|require_self_or_admin\|require_staff_or_admin` ≥ 3 |
| 명령 표기: `uv run pytest`, `uv run alembic`, `uv sync --all-extras` | grep |
| `pre-commit run --all-files` 종료 코드 0 | 명령 결과 |
| 테스트 카운트 변화 없음 (74 PASS) | `uv run pytest 2>&1 \| tail -1` |

## 설계

### 1. §프로젝트 구조 갱신 (line 20-57)

신규 모듈 5개 + alembic 디렉토리 반영. 코드 변경 없는 단순 트리 갱신.

```
/app
├── core/
│   ├── config.py              # 환경 설정 (Settings)
│   ├── database.py            # async engine / get_db
│   ├── datetime.py            # utcnow_aware() 헬퍼 (PR #12)
│   ├── logging.py             # setup_logging() + loguru sink (PR #23)
│   ├── security.py            # bcrypt + JWT
│   └── exceptions.py
├── api/
│   ├── dependencies.py        # 인증 (get_current_user / get_optional_current_user)
│   ├── permissions.py         # 권한 가드 (require_admin / require_self_or_admin / require_staff_or_admin) (PR #20/#26)
│   └── router.py
├── user/
│   ├── domain.py              # User / UserRole (is_admin / is_staff_or_above / can_manage_products)
│   ├── models.py
│   ├── masking.py             # mask_email (PR #15)
│   ├── schemas.py             # UserResponse / UserAdminView / UserSummary
│   ├── repository.py
│   ├── service.py
│   └── router.py
├── product/
│   ├── domain.py / models.py
│   ├── schemas.py             # ProductResponse / ProductPublicView (PR #19)
│   ├── repository.py
│   ├── service.py
│   └── router.py
├── di/
│   ├── containers.py
│   └── providers.py           # named helper (Depends(get_xxx_service)) (PR #17)
└── main.py                    # lifespan + setup_logging() 호출

alembic/                       # 스키마 마이그레이션 (PR #14, 단일 진실원)
```

### 2. §권한 단락 신설 (§API 문서 다음, §테스트 앞)

```markdown
## 권한 정책

권한 매트릭스의 운영자 진실원은 `docs/RUNBOOK.md` §9. 본 README 는 인덱스만 제공.

- 역할 계층: `CUSTOMER ⊂ STAFF ⊂ ADMIN` (`app/user/domain.py`)
- 권한 가드 (`app/api/permissions.py`):
  - `require_admin` — ADMIN 전용 (사용자 관리)
  - `require_self_or_admin` — 본인 또는 ADMIN (사용자 조회)
  - `require_staff_or_admin` — STAFF + ADMIN (상품 변경)
- 정책 결정 배경: PR #19 (viewer 분기) / PR #26 (B-2: 상품은 STAFF, 사용자 관리는 ADMIN) / PR #27 (RUNBOOK §9 정착)
- 다이어그램: `docs/diagram/인증_및_권한.md` §2

정책 변경 시는 RUNBOOK §9.5 의 갱신 순서를 따른다 (도메인 → 가드 → 라우터 → 테스트 → RUNBOOK → 다이어그램).
```

### 3. §로깅 단락 재작성 (line 161-174)

거짓 `get_logger` 제거. 실제 사용 패턴 명시.

```markdown
## 로깅

`app/core/logging.py::setup_logging()` 이 진입점에서 한 번 호출되어 loguru sink 와
stdlib `logging` InterceptHandler 를 모두 설정한다 (PR #23). 애플리케이션 코드는
loguru 를 직접 import 한다:

```python
from loguru import logger

logger.info("정보 메시지", user_id=42)
logger.bind(request_id="abc").warning("경고")
```

운영 토글은 환경 변수로 제어한다 (자세한 매트릭스는 `docs/RUNBOOK.md` §2):

- `LOG_LEVEL` — DEBUG / INFO / WARNING / ERROR
- `LOG_FORMAT` — `text` (개발, 컬러 사람-친화) / `json` (운영, 수집 파이프라인 연결)
- `LOG_FILE` / `LOG_FILE_ROTATION` / `LOG_FILE_RETENTION` — 파일 sink 옵션
```

### 4. 명령 표기 보강

- §의존성 설치: `uv pip install -e .[dev,test]` → `uv sync --all-extras` (한 줄로 단순화)
- §데이터베이스 마이그레이션: `alembic ...` → `uv run alembic ...` (2 곳)
- §테스트: `pytest` → `uv run pytest`, `pytest --cov=app` → `uv run pytest --cov=app` (2 곳)
- §애플리케이션 실행: `uvicorn app.main:app --reload` → `uv run uvicorn app.main:app --reload`

### 5. 파일 변경 요약

- `README.md`:
  - §프로젝트 구조 트리 갱신 (~5 모듈 추가 + 주석 보강 + alembic 행)
  - §권한 단락 신설 (~15 줄)
  - §로깅 단락 재작성 (~15 줄)
  - 명령 6 곳 표기 보강

## 영향

- **신규 컨트리뷰터 / 운영자**: README 만 보고도 모든 명령 / 모듈 / 권한 인덱스가 정확. RUNBOOK / 다이어그램 / 코드 진실원으로의 진입 경로 명확.
- **코드 변경 0** / 테스트 카운트 변화 없음 (74 PASS).
- **handoff §6 ⬜ 3건 동시 해소** + PR #28 다이어그램 갱신 마무리.

## 리스크

1. **§로깅 코드 스니펫의 정합성** — `loguru` 의 실제 사용 패턴이 PR #11/#13/#23 에서 변하면서 README 가 다시 stale 될 가능성.
   - 완화: README 의 §로깅 본문은 최소화 + RUNBOOK §2 + `app/core/logging.py` 를 진실원으로 명시 (다른 곳에서는 코드 스니펫 1개만 유지).
2. **구조 트리 갱신과 실제 코드 drift** — 새 모듈이 추가되면 README 도 동반 갱신 필요. 회귀 가드 없음.
   - 완화: 본 PR 비목적. CI 가드는 별도 후속.

## 결정 사항 (확정)

- [x] **§환경 변수 단락 전면 갱신은 별도 후속** — 본 PR 은 RUNBOOK §2 인덱스 안내 한 줄로만 보강.
- [x] **§권한 단락 위치**: §API 문서 다음, §테스트 앞 (의미 흐름 = API 진입 → 권한 → 테스트).
- [x] **§로깅 스니펫은 1개만** — loguru 직접 import 패턴. `get_logger` 같은 wrapper 함수 부재를 명시적으로 인정.
- [x] **명령 표기 일관성**: `uv run <cmd>` 또는 `uv sync` 패턴. handoff §1 / RUNBOOK §5 와 일치.

## 참고

- PR #11 (loguru 첫 사용), #13 (재해시 로깅), #23 (setup_logging + InterceptHandler)
- PR #14 (alembic), #15 (PII 마스킹), #17 (DI providers), #20 (permissions 분리), #26 (require_* 명명), #27 (RUNBOOK §9)
- 진실원: `app/core/logging.py`, `app/api/permissions.py`, `docs/RUNBOOK.md` §2 / §9
