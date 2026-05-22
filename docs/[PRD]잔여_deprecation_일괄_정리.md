# 잔여 deprecation 일괄 정리 PRD

| 항목       | 내용                                                                            |
| ---------- | ------------------------------------------------------------------------------- |
| 작성일     | 2026-05-22                                                                      |
| 작성자     | conner                                                                          |
| 상태       | 제안 (Draft)                                                                    |
| 도메인     | 모델 / 테스트 설정                                                              |
| 대상 범위  | `app/user/models.py`, `app/product/models.py`, `tests/pytest.ini`              |
| 관련 발견  | PR #1 ~ #7 의 테스트 실행 시 매번 누적되는 잔여 warning                          |

---

## 1. 배경

PR #5 (passlib 제거), PR #6 (Pydantic `.dict()` → `.model_dump()`) 에서 큼지막한 deprecation 을 해소했지만 다음 두 가지가 잔존한다.

### 1.1 `datetime.utcnow()` deprecation

```
DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled
for removal in a future version. Use timezone-aware objects to represent
datetimes in UTC: datetime.datetime.now(datetime.UTC).
```

**사용 위치 — 정확히 10곳**:

| 파일                       | 위치                              | 컨텍스트                       |
| -------------------------- | --------------------------------- | ------------------------------ |
| `app/user/models.py`       | 29, 30, 33, 36, 37                | `created_at`, `updated_at` 컬럼 |
| `app/product/models.py`    | 31, 32, 35, 38, 39                | `created_at`, `updated_at` 컬럼 |

각 컬럼마다:
- `Field(default_factory=datetime.utcnow, ...)` (Pydantic 측)
- `Column(DateTime, default=datetime.utcnow)` (SQLAlchemy 측)
- `updated_at` 의 경우 `onupdate=datetime.utcnow` 도 포함

Pydantic 과 SQLAlchemy 양쪽에서 deprecation warning 발생.

> **참고**: `app/core/security.py:57, 59` 의 JWT 토큰 부분은 PR #5 (또는 그 이전) 에서 이미 `datetime.now(UTC)` 로 마이그레이션 완료. 모델 측만 잔존.

### 1.2 `pytest.ini` 의 `verbosity` 옵션

```
PytestConfigWarning: Unknown config option: verbosity
```

- `tests/pytest.ini:19` 에 `verbosity = 2` 라인 존재
- pytest 는 `verbosity` 라는 ini 옵션을 인식하지 않음 (정확한 옵션은 CLI 의 `-v`/`-vv` 또는 `addopts`)
- 의도된 동작 없이 매 실행 시 warning 만 출력

### 1.3 timezone-aware vs naive 의 미묘함

단순 `datetime.utcnow()` → `datetime.now(UTC)` 1:1 대체는 **반환 타입이 달라진다.**

| 호출                   | 반환                                          | `Column(DateTime)` 호환 |
| ---------------------- | --------------------------------------------- | ----------------------- |
| `datetime.utcnow()`    | naive datetime (`tzinfo=None`)               | ✅ (기본 DateTime)        |
| `datetime.now(UTC)`    | aware datetime (`tzinfo=UTC`)                | ❌ (기본 DateTime, PostgreSQL 에서 에러) |

→ 컬럼 정의도 `DateTime(timezone=True)` 로 함께 변경해야 timezone-aware datetime 을 안전하게 받을 수 있다.

---

## 2. 목적

- `datetime.utcnow()` deprecation 을 완전히 제거 (Python 3.13+ 호환성 확보).
- 컬럼 정의를 timezone-aware (`DateTime(timezone=True)`) 로 정렬 → 데이터 모델에서 시간대 정보가 명시적으로 표현됨.
- `pytest.ini` 의 잘못된 `verbosity` 옵션 제거.
- 테스트 실행 시 발생하는 잔여 warning 의 대부분을 일소.

### 비목적

- Alembic 마이그레이션 파일 작성 — `alembic/versions/` 가 비어있고 `AUTO_CREATE_TABLES=true` 로 SQLModel `create_all` 만 사용 중이므로 첫 마이그레이션은 별도 PRD 에서 다룬다.
- 기존 DB row 의 timezone 정보 정정 — 운영 DB 가 없는 상태 가정.
- pytest `addopts` 에 `-v` 추가 (verbose 출력을 항상 켜는 것은 별도 결정).
- 다른 deprecation 정리 (예: bcrypt 라이브러리 자체의 경고, fastapi 의 OAuth2 관련) — 본 PR 은 위 2 가지로 한정.

---

## 3. 성공 기준

