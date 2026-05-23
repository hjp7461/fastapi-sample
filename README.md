# FastAPI 클린 아키텍처 프로젝트

모듈 기능 기반(Module-Functionality) 구조를 적용한 FastAPI 클린 아키텍처 프로젝트 템플릿입니다.

## 프로젝트 개요

이 프로젝트는 클린 아키텍처 원칙을 준수하면서 기능 중심으로 모듈화된 FastAPI 애플리케이션 구조를 제공합니다. 사용자 관리와 상품 관리 기능을 중심으로 구성되어 있으며, 확장성과 유지보수성을 높인 구조로 설계되었습니다.

### 주요 기술 스택

- **FastAPI**: 고성능 비동기 웹 프레임워크
- **SQLAlchemy 2.0**: 비동기 ORM(`async_scoped_session` 활용)
- **SQLModel**: SQLAlchemy와 Pydantic의 장점을 결합한 ORM
- **Alembic**: 데이터베이스 마이그레이션 도구
- **Pydantic**: 데이터 검증 및 설정 관리
- **Dependency Injector**: 의존성 주입 컨테이너
- **Loguru**: 고급 로깅 라이브러리
- **uv**: 현대적인 Python 패키지 관리자

## 프로젝트 구조

프로젝트는 기능별 모듈화 방식(Module-Functionality)으로, 관련 코드가 함께 배치되어 있습니다.

```
/app
├── core/                      # 핵심 모듈 (공통 기능)
│   ├── config.py              # Settings (환경 변수 진실원, RUNBOOK §2 참고)
│   ├── database.py            # async engine / get_db
│   ├── datetime.py            # utcnow_aware() 헬퍼 (timezone-aware UTC)
│   ├── logging.py             # setup_logging() — loguru sink + stdlib InterceptHandler
│   ├── security.py            # bcrypt 직접 사용 + JWT + needs_rehash
│   └── exceptions.py          # 도메인 / 비즈니스 예외
│
├── user/                      # 사용자 관리 모듈
│   ├── domain.py              # User / UserRole (is_admin, is_staff_or_above, can_manage_products)
│   ├── models.py              # SQLAlchemy 모델
│   ├── masking.py             # mask_email — PII 마스킹 헬퍼
│   ├── schemas.py             # UserResponse(본인) / UserAdminView(타인) / UserSummary(목록)
│   ├── repository.py          # 데이터 액세스 로직
│   ├── service.py             # authenticate_user (lazy rehash) 등
│   └── router.py              # /users 엔드포인트
│
├── product/                   # 상품 관리 모듈
│   ├── domain.py              # Product 도메인
│   ├── models.py              # SQLAlchemy 모델
│   ├── schemas.py             # ProductResponse(Full) / ProductPublicView(inventory 제외)
│   ├── repository.py          # update_inventory → InventoryUpdateOutcome (enum 결과 패턴)
│   ├── service.py             # 비즈니스 로직
│   └── router.py              # /products 엔드포인트 (viewer 분기)
│
├── api/                       # 인증 / 권한 / 라우터 통합
│   ├── dependencies.py        # 인증: get_current_user / get_optional_current_user
│   ├── permissions.py         # 권한 가드: require_admin / require_self_or_admin / require_staff_or_admin
│   └── router.py              # 메인 API 라우터
│
├── di/                        # 의존성 주입 설정
│   ├── containers.py          # dependency_injector Container
│   └── providers.py           # named helper (Depends(get_xxx_service))
│
└── main.py                    # FastAPI app + lifespan + setup_logging()

alembic/                       # 스키마 마이그레이션 단일 진실원
├── env.py                     # async + settings.DATABASE_URL fallback
└── versions/                  # 리비전 파일들
```

## 클린 아키텍처 적용

이 프로젝트는 다음과 같은 클린 아키텍처 원칙을 따릅니다:

1. **도메인 중심 설계**: 도메인 엔티티는 비즈니스 로직을 포함하며 어떤 프레임워크나 데이터베이스에도 의존하지 않습니다.

2. **의존성 규칙**: 외부 계층이 내부 계층에 의존하며, 내부 계층은 외부 계층을 알지 못합니다.
   - 도메인 엔티티 (domain.py) → 레포지토리 인터페이스 → 서비스 (service.py) → API 엔드포인트 (router.py)

3. **의존성 주입**: 구체적인 구현보다 추상화에 의존하도록 의존성 주입 패턴을 사용합니다.

## 비동기 데이터베이스 처리

