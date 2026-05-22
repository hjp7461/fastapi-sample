# 테스트 아키텍처 개선 구현 Plan

| 항목     | 내용                                          |
| -------- | --------------------------------------------- |
| 작성일   | 2026-05-22                                    |
| 연관 PRD | [`[PRD]테스트_아키텍처_개선.md`](./[PRD]테스트_아키텍처_개선.md) |
| 상태     | 제안 (Draft)                                  |
| 추정 작업량 | 약 2~3시간 (구현 + 검증)                       |

---

## 0. 사전 점검 (Pre-flight)

작업 시작 전 다음을 만족해야 한다.

- [ ] `mise install` 완료 (Python 3.12.12, uv 최신)
- [ ] `uv sync --all-extras` 실행으로 dev/test extras 설치 완료
- [ ] `pyproject.toml`의 `[tool.pytest.ini_options]` 오타 수정 반영 (완료됨)
- [ ] `tests/conftest.py`의 `ASGITransport` 연결 / fixture scope 정리 반영 (완료됨)
- [ ] 현재 상태에서 `uv run pytest --collect-only -q`가 18개 테스트를 정상 수집

---

## 1. 작업 분해

작업은 4개 단계로 나뉘며 각 단계 종료 시 반드시 검증 명령을 통과해야 한다.

### Step 1. 테스트용 DB 엔진 fixture 도입

**대상 파일**: `tests/conftest.py`

**변경 내용**

1. 불필요 임포트 정리 (`asyncio`, `Dict`, `Any` 미사용 제거).
2. `StaticPool` 및 `sessionmaker` 임포트 추가.
3. 기존 `engine` fixture를 다음과 같이 교체.

```python
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

@pytest_asyncio.fixture
async def engine():
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=False,
        future=True,
    )

    # 테이블 생성 (Base + SQLModel 양쪽 모두)
    from app.user.models import UserModel  # noqa: F401
    from app.product.models import ProductModel  # noqa: F401
    from app.core.database import Base
    from sqlmodel import SQLModel

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(SQLModel.metadata.create_all)

    yield test_engine

    await test_engine.dispose()
```

**검증**

```bash
uv run pytest --collect-only -q
```

수집 결과는 변동 없어야 한다 (18개).

---

### Step 2. Container 의존성 override fixture 도입

**대상 파일**: `tests/conftest.py`

**변경 내용**

1. `Container`를 import한다.
2. `engine`에 의존하는 `container_override` fixture를 작성한다 (autouse=True).
3. `session_factory` fixture는 기존 `engine`을 그대로 사용하되 명시적으로 test engine에 바인딩한다.
4. teardown 순서: `Container.db.shutdown()` → `reset_override()` → engine은 `engine` fixture가 dispose.

```python
import pytest
from dependency_injector import providers
from app.di.containers import Container

@pytest_asyncio.fixture(autouse=True)
async def container_override(engine):
    test_session_factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    Container.engine.override(providers.Singleton(lambda: engine))
    Container.session_factory.override(providers.Factory(lambda: test_session_factory))

    yield

    # 스코프 세션 정리 (테스트 간 누수 방지)
    if Container.db.initialized:
        scoped = Container.db()
        await scoped.remove()
        Container.db.shutdown()

    Container.engine.reset_override()
    Container.session_factory.reset_override()

@pytest.fixture
def session_factory(engine):
    return sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
```

> **주의**: `providers.Factory(lambda: test_session_factory)`로 감싸야 한다. `Container.session_factory`가 `providers.Factory(sessionmaker, engine, ...)` 형태로 정의되어 있어, 호출될 때마다 새 객체를 만든다고 가정하는 곳이 있을 수 있으므로 동일한 `sessionmaker` 인스턴스를 매번 반환하는 람다로 단순화한다.

**검증**

```bash
uv run pytest tests/user/test_router.py::test_create_user -x --tb=short
```

`OperationalError: no such table: users`가 사라지고 PASS 또는 다른 에러로 바뀌어야 한다.

---

### Step 3. 시드 픽스처 정상화 + httpx 클라이언트 정리

**대상 파일**: `tests/conftest.py`

**변경 내용**

