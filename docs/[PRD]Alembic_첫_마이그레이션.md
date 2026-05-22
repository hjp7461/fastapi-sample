# [PRD] Alembic 첫 마이그레이션 + AUTO_CREATE_TABLES 정리

| 항목 | 내용 |
| --- | --- |
| 상태 | 제안 (Draft) |
| 작성일 | 2026-05-23 |
| 출처 | PR #8 §7-#2 후속, [HANDOFF] §6 마스터 목록 |
| 분류 | 운영 인프라 (스키마 버저닝 도입) |
| 추정 작업량 | 중 (1.5~2 시간, env.py 재작성 + 첫 리비전 + AUTO_CREATE_TABLES 제거 + 청소 + 테스트) |

---

## 1. 배경

### 1.1 현재 스키마 관리 상태

- **alembic 설치/스캐폴드는 있지만 비활성** 상태.
  - `alembic.ini` 가 boilerplate 그대로 (sqlalchemy.url 만 채워짐).
  - `alembic/env.py` 의 `target_metadata = None` — autogenerate 비활성.
  - `alembic/versions/` 디렉토리 자체가 없음. 머지된 리비전 0건.
- 스키마는 `app/main.py` lifespan startup 의 `create_db_and_tables()` 가 만든다.

```python
# app/main.py
if settings.ENVIRONMENT == "development" and settings.AUTO_CREATE_TABLES:
    await create_db_and_tables()
```

```python
# app/core/database.py
async def create_db_and_tables() -> None:
    engine = Container.engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
```

문제는 다음과 같다.

1. **운영 환경 (`ENVIRONMENT != "development"`) 에서는 스키마 생성 수단이 0건.** 첫 배포가 막힌다.
2. **컬럼 추가/변경 시 자동 반영 불가.** `create_all` 은 기존 테이블이 있으면 스킵, 컬럼 추가는 안 함.
3. **AUTO_CREATE_TABLES 설정이 두 곳에 중복 정의** — `app/core/config.py` 와 `app/core/logging.py` 양쪽에 같은 라인이 존재. `logging.py` 자체는 어디서도 import 되지 않는 **죽은 모듈**이지만 설정만 우연히 일치해서 혼선을 만든다.
4. **다중 환경/팀 배포 시 스키마 정합성 보장 안 됨** — 누가 어느 컬럼을 어느 시점에 추가했는지 git 히스토리 외에는 추적 불가.

### 1.2 본 PR 의 위치

[HANDOFF] §6 의 명시 항목: "Alembic 첫 마이그레이션 + AUTO_CREATE_TABLES 정리 — PR #8 §7-#2, 운영 도입". 운영 배포 직전 마지막 인프라 작업.

---

## 2. 목적

1. **Alembic 을 단일 스키마 진실원으로 정착**시켜 운영/스테이징/로컬 환경에서 모두 같은 마이그레이션 명령으로 스키마를 구성/업그레이드한다.
2. 첫 리비전 (현재 모델 스키마 기준) 을 autogenerate 로 생성·머지·검증한다.
3. `AUTO_CREATE_TABLES` + `create_db_and_tables()` 의존을 제거하고, `app/main.py` lifespan 에서 startup 자동 생성 분기를 삭제한다.
4. `app/core/logging.py` 의 중복 정의 (실제 사용처 없는 죽은 코드) 를 청소한다.
5. `alembic/env.py` 가 `app.core.config.settings.DATABASE_URL` 을 단일 진실원으로 사용하도록 재배선 (alembic.ini 와 .env 가 서로 다른 URL 을 가질 위험 제거).
6. async DB 드라이버 (`aiosqlite`, `asyncpg`) 환경에서도 alembic 이 동작하는 비동기 env.py 패턴 정착.

---

## 3. 비목적

- 실제 운영 DB (Postgres 등) 로의 마이그레이션 — 별도 배포 작업. 본 PR 은 SQLite (개발) + 운영 호환 패턴까지만.
- 데이터 마이그레이션 (DML) — 본 PR 은 첫 DDL 리비전만.
- alembic 의 멀티 헤드/브랜치 전략 — 단일 브랜치만.
- CI 에서 마이그레이션 자동 적용 — 별도 후속 (운영 배포 파이프라인 때).
- 테스트 환경에서 alembic 사용 — 테스트는 인메모리 + StaticPool + `SQLModel.metadata.create_all` 직접 호출 유지 (속도/격리가 핵심).
- `Base = declarative_base()` 와 `SQLModel.metadata` 의 정합성 검토 — 본 프로젝트는 `SQLModel.metadata` 만 사용.
- Settings 의 `JSON_LOGS`, `LOG_LEVEL`, `LOG_FILE_PATH` 통합 — 별도 PR (loguru sink 설정 항목).