| 지표                                                                                  | 목표값          |
| ------------------------------------------------------------------------------------- | --------------- |
| `datetime.utcnow()` 사용 (`grep -rn "utcnow" app/`)                                   | 0 건            |
| `datetime.datetime.utcnow() is deprecated` warning                                     | 0 건            |
| `Unknown config option: verbosity` warning                                            | 0 건            |
| 전체 warning 수                                                                       | 73 → 10 미만으로 감소 |
| 기존 회귀 테스트                                                                      | 32/32 PASS 유지 |
| 신규 회귀 가드 (timezone-aware 동작 검증)                                             | 신규 2 케이스   |

---

## 4. 설계

### 4.1 datetime 패턴 정렬

**모든 모델 컬럼을 다음 패턴으로 정렬**:

```python
# app/user/models.py / app/product/models.py
from datetime import datetime, UTC

created_at: datetime = Field(
    default_factory=lambda: datetime.now(UTC),
    sa_column=Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    ),
)
updated_at: datetime = Field(
    default_factory=lambda: datetime.now(UTC),
    sa_column=Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    ),
)
```

**핵심 변화**:
- `datetime.utcnow` (callable) → `lambda: datetime.now(UTC)` (callable, returns aware)
- `DateTime` (timezone-naive) → `DateTime(timezone=True)` (timezone-aware)

### 4.2 lambda 반복 vs 헬퍼

10 곳에 lambda 가 반복된다. 가독성을 위해 짧은 헬퍼 도입을 고려할 수 있다.

| 옵션 | 형태                                                              | 평가                                |
| ---- | ----------------------------------------------------------------- | ----------------------------------- |
| α    | `default_factory=lambda: datetime.now(UTC)` (현재 선택)            | 정석. 의존성 최소                   |
| β    | 헬퍼 모듈 `app/core/datetime.py` 의 `utcnow_aware()` 정의 후 import | 가독성 ↑, import 비용 (소소)        |

**채택: α (lambda 직접)**. 헬퍼 도입은 후속 작업으로 분리 가능.

### 4.3 SQLite 와 timezone-aware datetime

SQLite 는 timezone-aware datetime 을 받아 **ISO 문자열로 저장하지만 timezone 정보를 그대로 보존** 한다. 검색 시에는 문자열 비교로 동작하므로 동일 시간대 (UTC) 내에서는 문제 없음.

본 프로젝트 테스트는 SQLite + StaticPool 인메모리 환경이라 추가 검증 필요. 회귀 가드 (§5) 가 이를 자동 확인.

### 4.4 pytest.ini 정리

```ini
# tests/pytest.ini (변경 전)
verbosity = 2

# 변경 후 — 해당 라인 제거
```

verbose 출력이 필요하면 `addopts = -v` 추가 또는 CLI 에서 `pytest -v`. 본 PR 은 잘못된 옵션 제거만.

---

## 5. 회귀 가드 (신규 테스트)

### 5.1 신규 케이스 (2 케이스)

`tests/core/test_datetime_handling.py` (신규).

```python
"""모델의 datetime 필드가 timezone-aware UTC 로 동작하는지 검증."""
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.models import UserModel


@pytest.mark.asyncio
async def test_user_created_at_is_timezone_aware(db_session: AsyncSession):
    """UserModel.created_at 이 timezone-aware UTC 로 저장된다."""
    user = UserModel(
        email="tz@example.com",
        username="tzuser",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.created_at.tzinfo is not None
    # UTC 와 동등한 offset
    assert user.created_at.utcoffset() == UTC.utcoffset(datetime.now(UTC))


@pytest.mark.asyncio
async def test_user_updated_at_changes_on_update(db_session: AsyncSession):
    """UserModel.updated_at 이 UPDATE 시점에 자동 갱신된다."""
    import asyncio

    user = UserModel(
        email="upd@example.com",
        username="upduser",
        hashed_password="h",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    initial_updated = user.updated_at

    # SQLite 의 datetime precision 한계로 짧은 sleep
    await asyncio.sleep(0.01)

    user.username = "upduser_renamed"
    await db_session.commit()
    await db_session.refresh(user)

    assert user.updated_at > initial_updated
    assert user.updated_at.tzinfo is not None
```

> SQLite 가 timezone-aware datetime 을 어떻게 저장/조회하는지 검증. PostgreSQL 으로 이전 시에도 통과해야 함.

### 5.2 회귀 자동화 — warning 카운트

```bash
# 본 PR 머지 전 기준선 측정
uv run pytest 2>&1 | grep -c "datetime.datetime.utcnow"
uv run pytest 2>&1 | grep -c "Unknown config option: verbosity"
```