1. `setup_db` fixture 제거 (이제 `engine` fixture가 테이블 생성을 직접 수행).
2. `db_session` fixture가 `engine` 의존만 받도록 단순화.
3. `client` fixture는 이미 ASGI 트랜스포트로 수정되어 있음 — base_url을 `http://testserver`로 유지.
4. `test_user`, `admin_user`, `test_product` fixture는 `db_session` 의존만 유지하고 그대로 둔다.
5. `auth_headers`, `admin_auth_headers`는 그대로 둔다.

```python
@pytest_asyncio.fixture
async def db_session(engine, session_factory):
    async with session_factory() as session:
        yield session
```

**검증**

```bash
uv run pytest tests/user/test_router.py -x --tb=short
```

`test_create_user`, `test_login`이 PASS. `test_get_current_user` 등 토큰 기반 테스트도 PASS.

---

### Step 4. 전체 회귀 검증 및 정리

**검증**

```bash
uv run pytest -v
uv run pytest --cov=app --cov-report=term-missing
```

- 18/18 PASS 확인
- 커버리지 리포트 정상 생성 확인

**(선택) 추가 정리**

- `tests/pytest.ini`의 `log_cli = true` → `false`로 변경 (테스트 출력 시각적 정리, 진단 시 다시 켤 수 있도록 주석 처리 권장)
- `tests/_init_.py` 오타 파일 삭제 (`__init__.py`만 남김)

---

## 2. 산출물 체크리스트

- [ ] `tests/conftest.py` 재작성 완료
- [ ] `uv run pytest -v` 18/18 PASS
- [ ] `uv run pytest --cov=app` 정상 실행 및 커버리지 출력
- [ ] 프로덕션 코드(`app/**`) 변경 없음 (git diff로 확인)
- [ ] 모든 비동기 경로 유지 (`async def`/`await` 우회 없음)

---

## 3. 테스트 케이스 (완료 판정 기준)

본 Plan의 "완료"는 **다음 18개 테스트가 모두 PASS**해야 한다. 단순 통과 외에 각 그룹의 추가 검증 포인트를 명시한다.

### 3.1 사용자 라우터 (tests/user/test_router.py)

| # | 테스트                                          | 핵심 검증 포인트                                       |
| - | ----------------------------------------------- | ------------------------------------------------------ |
| 1 | `test_create_user`                              | 201 응답, 응답에 `password` 미포함, `id` 발급          |
| 2 | `test_login`                                    | 200 응답, `access_token` + `token_type=bearer`         |
| 3 | `test_get_current_user`                         | 200 응답, 인증된 사용자 정보 반환                      |
| 4 | `test_update_current_user`                      | 200 응답, 부분 업데이트(`first_name`, `username`) 반영 |
| 5 | `test_get_user_by_id`                           | 200 응답, 시드 사용자 정보와 일치                      |
| 6 | `test_get_nonexistent_user`                     | 404 응답, `detail` 메시지 포함                         |
| 7 | `test_access_admin_endpoint_as_regular_user`    | 403 응답 (권한 부족)                                   |
| 8 | `test_access_admin_endpoint_as_admin`           | 200 응답, 사용자 리스트에 최소 1명 포함                |

### 3.2 상품 라우터 (tests/product/test_router.py)

| # | 테스트                                       | 핵심 검증 포인트                                  |
| - | -------------------------------------------- | ------------------------------------------------- |
| 9 | `test_create_product_unauthorized`           | 인증 없이 호출 시 401                             |
| 10 | `test_get_product`                           | 200, 시드 상품 정보 일치                          |
| 11 | `test_list_products`                         | 200, 리스트 타입                                  |
| 12 | `test_create_product_as_regular_user`        | 403 (권한 부족)                                   |
| 13 | `test_create_product_as_admin`               | 201, 응답에 입력값 반영                           |
| 14 | `test_update_product_as_admin`               | 200, 변경된 필드 반영                             |
| 15 | `test_update_inventory_as_admin`             | 200, 재고 수치 갱신                               |
| 16 | `test_delete_product_as_admin`               | 204 또는 200 (라우터 정의 확인 후 PASS 기준 확정) |
| 17 | `test_filter_products_by_category`           | 200, 필터 결과의 카테고리 일치                    |
| 18 | `test_filter_products_by_active_status`      | 200, `is_active=True` 필터 동작                   |

### 3.3 (있다면) 리포지토리/서비스 단위 테스트