---

## 4. 성공 기준

- [ ] `alembic upgrade head` 가 빈 SQLite DB 에 두 테이블 (`users`, `products`) 을 정확히 생성한다.
- [ ] `alembic downgrade base` 가 두 테이블을 정확히 제거한다.
- [ ] `alembic upgrade head` → `alembic check` (또는 `alembic revision --autogenerate` 가 빈 diff 반환) 으로 모델 ↔ DB 정합성 검증.
- [ ] `app/main.py` lifespan 에서 `create_db_and_tables` 호출 분기 제거.
- [ ] `app/core/database.py::create_db_and_tables` 함수 자체 제거 (테스트 conftest 는 `SQLModel.metadata.create_all` 을 직접 호출하므로 무관).
- [ ] `app/core/config.py` 에서 `AUTO_CREATE_TABLES` 설정 라인 제거.
- [ ] `app/core/logging.py` 파일 자체 삭제 (어디서도 import 되지 않는 죽은 모듈).
- [ ] `alembic/env.py` 가 `app.core.config.settings.DATABASE_URL` 을 단일 진실원으로 사용 (alembic.ini 의 `sqlalchemy.url` 은 fallback/placeholder).
- [ ] async URL (`sqlite+aiosqlite://`) 에서 alembic 이 정상 동작.
- [ ] 신규 회귀 가드:
  - 첫 리비전 적용 후 두 테이블의 스키마 (컬럼명/타입/제약) 가 모델과 일치하는지 검증하는 통합 테스트 1건.
  - `alembic check` 가 빈 diff 를 반환하는지 (idempotency) 검증하는 sanity 테스트 1건.
- [ ] 기존 44 PASS 유지 (테스트 환경은 conftest 가 직접 create_all 하므로 영향 없음 기대).

---

## 5. 설계

### 5.1 디렉토리 구조 (변경 후)

```
alembic/
├── env.py                            # 재작성 (async + settings.DATABASE_URL)
├── README                            # 그대로
├── script.py.mako                    # 그대로 (boilerplate)
└── versions/
    └── 0001_initial_schema.py        # 신규 — autogenerate 결과
alembic.ini                           # sqlalchemy.url 은 .env 가 없을 때 fallback (env.py 가 override)
```

### 5.2 `alembic/env.py` 재작성

```python
"""Alembic env.py — async-friendly + settings 기반 URL.

target_metadata 는 SQLModel.metadata 를 사용한다. 모델 import 가 SQLModel 의
metadata 에 테이블을 등록하는 사이드 이펙트를 가지므로, 명시적으로 두 모델
모듈을 import 한다 (linter F401 무시).
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from alembic import context
from app.core.config import settings
from app.user import models as _user_models  # noqa: F401 — 메타데이터 등록
from app.product import models as _product_models  # noqa: F401 — 메타데이터 등록

config = context.config

# 단일 진실원: app.core.config.settings.DATABASE_URL
# alembic.ini 의 sqlalchemy.url 은 fallback/placeholder.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """offline 모드: URL 만으로 SQL 스크립트 생성."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """async 엔진으로 마이그레이션 실행."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### 5.3 첫 리비전 생성

```bash
# 빈 DB 상태에서
rm -f app.db
uv run alembic revision --autogenerate -m "initial schema (users, products)"
# → alembic/versions/0001_xxxxxxxx_initial_schema_users_products.py

# 검증
uv run alembic upgrade head
sqlite3 app.db ".schema users"
sqlite3 app.db ".schema products"
uv run alembic downgrade base
```

리비전 파일은 git에 커밋. 파일명에는 hash 가 포함되므로 정확한 이름은 생성 시점 결정.

### 5.4 `app/main.py` 변경

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 스키마는 alembic 으로 관리 (`uv run alembic upgrade head`).
    # startup 자동 create_all 분기는 제거됨.
    yield

    if container.db.initialized:
        scoped_session = container.db()
        await scoped_session.remove()
```

### 5.5 `app/core/database.py` 변경

