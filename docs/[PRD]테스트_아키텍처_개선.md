# 테스트 아키텍처 개선 PRD

| 항목      | 내용                                          |
| --------- | --------------------------------------------- |
| 작성일    | 2026-05-22                                    |
| 작성자    | conner                                        |
| 상태      | 제안 (Draft)                                  |
| 대상 범위 | `tests/` 전체 (conftest 및 라우터/리포지토리/서비스 테스트) |
| 관련 이슈 | 18개 테스트 중 17개가 `OperationalError`로 실패 |

---

## 1. 배경

본 프로젝트는 클린 아키텍처와 모듈 기능 기반 구조를 따르며, 다음의 핵심 룰을 가진다.

- **모든 데이터 액세스 계층(repository) / 비즈니스 계층(service) / API 계층(router)은 비동기(`async`)로 동작한다.**
- **의존성은 `dependency_injector.Container`를 통해 주입한다.** (싱글톤 `engine`, 팩토리 `session_factory`, 리소스 `async_scoped_session`)
- 세션 스코프는 `asyncio.current_task`를 기준으로 한 `async_scoped_session`이며, 동일 요청 컨텍스트 내 동일 세션을 공유한다.

현재 `tests/conftest.py`는 별도의 인메모리 SQLite 엔진을 만들어 테이블을 생성하지만, **실제 API 호출은 `Container`의 싱글톤 엔진(= `settings.DATABASE_URL`)을 사용**한다. 두 엔진이 분리되어 있어 라우터를 통과하는 모든 테스트는 `no such table: users` 오류로 실패한다.

또한 다음의 부수적 문제가 확인되었다.

1. `pyproject.toml`의 `[cltool.pytest.ini_options]` 오타 → **수정 완료**
2. `tests/conftest.py`의 `AsyncClient`가 ASGI 트랜스포트 없이 생성됨 → **수정 완료** (`httpx.ASGITransport`)
3. session-scoped 비동기 fixture가 function-scoped 이벤트 루프와 충돌 → **수정 완료** (function 스코프 통일)
4. **(남은 문제)** `Container` 엔진/세션이 테스트 DB로 교체되지 않음 → 본 PRD의 대상
5. **(남은 문제)** ASGI lifespan이 `httpx.ASGITransport`에서 실행되지 않아 `create_db_and_tables()`가 호출되지 않음 → 본 PRD의 대상

---

## 2. 목적

- `tests/` 디렉토리의 모든 테스트(라우터 통합 테스트 + 리포지토리/서비스 단위 테스트)가 안정적으로 통과한다.
- 프로덕션 코드를 수정하지 않고 테스트 인프라(`conftest.py`)만으로 격리를 달성한다.
- 비동기 + DI 룰을 깨지 않는다. 즉, 동기 세션이나 직접 인스턴스화로 우회하지 않는다.

### 비목적(Non-goals)

- 프로덕션 `Container`/`database.py`/`main.py` 코드 리팩토링 (필요 최소 외).
- 새로운 테스트 케이스 추가. (본 PRD는 기존 테스트의 정상화에 집중)
- E2E 테스트, 성능 테스트 도입.

---

## 3. 성공 기준

| 지표                                                    | 목표값                  |
| ------------------------------------------------------- | ----------------------- |
| `uv run pytest` 총 통과율                               | 18/18 (100%)            |
| 테스트 간 데이터 격리 (한 테스트의 상태가 다음 테스트에 누출되지 않음) | 100%                    |
| `Container` override가 테스트 종료 시 원복되는지        | 100%                    |
| 비동기 코드 경로(`async def`) 우회 여부                 | 0건 (모두 `async` 유지) |
| 단일 테스트 평균 실행 시간                              | ≤ 1초 (인메모리 SQLite 기준) |

---

## 4. 영향 받는 파일

| 파일                          | 변경 종류                  | 비고                                                       |
| ----------------------------- | -------------------------- | ---------------------------------------------------------- |
| `tests/conftest.py`           | 거의 전면 재작성           | Container override, 세션 정리, 의존성 override 추가         |
| `tests/pytest.ini`            | 미세 조정 (선택)           | `log_cli` 끄기로 테스트 출력 정리 (선택사항)                |
| `pyproject.toml`              | `test` extras에 `asgi-lifespan` 추가 (선택) | lifespan 통합 시에만 필요. 본 PRD는 직접 호출 권장          |
| `tests/user/test_router.py` 등 | 변경 없음                  | fixture 인터페이스(`client`, `test_user` 등)는 유지         |