`tests/user/test_repository.py`, `tests/user/test_service.py`, `tests/product/test_repository.py`, `tests/product/test_service.py` 파일이 존재하지만 현재 테스트가 정의되어 있지 않다면 본 Plan의 완료 기준에서 제외한다. 만약 케이스가 정의되어 있다면 동일한 PASS 기준을 적용한다.

> **확인 명령**: `uv run pytest tests/user/test_repository.py tests/user/test_service.py tests/product/test_repository.py tests/product/test_service.py --collect-only -q`

---

## 4. 테스트 간 격리 검증

본 Plan은 단순 통과뿐 아니라 **테스트 간 상태 누수가 없음**도 검증해야 한다.

### 4.1 순서 무관성 검증

```bash
uv run pytest -v -p no:randomly  # 정렬된 순서
uv run pytest -v --randomly-seed=0xDEADBEEF  # 무작위 순서 (pytest-randomly 미설치시 생략)
```

> `pytest-randomly`는 현재 의존성에 없다. 본 검증은 선택사항이며, 도입 여부는 별도 결정.

### 4.2 격리 회귀 케이스 (수동)

다음 2개 시나리오를 수동으로 확인한다.

| # | 시나리오                                                          | 기대 결과                                                                 |
| - | ----------------------------------------------------------------- | ------------------------------------------------------------------------- |
| A | `test_create_user`를 두 번 연속 실행                              | 두 번 모두 PASS. 첫 실행의 사용자가 두 번째 실행에 영향 주지 않아야 함     |
| B | `test_get_user_by_id` 단독 실행                                   | PASS. 다른 테스트 fixture 의존 없이 시드 fixture만으로 동작해야 함         |

```bash
uv run pytest tests/user/test_router.py::test_create_user tests/user/test_router.py::test_create_user
uv run pytest tests/user/test_router.py::test_get_user_by_id
```

---

## 5. 회귀 방지 체크리스트

PR 머지 전 모두 확인.

- [ ] `git diff app/`가 비어있음 (프로덕션 코드 무변경)
- [ ] `uv run pytest` 18/18 PASS
- [ ] 단일 테스트 실행도 PASS (`tests/user/test_router.py::test_get_user_by_id`)
- [ ] `app.db` 파일이 테스트 실행 후 생성되지 않음 (인메모리 사용 증거)
- [ ] 테스트 실행 시간 합계 ≤ 10초 (인메모리 SQLite 기준 합리적 상한)
- [ ] 경고는 허용하되 신규 에러는 0건

---

## 6. 롤백 전략

- 본 작업은 `tests/conftest.py` 단일 파일 변경이 대부분이다.
- 작업 전 `git stash` 또는 별도 브랜치(`feature/test-architecture`)에서 진행.
- 문제 발생 시 `git checkout HEAD -- tests/conftest.py`로 즉시 원복 가능.

---

## 7. 후속 작업 (별도 이슈 권장)

본 Plan에서는 다루지 않지만 검토가 필요한 항목.

| # | 항목                                                                 | 권장 처리                                |
| - | -------------------------------------------------------------------- | ---------------------------------------- |
| 1 | `UserRole` enum vs 문자열 비교 불일치 (`app/api/dependencies.py:66`) | 별도 이슈로 enum 정합성 확보             |
| 2 | `pyproject.toml`의 `pytest-tornasync` / `pytest-trio` / `pytest-twisted` / `twisted` 의존성 실사용 여부 | 사용처가 없다면 제거                     |
| 3 | `passlib` deprecation 경고 (`crypt` 모듈)                            | `bcrypt` / `argon2-cffi`로 마이그레이션 검토 |
| 4 | `app/user/router.py:28`의 `.dict()` → `.model_dump()` 마이그레이션   | Pydantic v3 대비                          |
| 5 | `app/main.py` lifespan에서 `AUTO_CREATE_TABLES` 설정값 검증 강화     | 프로덕션 환경 안전성 점검                |

---

## 8. 참고

- 관련 PRD: [`[PRD]테스트_아키텍처_개선.md`](./[PRD]테스트_아키텍처_개선.md)
- 핵심 코드:
  - `app/di/containers.py:14` — Container 정의
  - `app/core/database.py:14` — `Base` 선언
  - `app/main.py:20` — lifespan
  - `tests/conftest.py` — 본 Plan의 주 수정 대상
