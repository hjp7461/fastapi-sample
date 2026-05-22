# [PLAN] Alembic 첫 마이그레이션 + AUTO_CREATE_TABLES 정리

| 항목 | 내용 |
| --- | --- |
| 연관 PRD | `docs/[PRD]Alembic_첫_마이그레이션.md` |
| 브랜치 | `feature/alembic-initial-migration` |
| 추정 작업량 | 중 (1.5~2 시간) |
| 채택 전략 | async env.py + 첫 autogenerate 리비전 + AUTO_CREATE_TABLES/logging.py 청소 + 회귀 가드 |

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 최신, 44 PASS 기준선 확인
- [ ] `uv run alembic --version` 호출 성공 확인 (alembic 1.10.4+)
- [ ] `app/core/logging.py` 가 어디서도 import 되지 않는지 grep 재확인
- [ ] 새 브랜치 `feature/alembic-initial-migration` 생성

---

## 1. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout -b feature/alembic-initial-migration
```

### Step 2 — `alembic/env.py` 재작성

PRD §5.2 코드 그대로 적용 (async + `settings.DATABASE_URL` 단일 진실원, SQLModel.metadata 등록).

**검증**

```bash
uv run alembic current
# 기대: 아직 빈 DB 면 (empty), 디렉토리 잘못되면 ImportError
```

### Step 3 — `alembic.ini` 코멘트 추가

`sqlalchemy.url` 줄 위에 "env.py 가 settings 로 override 함" 코멘트 추가. URL 값 자체는 placeholder 로 유지.

### Step 4 — 첫 리비전 autogenerate

```bash
# 기존 dev DB 파일 정리 (autogenerate 가 빈 DB 와 모델 metadata 를 비교하도록)
rm -f app.db

# autogenerate
uv run alembic revision --autogenerate -m "initial schema (users, products)"