`create_db_and_tables` 함수 자체 제거. `Base`, `get_db` 는 유지. SQLModel import 도 함수 안에서만 쓰였으니 함께 제거.

### 5.6 `app/core/config.py` 변경

```python
# 변경 전
AUTO_CREATE_TABLES: bool = os.getenv("AUTO_CREATE_TABLES", "true").lower() == "true"

# 변경 후 — 라인 제거
```

### 5.7 `app/core/logging.py` 삭제

미사용 모듈 (`grep -rn "from app.core.logging\|import app.core.logging" → 0건`). 파일 자체를 삭제한다.

### 5.8 `alembic.ini` 의 sqlalchemy.url 정책

`env.py` 가 `settings.DATABASE_URL` 로 override 하므로 `alembic.ini` 의 `sqlalchemy.url` 은 사실상 무시된다. 다만 alembic offline 모드의 placeholder 가 비면 안 되므로 그대로 두되, 코멘트로 "env.py 가 override 함" 을 명시한다.

```ini
# sqlalchemy.url: env.py 가 app.core.config.settings.DATABASE_URL 로 덮어쓴다.
# 이 값은 offline placeholder 일 뿐 — 실제로는 settings 가 단일 진실원.
sqlalchemy.url = sqlite+aiosqlite:///./app.db
```

### 5.9 README/운영 가이드

새 운영 명령:

| 작업 | 명령 |
| --- | --- |
| 최신 스키마로 업그레이드 | `uv run alembic upgrade head` |
| 한 단계 다운그레이드 | `uv run alembic downgrade -1` |
| 모델 변경 후 새 리비전 | `uv run alembic revision --autogenerate -m "<message>"` |
| 적용된 리비전 확인 | `uv run alembic current` |
| 리비전 히스토리 | `uv run alembic history` |

본 PR 에서는 별도 운영 가이드 문서는 만들지 않고 PR description 에만 정리 (별도 후속에서 docs/RUNBOOK.md 신설 가능).

### 5.10 테스트 정책