SQLAlchemy 2.0의 비동기 기능과 `async_scoped_session`을 사용하여 효율적인 비동기 데이터베이스 작업을 구현했습니다:

```python
# app/core/database.py (핵심 부분)
AsyncScopedSession = async_scoped_session(
    async_session_factory,
    scopefunc=asyncio.current_task
)
```

이 설정은 각 비동기 요청 컨텍스트에서 동일한 데이터베이스 세션을 공유하도록 합니다.

## 설치 및 실행

### 의존성 설치

[uv](https://github.com/astral-sh/uv)를 사용하여 의존성을 설치합니다:

```bash
# 모든 extras (dev, test) 포함 설치 — lockfile (uv.lock) 기반
uv sync --all-extras
```

### Pre-commit hook (선택, 권장)

ruff check/format 과 기본 위생 hook (trailing-whitespace, EOF newline 등) 을
커밋 시점에 자동 실행합니다.

```bash
# 1회: git hook 활성화
uv run pre-commit install

# 전체 파일에 한 번 실행 (수동)
uv run pre-commit run --all-files
```

이후 `git commit` 시 hook 이 자동 실행되어 lint/포맷 위반이 있으면 차단합니다.
`.pre-commit-config.yaml` 의 ruff rev 는 `pyproject.toml` 의 ruff 버전과
일치시켜 두었으므로 룰 차이가 발생하지 않습니다.

### 환경 변수 설정

`.env` 파일을 생성하고 필요한 환경 변수를 설정합니다:

```bash
# .env
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite+aiosqlite:///./app.db
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

### 데이터베이스 마이그레이션

```bash
# 마이그레이션 생성 (모델 변경 후)
uv run alembic revision --autogenerate -m "메시지"

# 마이그레이션 적용
uv run alembic upgrade head
```

> 운영 명령 매트릭스 (롤백 / Postgres 이전 / 트러블슈팅) 는 [`docs/RUNBOOK.md`](docs/RUNBOOK.md) §4~§8 참조.

### 애플리케이션 실행

```bash
# 개발 서버 실행
uv run uvicorn app.main:app --reload
```

## API 문서

애플리케이션이 실행되면 다음 URL에서 API 문서를 확인할 수 있습니다:

- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc

## 권한 정책

권한 매트릭스의 운영자 진실원은 [`docs/RUNBOOK.md`](docs/RUNBOOK.md) §9. 본 README 는 인덱스만 제공합니다.

- 역할 계층: `CUSTOMER ⊂ STAFF ⊂ ADMIN` (`app/user/domain.py`)
- 권한 가드 (`app/api/permissions.py`):
  - `require_admin` — ADMIN 전용 (사용자 관리)
  - `require_self_or_admin` — 본인 또는 ADMIN (사용자 단건 조회)
  - `require_staff_or_admin` — STAFF + ADMIN (상품 변경)
- 정책 결정 배경: PR #19 (viewer 분기) / PR #26 (B-2: 상품은 STAFF, 사용자 관리는 ADMIN) / PR #27 (RUNBOOK §9 정착)
- 다이어그램: [`docs/diagram/인증_및_권한.md`](docs/diagram/인증_및_권한.md) §2

정책 변경 시는 RUNBOOK §9.5 의 갱신 순서를 따릅니다 (도메인 → 가드 → 라우터 → 테스트 → RUNBOOK → 다이어그램).

## 테스트

```bash
# 테스트 실행
uv run pytest

# 코드 커버리지 보고서와 함께 테스트 실행
uv run pytest --cov=app
```

## 로깅

`app/core/logging.py::setup_logging()` 이 진입점 (`app/main.py` import 시점) 에서 한 번 호출되어
loguru sink + stdlib `logging` InterceptHandler 를 모두 설정합니다. 애플리케이션 코드는 loguru 를
직접 import 합니다:

```python
from loguru import logger

logger.info("정보 메시지", user_id=42)
logger.bind(request_id="abc").warning("경고")
```

운영 토글은 환경 변수로 제어합니다 (자세한 매트릭스는 [`docs/RUNBOOK.md`](docs/RUNBOOK.md) §2 참조):

- `LOG_LEVEL` — `DEBUG` / `INFO` / `WARNING` / `ERROR`
- `LOG_FORMAT` — `text` (개발, 컬러 사람-친화) / `json` (운영, 수집 파이프라인 연결)
- `LOG_FILE` / `LOG_FILE_ROTATION` / `LOG_FILE_RETENTION` — 파일 sink 옵션

## 라이센스

MIT
