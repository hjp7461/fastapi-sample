# [PRD] `docs/RUNBOOK.md` — 운영 마이그레이션 가이드

| 항목 | 내용 |
| --- | --- |
| 상태 | 제안 (Draft) |
| 작성일 | 2026-05-23 |
| 출처 | PR #14 §7 후속, [HANDOFF] §6 마스터 목록 |
| 분류 | 문서 (운영 핸드북) |
| 추정 작업량 | 소~중 (1~1.5 시간, RUNBOOK.md 신규) |

---

## 1. 배경

PR #14 (Alembic 첫 마이그레이션) 머지 후 운영 흐름이 다음과 같이 변경됐다.

- 첫 배포 시 `uv run alembic upgrade head` 가 **필수**
- 스키마 변경 시 `revision --autogenerate` → 리뷰 → upgrade 패턴
- AUTO_CREATE_TABLES / `create_db_and_tables` 자동 분기 제거

이 운영 절차가 현재 PR description 과 PRD/PLAN 문서에 흩어져있다. 운영자 (또는 새 컨트리뷰터) 가 한 곳에서 참조할 수 있는 RUNBOOK 이 필요하다.

또한 docs/ 디렉토리에는 PRD/PLAN/HANDOFF 만 있고 **운영 핸드북 (RUNBOOK) 형식의 문서가 부재**. 본 PR 이 그 빈자리를 채운다.

---

## 2. 목적

1. **운영자가 처음 보더라도 안전하게 마이그레이션 수행 가능** 한 매트릭스 / 명령 / 롤백 절차를 한 문서에 담는다.
2. 환경 변수 (`DATABASE_URL`, `BCRYPT_ROUNDS`, `ENVIRONMENT` 등) 의 운영 매트릭스를 명시.
3. Postgres 등 운영 DB 로 이전 시의 차이점 (현재 SQLite 기반) 을 미리 안내.
4. 트러블슈팅 시나리오 (multiple heads, 실패한 revision, sqlmodel import 누락 등) 를 미리 기록.

---

## 3. 비목적