> 프로덕션 코드(`app/**`)는 본 PRD 범위에서 수정하지 않는다.

---

## 5. 설계

### 5.1 DB 엔진 전략

**선택: 단일 커넥션 + `StaticPool`을 사용하는 인메모리 SQLite**

```python
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
    echo=False,
    future=True,
)
```

**이유**

- `:memory:` SQLite는 커넥션마다 별도 DB를 갖는다. `StaticPool`로 단일 커넥션을 공유해 여러 세션이 동일 DB를 보도록 강제한다.
- 파일 DB 대비 빠르고, 테스트 간 자연스러운 격리 (엔진 폐기 시 데이터도 사라짐).
- 프로덕션 `aiosqlite` 드라이버를 그대로 사용하므로 SQL 방언 차이 없음.

### 5.2 Container 의존성 override

`Container`는 클래스 기반 `DeclarativeContainer`이며, 실행 중 `app.container = Container()` 인스턴스가 `app.di.containers.Container`(클래스) 자체와 동일하게 동작한다(`providers.Resource` 등이 클래스 속성으로 관리됨).

**전략: `Container.engine` / `Container.session_factory` 두 가지를 `override()` 한다.**

```python
from dependency_injector import providers
from app.di.containers import Container

# 엔진과 세션 팩토리를 테스트용으로 교체
Container.engine.override(providers.Singleton(lambda: test_engine))
Container.session_factory.override(
    providers.Factory(
        sessionmaker,
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
)
```

`Container.db`(=`providers.Resource(async_scoped_session, ...)`)는 그대로 두되, 내부적으로 새 `session_factory`를 참조한다. `Container.user_repository` 등 하위 프로바이더는 자동으로 새 세션을 받는다.

**원복**: 각 테스트(또는 세션) 종료 시 `Container.engine.reset_override()`, `Container.session_factory.reset_override()` 호출.

### 5.3 테이블 생성 및 lifespan

**선택: lifespan을 우회하고 conftest에서 명시적으로 `metadata.create_all`을 호출한다.**

- `httpx.ASGITransport`는 lifespan을 실행하지 않는다. 외부 의존성(`asgi-lifespan`)을 도입할 수도 있으나, 본 프로젝트의 lifespan 로직은 `create_db_and_tables()` 호출과 종료 시 세션 제거뿐이라 직접 처리하는 편이 더 명시적이다.
- conftest에서 `Base.metadata.create_all` + `SQLModel.metadata.create_all`을 동일 트랜잭션으로 실행한다.
- 종료 시 `async_scoped_session.remove()`로 스코프 정리 + `engine.dispose()`로 커넥션 풀 정리.

### 5.4 세션 스코프와 정리

`async_scoped_session(scopefunc=asyncio.current_task)`는 각 비동기 태스크마다 별도 세션을 갖는다. **테스트 함수 본문과 라우터 핸들러는 서로 다른 태스크**일 가능성이 높으므로:

- conftest의 `db_session` fixture는 **테스트 데이터 준비(seeding)** 용도로만 사용한다 (`test_user`, `admin_user`, `test_product`).
- API 호출(`client.post(...)`)이 도는 동안에는 라우터가 받는 세션이 별개일 수 있다.
- **두 세션이 동일 DB를 보도록**, 5.1의 `StaticPool` 단일 커넥션 전략이 필수다.
- 테스트 함수 teardown에서 `scoped_session.remove()` 호출 → 다음 테스트에 세션 누출 방지.

### 5.5 픽스처 설계 (재작성 후 청사진)

```
session 스코프 (테스트 전체 1회)
  - 없음 (function 스코프로 통일)

function 스코프 (각 테스트마다)
  engine            : StaticPool 인메모리 엔진 생성 + 테이블 생성, teardown에서 dispose
  container_override: Container.engine/session_factory를 위 엔진으로 override, teardown에서 reset
  session_factory   : test_engine 바인딩된 AsyncSession 팩토리
  db_session        : 시드 데이터 생성용 단일 세션
  app               : fastapi_app 참조 (override는 container_override가 담당)
  client            : ASGITransport로 감싼 AsyncClient, dependency_overrides 초기화
  test_user, admin_user, test_product : 도메인 시드 데이터
  auth_headers, admin_auth_headers    : 토큰 발급 후 헤더 반환
```

> `container_override`는 `engine` fixture가 만든 엔진을 받아 Container 프로바이더를 교체하고, 테스트 종료 시 반드시 `reset_override` 한다.

### 5.6 인증 픽스처