머지 후 둘 다 0 이어야 함.

---

## 6. 영향 받는 파일

| 파일                                | 변경 종류                                                    | 비고                                                 |
| ----------------------------------- | ------------------------------------------------------------ | ---------------------------------------------------- |
| `app/user/models.py`                | 5 곳 변경 — `datetime.utcnow` → lambda + `DateTime(timezone=True)` | `created_at` × 2, `updated_at` × 3                 |
| `app/product/models.py`             | 5 곳 변경 — 동일 패턴                                         | 동일                                                 |
| `tests/pytest.ini`                  | `verbosity = 2` 라인 삭제                                    | 빈 행 정리                                            |
| `tests/core/test_datetime_handling.py` (신규) | timezone-aware 동작 검증 2 케이스                    | `tests/core/__init__.py` 는 PR #5 에서 이미 존재     |

---

## 7. 테스트 영향

| 기존 테스트                      | 영향                                          |
| -------------------------------- | --------------------------------------------- |
| `test_create_user`, `test_login` | 동일 동작 — PASS 유지                         |
| 상품/사용자 조회/수정 케이스     | datetime 필드의 응답 직렬화는 ISO 문자열 동일 |
| `test_security` 5 케이스         | datetime 무관 — 영향 없음                     |

신규 2 케이스 추가로 **32 → 34 PASS**.

---

## 8. 리스크 및 미해결 이슈

| #   | 항목                                                                                  | 대응                                                                          |
| --- | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 1   | SQLite 가 timezone 정보를 어떻게 저장/조회하는지                                      | ISO 문자열로 timezone offset 까지 저장. 비교 / 정렬 동일 시간대에서는 안전. §5.1 가드 |
| 2   | 기존 DB 가 있는 환경에서 컬럼 타입 변경                                              | 본 프로젝트는 dev/test 환경 가정 (alembic/versions 비어있음). 운영 DB 가 생기면 별도 마이그레이션 |
| 3   | `DateTime(timezone=True)` 가 SQLAlchemy 2.0 모든 DB dialect 에서 동작 여부            | PostgreSQL, MySQL, SQLite 모두 지원. 일반적 호환                              |
| 4   | lambda 반복으로 인한 가독성 저하                                                      | 헬퍼 함수 추출은 후속 작업으로 분리                                            |
| 5   | Pydantic 의 `default_factory` 와 SQLAlchemy 의 `default` 가 동시에 정의됨 — 중복 호출 위험 | 본 프로젝트 패턴 그대로 유지 (sa_column 우선). 별도 정리 이슈                  |
| 6   | API 응답에서 datetime 직렬화 형식 변화 가능성                                          | Pydantic v2 의 datetime ISO 직렬화는 timezone-aware 면 `+00:00` 접미사 포함 → 클라이언트 호환 필요 시 검토 |

### 결정 사항 (확정)

- [x] 옵션 A 채택 — `DateTime(timezone=True)` + `datetime.now(UTC)`
- [x] lambda 직접 사용 (헬퍼 도입은 후속)
- [x] `pytest.ini` 의 `verbosity = 2` 단순 삭제
- [x] alembic 마이그레이션은 본 PR 범위 외

### 리스크 #6 — API 응답 datetime 형식 변화

변경 전 (`datetime.utcnow`, naive):
```json
"created_at": "2026-05-22T18:30:00.123456"
```

변경 후 (`datetime.now(UTC)`, aware):
```json
"created_at": "2026-05-22T18:30:00.123456+00:00"
```

→ **클라이언트가 ISO 8601 표준 timezone 접미사를 받을 수 있는지** 검토 필요. 표준 라이브러리는 모두 처리 가능하지만 일부 모바일 클라이언트나 레거시 파서는 영향 가능. 본 PR 의 회귀 가드 (`test_create_user` 등) 가 응답 검증 시 키 존재 여부만 확인하므로 자동 검증되지는 않음 — **수동 점검 필요 사항**.

---

## 9. 참고

- Python 3.13 datetime 변경: https://docs.python.org/3.13/whatsnew/3.12.html#deprecated (3.12 에서 deprecation 시작)
- SQLAlchemy `DateTime(timezone=True)`: https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.DateTime
- pytest ini 옵션: https://docs.pytest.org/en/stable/reference/reference.html#configuration-options
- 핵심 코드:
  - `app/user/models.py:29-39`
  - `app/product/models.py:31-39`
  - `tests/pytest.ini:19`
- 선례: PR #5 (passlib 제거), PR #6 (Pydantic .dict() → .model_dump())
