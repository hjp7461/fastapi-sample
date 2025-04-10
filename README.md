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
│   ├── config.py              # 환경 설정
│   ├── database.py            # 데이터베이스 연결 및 설정
│   ├── security.py            # 인증, 암호화 관련 유틸리티
│   ├── exceptions.py          # 커스텀 예외 정의
│   └── logging.py             # 로깅 설정
│
├── user/                      # 사용자 관리 모듈
│   ├── domain.py              # 사용자 도메인 엔티티
│   ├── models.py              # 데이터베이스 모델
│   ├── schemas.py             # Pydantic 모델 (API 스키마)
│   ├── repository.py          # 데이터 액세스 로직
│   ├── service.py             # 비즈니스 로직
│   └── router.py              # API 엔드포인트
│
├── product/                   # 상품 관리 모듈
│   ├── domain.py              # 상품 도메인 엔티티
│   ├── models.py              # 데이터베이스 모델
│   ├── schemas.py             # Pydantic 모델 (API 스키마)
│   ├── repository.py          # 데이터 액세스 로직
│   ├── service.py             # 비즈니스 로직
│   └── router.py              # API 엔드포인트
│
├── api/                       # API 라우터 통합
│   ├── dependencies.py        # 공통 의존성
│   └── router.py              # 메인 API 라우터
│
├── di/                        # 의존성 주입 설정
│   └── containers.py          # 의존성 주입 컨테이너
│
└── main.py                    # 애플리케이션 진입점
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
# 기본 의존성 설치
uv pip install -e .

# 개발 및 테스트 의존성 포함 설치
uv pip install -e ".[dev,test]"
```

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
# 마이그레이션 생성
alembic revision --autogenerate -m "Initial migration"

# 마이그레이션 적용
alembic upgrade head
```

### 애플리케이션 실행

```bash
# 개발 서버 실행
uvicorn app.main:app --reload
```

## API 문서

애플리케이션이 실행되면 다음 URL에서 API 문서를 확인할 수 있습니다:

- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc

## 테스트

```bash
# 테스트 실행
pytest

# 코드 커버리지 보고서와 함께 테스트 실행
pytest --cov=app
```

## 로깅

애플리케이션은 Loguru를 사용하여 구조화된 로깅을 제공합니다:

```python
from app.core.logging import get_logger

logger = get_logger("module_name")
logger.info("정보 메시지")
logger.error("오류 발생", extra={"context": "추가 정보"})
```

- 개발 환경: 컬러링된 사람이 읽기 쉬운 로그
- 프로덕션 환경: JSON 형식의 구조화된 로그

## 라이센스

MIT