기존 `auth_headers` / `admin_auth_headers`는 `/api/v1/users/token` 엔드포인트를 호출해 토큰을 얻는다. **DB가 정상 격리되면 그대로 동작**한다. 단, `admin_user` fixture가 `role="admin"` 문자열을 쓰는데 `app/api/dependencies.py:66`도 `"admin"` 문자열과 비교하므로 호환된다. (도메인은 `UserRole.ADMIN` enum을 사용하지만 DB에는 문자열로 저장됨 — 추후 정합성 점검 필요, 본 PRD 범위는 아님.)

### 5.7 의존성 주입 우회 옵션 (대안 검토)

`app.dependency_overrides`로 FastAPI 레벨에서 `get_db`/`get_current_user`를 교체하는 방식도 가능하다. 그러나:

- 본 프로젝트는 라우터가 `Container.user_service()`를 직접 호출하는 패턴(`Depends(lambda: Container.user_service())`)을 사용한다.
- 따라서 `dependency_overrides`만으로는 `Container`가 만드는 세션을 교체할 수 없다.
- **결론: Container 레벨 override가 정답이다.**

---

## 6. 구현 계획 (작업 순서)

1. **conftest 재작성** (`tests/conftest.py`)
   1. `StaticPool` 인메모리 엔진 fixture 작성
   2. `Container.engine` / `Container.session_factory` override fixture 작성 (autouse 또는 명시 의존)
   3. `Base.metadata.create_all` + `SQLModel.metadata.create_all` 실행
   4. `AsyncClient(transport=ASGITransport(app=app))` 유지
   5. 기존 시드 픽스처(`test_user`, `admin_user`, `test_product`)는 새 `db_session`에 맞게 인터페이스 유지
   6. teardown: `scoped_session.remove()` → `engine.dispose()` → `reset_override()`
2. **로컬 검증**: `uv run pytest -x` → 첫 실패만 확인하며 1개씩 정상화
3. **전체 실행**: `uv run pytest --cov=app` → 18/18 + 커버리지 리포트 확인
4. **선택 사항**: `pytest.ini`의 `log_cli` 정리, `pyproject.toml`의 `pytest-tornasync`/`pytest-trio`/`pytest-twisted`/`twisted` 의존성 실제 사용 여부 재검토 (사용처가 없다면 제거 후보)

---

## 7. 리스크 & 미해결 이슈

| # | 리스크                                                                                                | 완화책                                                                       |
| - | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 1 | `async_scoped_session`의 스코프 키(`asyncio.current_task`)가 테스트 본문과 라우터 핸들러에서 달라져 두 세션이 동일 DB를 보지 못함 | `StaticPool` 단일 커넥션으로 강제 공유. 그래도 SQLite 트랜잭션 격리 수준에 주의 |
| 2 | `Container.db`가 `providers.Resource`라 초기화/해제 타이밍이 lifespan에 묶여 있음                      | 테스트마다 `Container.db.shutdown()` 호출 또는 새 인스턴스로 reset            |
| 3 | `UserRole` enum vs 문자열 불일치 (도메인은 enum, 라우터 권한 체크는 문자열 비교)                       | 본 PRD 범위 밖. 별도 이슈 등록 권장                                          |
| 4 | `pyproject.toml`의 `pytest-tornasync` / `pytest-trio` / `pytest-twisted` 의존성이 실제로 어디서도 사용되지 않음 | 본 PRD 범위 밖. asyncio 모드로 통일이 검증되면 제거 검토                     |
| 5 | `passlib`의 `crypt` 모듈 deprecation 경고 (Python 3.13+에서 제거 예정)                                 | 현재 사용하는 3.12.12에서는 영향 없음. 향후 `passlib` → `argon2-cffi`/`bcrypt` 마이그레이션 검토 |

---

## 8. 참고 자료

- pytest-asyncio 0.26.0 changelog 및 `asyncio_default_fixture_loop_scope`
- SQLAlchemy `StaticPool` 문서: https://docs.sqlalchemy.org/en/20/core/pooling.html#sqlalchemy.pool.StaticPool
- `dependency_injector` provider override: https://python-dependency-injector.ets-labs.org/providers/overriding.html
- httpx `ASGITransport`: https://www.python-httpx.org/async/#calling-into-python-web-apps
- 본 저장소 파일:
  - `app/di/containers.py` — Container 정의
  - `app/core/database.py` — `Base`, `get_db`, `create_db_and_tables`
  - `app/main.py` — lifespan 및 `app.container` 바인딩
  - `tests/conftest.py` — 현재 픽스처