테스트 환경은 인메모리 + StaticPool + Container override 패턴 (PR #1) 을 유지. alembic 을 거치지 않는다 — 이유:

- 테스트는 매번 새로운 인메모리 DB 에서 격리 실행되므로 마이그레이션 단계가 의미 없음.
- alembic 을 거치면 테스트 setup 시간이 수십 ms ~ 수백 ms 증가 (44 케이스 × N → 누적 부담).
- 모델 ↔ 마이그레이션 정합성은 `alembic check` 또는 신규 회귀 가드 #2 가 보장.

### 5.11 신규 회귀 가드

```python
# tests/migration/test_alembic_schema.py (신규 모듈)
"""Alembic 마이그레이션 ↔ SQLModel 메타데이터 정합성 회귀."""
import asyncio
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel

from app.user import models as _user_models  # noqa: F401
from app.product import models as _product_models  # noqa: F401


@pytest.mark.asyncio
async def test_alembic_upgrade_creates_expected_tables(tmp_path: Path):
    """`alembic upgrade head` 후 users/products 테이블이 생성됨."""
    db_path = tmp_path / "alembic_test.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    # alembic 을 CLI 로 호출 — env.py 가 DATABASE_URL 을 settings 에서 읽으므로
    # subprocess 환경 변수로 override
    import subprocess
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        env={**__import__("os").environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    engine: AsyncEngine = create_async_engine(url)
    async with engine.connect() as conn:
        def _inspect(sync_conn):
            insp = inspect(sync_conn)
            return set(insp.get_table_names())
        tables = await conn.run_sync(_inspect)
    await engine.dispose()

    assert "users" in tables
    assert "products" in tables
    assert "alembic_version" in tables
```

**검토 필요**: subprocess 로 alembic 을 호출하면 테스트가 무거워진다 (uv run 오버헤드 ~수 초). 대안: Python API 로 alembic 호출.

```python
from alembic.config import Config
from alembic import command

alembic_cfg = Config("alembic.ini")
alembic_cfg.set_main_option("sqlalchemy.url", url)
command.upgrade(alembic_cfg, "head")
```

후자가 깔끔. 채택.

회귀 가드 2건:
1. **`test_alembic_upgrade_creates_expected_tables`** — upgrade head 후 두 테이블 존재.
2. **`test_alembic_metadata_matches_models`** — `alembic_version` 테이블의 head revision 이 모델 메타데이터와 일치하는지 (스키마 drift 가드).

테스트 위치: `tests/migration/test_alembic_schema.py` (신규 디렉토리).

---

## 6. 영향

| 영역 | 영향 |
| --- | --- |
| 운영 배포 흐름 | 첫 배포 시 `alembic upgrade head` 단계 필수화 (지금까지는 첫 요청 시 자동 생성 안 됨 → 운영에서 0 건 작동) |
| 개발 환경 | 첫 실행 시 `uv run alembic upgrade head` 한 번 필요. 이후 모델 변경 시 `revision --autogenerate` |
| `app/main.py` | lifespan startup 의 자동 create_all 분기 제거 |
| `app/core/database.py` | `create_db_and_tables` 함수 제거. `Base`, `get_db` 는 유지 |
| `app/core/config.py` | `AUTO_CREATE_TABLES` 설정 제거 |
| `app/core/logging.py` | 파일 자체 삭제 (미사용) |
| `alembic/env.py` | 재작성 — async + settings.DATABASE_URL 단일 진실원 |
| `alembic/versions/` | 첫 리비전 추가 |
| 테스트 환경 | **변화 없음** — conftest 가 직접 create_all |
| 외부 API / DB 스키마 | **변화 없음** — 첫 리비전은 현재 모델과 100% 동일 |

---

## 7. 리스크

| 리스크 | 가능성 | 대응 |
| --- | --- | --- |
| 운영 환경에서 첫 배포 시 alembic upgrade 누락 | 중 | PR description / README 에 명시. 별도 후속으로 CI/CD 파이프라인에 통합 |
| 첫 리비전 autogenerate 결과가 현재 스키마와 미세 불일치 (DateTime timezone, Enum 타입 등) | 중 | 생성 후 SQL 을 직접 검토. 회귀 가드 #1 이 실제 적용 결과 검증 |
| async engine 에서 alembic 의 일부 동작 (offline mode 등) 호환성 | 낮음 | offline mode 도 sync API. async 는 online 만. 첫 리비전 검증에서 양쪽 모두 확인 |
| `app/core/logging.py` 가 (현재는 미사용이지만) 외부 스크립트/도구에서 의존 중일 수도 | 매우 낮음 | grep + 동작 검증으로 0건 재확인. 발견 시 별도 PR 로 분리 |
| 테스트가 alembic.ini 경로 의존 (tests/ 디렉토리에서 실행 시 cwd 변화) | 낮음 | `Config(str(Path(__file__).parent.parent.parent / "alembic.ini"))` 절대 경로 사용 |
| settings.DATABASE_URL 이 sync URL (예: `sqlite:///`) 일 때 async_engine_from_config 실패 | 낮음 | 본 프로젝트는 `sqlite+aiosqlite://` 고정. 변경 시 별도 검토 |

---

## 8. 결정 사항 (확정)

- [x] alembic env.py 는 **async 패턴** 으로 재작성
- [x] env.py 는 `settings.DATABASE_URL` 을 단일 진실원으로 사용 (`config.set_main_option`)
- [x] alembic.ini 의 `sqlalchemy.url` 은 placeholder 로 유지하되 코멘트로 명시
- [x] `target_metadata = SQLModel.metadata` (모델 import 명시)
- [x] 첫 리비전은 autogenerate, 파일명에 hash + slug
- [x] **AUTO_CREATE_TABLES 설정 완전 제거** — config.py 라인 삭제, main.py 분기 삭제, create_db_and_tables 함수 삭제
- [x] **app/core/logging.py 파일 자체 삭제** (미사용 모듈 청소)
- [x] 테스트 환경은 alembic 거치지 않음 — 인메모리 conftest 패턴 유지
- [x] 회귀 가드 2건: upgrade head 후 테이블 존재 + (선택) metadata 정합성
- [x] 운영 가이드는 PR description 에만, 별도 RUNBOOK.md 는 후속

---

## 9. 참고

- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`
- `app/main.py`, `app/core/database.py`, `app/core/config.py`, `app/core/logging.py`
- `app/user/models.py`, `app/product/models.py`
- `tests/conftest.py` (테스트 격리 패턴)
- Alembic docs: https://alembic.sqlalchemy.org
- SQLModel + Alembic 가이드: https://sqlmodel.tiangolo.com/tutorial/code-structure/