- 실제 운영 인프라 (CI/CD pipeline, Docker, deploy 스크립트) 구축 — 별도 PR.
- Postgres 환경 실증 — 별도 PR (PR #14 후속 항목).
- 자동 CI 통합 (`alembic upgrade head` 가 배포 단계에서 자동 실행) — 별도 PR.
- 운영 모니터링 / 알람 — 별도 PR (loguru sink 항목과 함께 진행 가능).
- 보안 정책 핸드북 (BCRYPT_ROUNDS, 마스킹 정책 등) — 별도 SECURITY.md 후속.
- 한국어/영어 동시 작성 — 본 RUNBOOK 은 한국어 (프로젝트 컨벤션).

---

## 4. 성공 기준

- [ ] `docs/RUNBOOK.md` 신규 작성. 다음 섹션 포함:
  - 환경 변수 매트릭스
  - 초기 배포 절차
  - 스키마 변경 절차
  - 일상 alembic 명령어 매트릭스
  - 롤백 시나리오
  - Postgres 이전 안내 (체크리스트)
  - 트러블슈팅
- [ ] 모든 명령은 **복사-붙여넣기 가능** 한 형태로 (코드 블록).
- [ ] 명령 결과 / 예상 출력을 인라인으로 함께.
- [ ] 본 PR 머지 후 [HANDOFF] §10 참고 파일 섹션에 `docs/RUNBOOK.md` 추가.
- [ ] 코드 변경 0, 테스트 변경 0 — 회귀 영향 없음.
- [ ] `uv run pytest` 55 PASS 그대로.

---

## 5. 설계

### 5.1 RUNBOOK.md 의 구조

```markdown
# RUNBOOK — fastapi-sample 운영 가이드

## 1. 개요
## 2. 환경 변수 매트릭스
## 3. 초기 배포
## 4. 스키마 변경
## 5. 일상 명령
## 6. 롤백
## 7. Postgres 이전 체크리스트
## 8. 트러블슈팅
## 9. 참고 문서 / 링크
```

### 5.2 섹션별 핵심 내용

#### §2 환경 변수 매트릭스

| 변수 | 기본값 | 운영 권장값 | 설명 |
| --- | --- | --- | --- |
| `ENVIRONMENT` | `development` | `production` | 로그/보안 정책 분기 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | `postgresql+asyncpg://...` | DB 연결 문자열 (async drivers) |
| `DB_ECHO` | `false` | `false` | SQL 출력 — 운영에서는 비활성 |
| `SECRET_KEY` | placeholder | **반드시 변경** | JWT 서명 키 |
| `BCRYPT_ROUNDS` | `12` | `12` 또는 `13` | bcrypt 라운드 (운영에선 ≥12) |
| ~~AUTO_CREATE_TABLES~~ | (제거됨) | — | PR #14 에서 폐기. alembic 으로 대체 |

#### §3 초기 배포

```bash
# 1. 환경 변수 설정 (.env)
cp .env.example .env  # 또는 운영 secret 매니저
# DATABASE_URL, SECRET_KEY 등 채움

# 2. 의존성 설치
uv sync --all-extras

# 3. DB 초기 스키마 적용 (PR #14 의 첫 리비전)
uv run alembic upgrade head

# 4. 검증
uv run alembic current  # → ab265552a4a2 (head)

# 5. 앱 기동
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### §4 스키마 변경

```bash
# 1. 모델 수정 (app/user/models.py 또는 app/product/models.py)

# 2. 리비전 자동 생성
uv run alembic revision --autogenerate -m "<변경 요약>"

# 3. 생성된 alembic/versions/<hash>_<slug>.py 검토
#    - upgrade()/downgrade() 가 의도와 일치하는지
#    - sqlmodel 의 AutoString 등 특수 타입이 정상 처리됐는지

# 4. 로컬에서 적용 + 회귀 테스트
uv run alembic upgrade head
uv run pytest

# 5. 커밋 + PR
```

#### §5 일상 명령 매트릭스

| 작업 | 명령 |
| --- | --- |
| 최신 스키마 | `uv run alembic upgrade head` |
| 한 단계 다운그레이드 | `uv run alembic downgrade -1` |
| 처음으로 | `uv run alembic downgrade base` |
| 적용된 리비전 확인 | `uv run alembic current` |
| 히스토리 | `uv run alembic history --verbose` |
| 새 리비전 (자동) | `uv run alembic revision --autogenerate -m "..."` |
| 새 리비전 (수동) | `uv run alembic revision -m "..."` |
| 다음/이전 리비전 | `uv run alembic heads` / `uv run alembic show <rev>` |

#### §6 롤백

- **단일 리비전 롤백**: `uv run alembic downgrade -1`
- **특정 리비전으로 롤백**: `uv run alembic downgrade <rev_id>`
- **DB 전체 초기화**: `uv run alembic downgrade base` (개발만)
- **운영에서 데이터가 들어간 후의 롤백**:
  - downgrade SQL 이 데이터를 삭제할 수 있으므로 **백업 후 진행**
  - DDL 변경은 가능하면 forward-only (다음 리비전에서 정정) 가 안전
  - 비상시: `pg_dump` / `restore` 로 시점 복구 + 정상 리비전부터 재 upgrade

#### §7 Postgres 이전 체크리스트

- [ ] `DATABASE_URL=postgresql+asyncpg://user:pass@host/db`
- [ ] `asyncpg` 의존성 추가 (`uv add asyncpg`)
- [ ] 새 환경에서 `uv run alembic upgrade head` 검증
- [ ] 기존 SQLite 데이터 마이그레이션 (수동 SQL 또는 ETL)
- [ ] `tests/migration/test_alembic_schema.py` 가 SQLite 만 검증 — Postgres 별도 통합 테스트 권장
- [ ] timezone-aware datetime 이 native 지원되므로 `tests/core/test_datetime_handling.py` 의 SQLite 한계 노트 해소

#### §8 트러블슈팅

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| `revision --autogenerate` 가 빈 리비전 생성 | 모델 변경 미반영 (import 누락) | `alembic/env.py` 의 `_user_models`, `_product_models` import 확인 |
| 생성된 리비전이 `NameError: sqlmodel is not defined` | `script.py.mako` 누락 (PR #14 의 보강 누락) | `alembic/script.py.mako` 에 `import sqlmodel` 확인 |
| `Multiple heads detected` | 여러 브랜치에서 동시에 revision 생성 | `alembic merge <h1> <h2> -m "merge"` 로 합침 |
| `Can't locate revision identified by '<rev>'` | git pull 시점 충돌 | `alembic history` 로 확인 후 정상 head 로 reset |
| 테스트가 production DB 에 쓰기 시도 | `DATABASE_URL` 이 conftest override 전에 사용 | conftest 가 `Container.engine.override(...)` 적용 시점 확인 |

#### §9 참고 문서 / 링크

- `[PRD]Alembic_첫_마이그레이션.md`, `[PLAN]Alembic_첫_마이그레이션.md`
- `[HANDOFF]세션_이어가기.md`
- Alembic docs: https://alembic.sqlalchemy.org
- SQLAlchemy async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html

---

## 6. 영향

| 영역 | 영향 |
| --- | --- |
| `docs/RUNBOOK.md` | 신규 |
| `docs/[HANDOFF]세션_이어가기.md` §10 | 참고 파일에 RUNBOOK 한 줄 추가 |
| 코드 / 테스트 / DB / API | **변화 없음** |
| 회귀 | 55 PASS 그대로 |

---

## 7. 리스크

| 리스크 | 가능성 | 대응 |
| --- | --- | --- |
| RUNBOOK 의 명령이 실제 환경에서 동작 안 함 | 낮음 | 모든 명령을 본 PR 검증 단계에서 실제 실행 (dev 환경) |
| 일부 환경 변수 정보가 사실과 다름 | 낮음 | `app/core/config.py` 의 Settings 클래스를 그대로 참조 |
| Postgres 체크리스트가 추상적 | 중 | 실증은 별도 PR (운영 검증) — 본 PR 은 안내 수준 명시 |
| RUNBOOK 이 코드 변경에 따라 stale 됨 | 중 | 각 섹션에 참조한 PR 번호 / 출처 파일 명시. 후속에서 갱신 책임 명확화 |

---

## 8. 결정 사항 (확정)

- [x] 파일: `docs/RUNBOOK.md` (kebab/space 없음, 단일 파일)
- [x] 언어: 한국어 (프로젝트 컨벤션)
- [x] 형식: Markdown, 코드 블록은 bash/markdown 명시
- [x] 분량: 약 200~300 줄 (한 페이지 내 운영 핸드북 수준)
- [x] HANDOFF §10 에 한 줄 추가
- [x] 코드 변경 0 / 테스트 변경 0
- [x] 본 PR 검증 단계에서 모든 명령 실제 실행으로 검증

---

## 9. 참고

- `docs/[PRD]Alembic_첫_마이그레이션.md`
- `alembic.ini`, `alembic/env.py`, `alembic/versions/`
- `app/core/config.py` (Settings 정의)
- `[HANDOFF]세션_이어가기.md` §5, §10