# 생성된 파일 검토 — 두 테이블 (users, products) + Enum 타입 + DateTime(timezone=True) 확인
ls alembic/versions/
cat alembic/versions/*_initial_schema*.py
```

생성된 리비전 파일에서 검토할 포인트:
- `users` 테이블 (id, email, username, hashed_password, first_name, last_name, role[Enum], is_active, created_at, updated_at)
- `products` 테이블 (id, name, description, price[Numeric(10,2)], category[Enum], inventory, is_active, created_at, updated_at)
- `created_at`/`updated_at` 의 `DateTime(timezone=True)`
- 유니크/인덱스: email, username (users), name (products)

**검증**

```bash
uv run alembic upgrade head
uv run alembic current
sqlite3 app.db ".schema users"
sqlite3 app.db ".schema products"
uv run alembic downgrade base
uv run alembic upgrade head
# 두 번째 upgrade 도 멱등적이어야 함
```

### Step 5 — `app/main.py` lifespan 정리

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 스키마는 alembic 으로 관리한다 (`uv run alembic upgrade head`).
    yield

    if container.db.initialized:
        scoped_session = container.db()
        await scoped_session.remove()
```

- `create_db_and_tables` import 제거
- startup 분기 (development + AUTO_CREATE_TABLES) 제거

### Step 6 — `app/core/database.py` 정리

```python
# 변경 전 — create_db_and_tables 함수 정의 (28-37 라인)
# 변경 후 — 함수 제거. Base, get_db 만 남김.
```

SQLModel import 도 함수 내부에만 있었으므로 함께 정리.

### Step 7 — `app/core/config.py` 정리

```python
# AUTO_CREATE_TABLES 라인 (35) 제거
```

### Step 8 — `app/core/logging.py` 삭제

```bash
git rm app/core/logging.py
```

`grep -rn "from app.core.logging\|import app.core.logging"` 결과가 0건임을 사전에 확인했음.

### Step 9 — 회귀 가드 추가 (`tests/migration/test_alembic_schema.py`)

PRD §5.11 의 Python API 패턴 채택.

```python
"""Alembic 마이그레이션 ↔ SQLModel 메타데이터 정합성 회귀."""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[2]


def _make_alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


def test_alembic_upgrade_creates_expected_tables(tmp_path: Path):
    """`alembic upgrade head` 후 users/products/alembic_version 테이블 생성."""
    db_path = tmp_path / "alembic_upgrade.db"
    # alembic 의 online 모드는 async 엔진을 쓰지만, 검증은 sync 로 충분.
    # async URL 을 그대로 넘기되 검증만 sync sqlite 로.
    async_url = f"sqlite+aiosqlite:///{db_path}"
    cfg = _make_alembic_config(async_url)

    command.upgrade(cfg, "head")

    sync_engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(sync_engine)
    tables = set(insp.get_table_names())
    sync_engine.dispose()

    assert "users" in tables
    assert "products" in tables
    assert "alembic_version" in tables


def test_alembic_downgrade_removes_tables(tmp_path: Path):
    """`alembic downgrade base` 후 users/products 가 제거됨."""
    db_path = tmp_path / "alembic_downgrade.db"
    async_url = f"sqlite+aiosqlite:///{db_path}"
    cfg = _make_alembic_config(async_url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    sync_engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(sync_engine)
    tables = set(insp.get_table_names())
    sync_engine.dispose()

    assert "users" not in tables
    assert "products" not in tables
    # alembic_version 은 보통 남아있을 수 있고, 그건 alembic 표준 동작
```

신규 디렉토리 `tests/migration/` (회귀 가드 누적용).

**검증**

```bash
uv run pytest tests/migration/ -v
```

### Step 10 — 전체 회귀

```bash
uv run pytest
# 기대: 44 + 2 = 46 PASS, warning 0
```

테스트 환경은 alembic 거치지 않으므로 기존 44 케이스는 영향 없음.

### Step 11 — 커밋 + 푸시 + PR

```bash
git add -f docs/'[PRD]Alembic_첫_마이그레이션.md' docs/'[PLAN]Alembic_첫_마이그레이션.md'
git add alembic/env.py alembic.ini alembic/versions/
git add app/main.py app/core/database.py app/core/config.py
git rm app/core/logging.py
git add tests/migration/test_alembic_schema.py
git status
git commit -m "$(cat <<'EOF'
feat(infra): Alembic 첫 마이그레이션 + AUTO_CREATE_TABLES 청소

운영 도입 직전 마지막 인프라 작업. 스키마 관리를 alembic 단일 진실원으로
정착시키고, 죽은 코드/중복 설정을 정리한다.

- alembic/env.py: async + settings.DATABASE_URL 단일 진실원으로 재작성
- alembic/versions/: 첫 리비전 (users, products) autogenerate 생성
- app/main.py: lifespan startup 의 create_all 분기 제거
- app/core/database.py: create_db_and_tables 함수 제거 (alembic 으로 대체)
- app/core/config.py: AUTO_CREATE_TABLES 설정 라인 제거
- app/core/logging.py: 파일 자체 삭제 (미사용 + AUTO_CREATE_TABLES 중복 정의)
- tests/migration/test_alembic_schema.py: upgrade/downgrade 회귀 가드 +2

테스트 환경 (인메모리 conftest) 은 영향 없음.
외부 API/DB 스키마 변화 없음 — 첫 리비전은 현재 모델 100% 반영.

운영 배포 흐름: `uv run alembic upgrade head` 가 첫 배포에 필수가 됨.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push -u origin feature/alembic-initial-migration
gh pr create ...
```

---

## 2. 산출물 체크리스트

| 산출물 | 위치 | 상태 |
| --- | --- | --- |
| PRD | `docs/[PRD]Alembic_첫_마이그레이션.md` | ✅ |
| PLAN | `docs/[PLAN]Alembic_첫_마이그레이션.md` | ✅ |
| env.py 재작성 | `alembic/env.py` | ⬜ |
| alembic.ini 코멘트 | `alembic.ini` | ⬜ |
| 첫 리비전 | `alembic/versions/0001_*.py` | ⬜ |
| main.py lifespan 정리 | `app/main.py` | ⬜ |
| database.py 함수 제거 | `app/core/database.py` | ⬜ |
| config.py 설정 제거 | `app/core/config.py` | ⬜ |
| logging.py 삭제 | `app/core/logging.py` | ⬜ |
| 회귀 가드 +2 | `tests/migration/test_alembic_schema.py` | ⬜ |

---

## 3. 신규 테스트 케이스

| # | 위치 | 케이스 |
| --- | --- | --- |
| 1 | `tests/migration/test_alembic_schema.py::test_alembic_upgrade_creates_expected_tables` | upgrade head 후 users/products/alembic_version 생성 검증 |
| 2 | `tests/migration/test_alembic_schema.py::test_alembic_downgrade_removes_tables` | downgrade base 후 users/products 제거 검증 |

---

## 4. 회귀 방지

| 회귀 시나리오 | 가드 |
| --- | --- |
| 마이그레이션이 모델과 어긋남 (테이블 누락/오타) | 신규 케이스 #1 |
| downgrade 가 깨짐 (한쪽 방향만 동작) | 신규 케이스 #2 |
| 운영 배포 시 startup create_all 누락 인지 못함 | PR description / commit message 명시 + 후속 CI 통합 |
| 테스트 환경에 alembic 사이드 이펙트 침투 | 회귀 케이스가 `tmp_path` 만 사용. 인메모리 conftest 그대로 |

---

## 5. 롤백

본 변경은 (테스트 + 첫 머지 후 운영 적용 전이라면) 단일 머지 revert 로 충분.

```bash
git revert <merge-commit-sha>
```

운영 배포 후 데이터가 들어간 뒤 롤백이 필요하다면 `alembic downgrade base` 가 데이터를 삭제하므로 별도 백업/복구 필요.

---

## 6. 후속 작업 후보

- CI/CD 파이프라인에 `alembic upgrade head` 단계 통합
- `docs/RUNBOOK.md` — 운영 마이그레이션 가이드 (생성/배포/롤백 시나리오)
- Postgres 환경 검증 (현재는 SQLite 만)
- 데이터 마이그레이션 (DML) 패턴 가이드 (필요 시점에)

---

## 7. 참고

- PRD: `docs/[PRD]Alembic_첫_마이그레이션.md`
- Alembic docs (async): https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`
- `tests/conftest.py` (테스트 격리 — alembic 무관)
