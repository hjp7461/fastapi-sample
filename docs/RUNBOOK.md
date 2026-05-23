# RUNBOOK — fastapi-sample 운영 가이드

운영자/컨트리뷰터가 일상 운영 (배포, 스키마 변경, 롤백) 시 참고하는 단일 핸드북.
모든 명령은 프로젝트 루트 (`/Users/connor/biz/fastapi-sample` 또는 동등 경로) 에서 실행한다.

---

## 1. 개요

- 패키지 관리: **uv** (`uv sync --all-extras`, `uv run <cmd>`)
- 스키마 관리: **alembic** (단일 진실원, PR #14 이후)
- 환경 파일: `.env` (load_dotenv 로 자동 로드)
- 현재 head 리비전: `ab265552a4a2` (initial schema — users, products)

배포 흐름 핵심: **항상 `uv run alembic upgrade head` 후 앱 기동**.

---

## 2. 환경 변수 매트릭스

`app/core/config.py::Settings` 가 단일 진실원.

| 변수 | 기본값 | 운영 권장값 | 설명 |
| --- | --- | --- | --- |
| `ENVIRONMENT` | `development` | `production` | 환경 분기. 현재는 정보용 (lifespan 자동 분기 제거됨) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | `postgresql+asyncpg://user:pass@host/db` | DB 연결 문자열. async drivers 필수 |
| `DB_ECHO` | `false` | `false` | SQL echo. 디버깅 시에만 `true` |
| `SECRET_KEY` | placeholder | **반드시 변경** (운영은 secret 매니저) | JWT 서명 키 |
| `ALGORITHM` | `HS256` | `HS256` | JWT 알고리즘 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | 정책에 맞게 | 토큰 만료 (분) |
| `BCRYPT_ROUNDS` | `12` | `12`~`13` (운영), `4` (테스트만) | bcrypt cost. 운영에서는 ≥12, 다운그레이드는 자동 차단 (PR #13) |

**참고**: `AUTO_CREATE_TABLES` 는 PR #14 에서 폐기됨. alembic 으로 대체.

---

## 3. 초기 배포

```bash
# 1. 환경 변수 설정
cp .env.example .env  # 또는 secret 매니저
# .env 의 DATABASE_URL, SECRET_KEY 등 채움

# 2. 의존성 설치
uv sync --all-extras

# 3. DB 스키마 적용 (필수)
uv run alembic upgrade head

# 4. 검증
uv run alembic current
# 기대 출력: ab265552a4a2 (head)

# 5. 회귀 테스트 (배포 전 권장)
uv run pytest

# 6. 앱 기동
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

운영 환경에서는 `--workers <N>`, `--reload` 비활성 등 추가 옵션 검토.

---

## 4. 스키마 변경

```bash
# 1. 모델 수정
#    - app/user/models.py 또는 app/product/models.py
#    - 새 모델 추가 시 alembic/env.py 의 import 도 갱신

# 2. 리비전 자동 생성
uv run alembic revision --autogenerate -m "<변경 요약>"
# alembic/versions/<hash>_<slug>.py 가 생성됨

# 3. 생성 리비전 검토 (필수)
#    - upgrade() / downgrade() 가 의도와 일치
#    - sqlmodel.sql.sqltypes.AutoString 등이 정상 처리
#    - 인덱스/제약/Enum 누락 없는지

# 4. 로컬 적용 + 회귀
uv run alembic upgrade head
uv run pytest

# 5. 커밋 (리비전 파일도 포함) + PR
git add alembic/versions/<hash>_<slug>.py app/<domain>/models.py
git commit -m "feat(schema): <변경 요약>"
```

**중요**: 새 모델 모듈 추가 시 `alembic/env.py` 의 메타데이터 등록 import 도 갱신 필수.

```python
# alembic/env.py
from app.<new_domain> import models as _new_models  # noqa: F401 — 메타데이터 등록
```

---

## 5. 일상 명령 매트릭스

| 작업 | 명령 |
| --- | --- |
| 최신 스키마 적용 | `uv run alembic upgrade head` |
| 한 단계 다운그레이드 | `uv run alembic downgrade -1` |
| 특정 리비전으로 | `uv run alembic downgrade <rev_id>` |
| 처음으로 (개발만) | `uv run alembic downgrade base` |
| 현재 리비전 확인 | `uv run alembic current` |
| 히스토리 | `uv run alembic history --verbose` |
| 모든 head 확인 | `uv run alembic heads` |
| 새 리비전 (자동) | `uv run alembic revision --autogenerate -m "<msg>"` |
| 새 리비전 (수동) | `uv run alembic revision -m "<msg>"` |
| 특정 리비전 상세 | `uv run alembic show <rev_id>` |

---

## 6. 롤백

### 6.1 개발 환경

```bash
# 단일 리비전 롤백
uv run alembic downgrade -1

# 전체 초기화
uv run alembic downgrade base

# 또는 DB 파일 삭제 후 재 upgrade
rm -f app.db
uv run alembic upgrade head
```

### 6.2 운영 환경 (데이터 있는 상태)

**경고**: `downgrade` 가 컬럼/테이블 삭제를 동반하면 **데이터 손실**.

권장 순서:

1. **백업**: `pg_dump <db> > backup.sql` (Postgres) 또는 동등한 작업
2. 비상 시: forward-only 패턴 — 새 revision 으로 정정 (이전 revision 의 변경을 되돌리는 새 revision)
3. 정말 downgrade 가 필요하면:
   - 영향 받는 테이블 / 컬럼 / 데이터 사전 확인
   - 백업 후 `uv run alembic downgrade <rev_id>`
   - 즉시 검증 (`alembic current`, 주요 쿼리 sanity)
4. 복구 불가 시: 백업 restore 후 안정 시점으로 재 upgrade

---

## 7. Postgres 이전 체크리스트

현재 프로젝트는 SQLite (개발) 기준. 운영 Postgres 이전 시 다음 항목 점검.

- [ ] `DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db`
- [ ] `asyncpg` 의존성 추가 (`uv add asyncpg`)
- [ ] 새 환경에서 `uv run alembic upgrade head` 동작 검증
- [ ] 기존 SQLite 데이터 마이그레이션 (필요 시 수동 SQL/ETL)
- [ ] `tests/core/test_datetime_handling.py` 의 SQLite tzinfo 유실 노트가 Postgres 에서는 해소됨 (native `timestamptz`)
- [ ] `tests/migration/test_alembic_schema.py` 는 SQLite 만 검증 — Postgres 전용 통합 테스트 권장
- [ ] Connection pool 설정 검토 (`pool_size`, `max_overflow`, `pool_pre_ping`)
- [ ] Postgres-specific 인덱스/제약 (GIN, partial index 등) 활용 여부 검토

---

## 8. 트러블슈팅

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| `revision --autogenerate` 가 빈 upgrade/downgrade 생성 | 모델 import 누락 → 메타데이터 미반영 | `alembic/env.py` 의 `_user_models`, `_product_models` import 확인 |
| 리비전 적용 시 `NameError: name 'sqlmodel' is not defined` | `alembic/script.py.mako` 의 `import sqlmodel` 누락 | mako 템플릿 확인 (PR #14 에서 보강) |
| `Multiple heads detected` | 여러 브랜치에서 동시에 revision 생성 | `uv run alembic merge <h1> <h2> -m "merge heads"` |
| `Can't locate revision identified by '<rev>'` | git pull 시 리비전 파일 충돌 또는 누락 | `uv run alembic history` 로 확인, 정상 head 로 reset 또는 파일 동기화 |
| 테스트가 `no such table: users` 로 실패 | conftest override 시점에 production engine 사용 | conftest 의 `container_override` fixture 확인 (autouse=True) |
| 마이그레이션이 production engine 으로 동작 | `alembic.ini` 의 sqlalchemy.url 비어있는데 env.py 의 settings 미반영 | `app/core/config.py::settings.DATABASE_URL` 확인, env.py 의 `config.set_main_option` 로직 확인 |
| `Provide[Container.xxx]` 가 그대로 의존성에 주입됨 | dependency-injector 4.46.0 + FastAPI 호환성 문제 | `Depends(get_xxx_service)` named helper 사용 (PR #17, `app/di/providers.py`) |

---

## 9. 참고 문서 / 링크

- 마이그레이션 도입 배경: `docs/[PRD]Alembic_첫_마이그레이션.md`
- 운영 핵심 정책 후속:
  - bcrypt 라운드: `docs/[PRD]bcrypt_라운드_환경별_설정.md`, `docs/[PRD]라운드_다운그레이드_차단.md`
  - PII 마스킹: `docs/[PRD]UserResponse_PII_마스킹.md`
- 세션 이어가기: `docs/[HANDOFF]세션_이어가기.md` (로컬 전용)
- Alembic 공식: https://alembic.sqlalchemy.org
- SQLAlchemy async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- dependency-injector: https://python-dependency-injector.ets-labs.org/

---

> 이 문서가 stale 됐다고 느껴지면 즉시 PR 로 갱신해주세요. 운영 핸드북은 **항상 최신 상태**가 가치의 핵심입니다.
