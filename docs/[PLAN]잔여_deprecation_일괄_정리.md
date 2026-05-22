# 잔여 deprecation 일괄 정리 구현 Plan

| 항목         | 내용                                                                          |
| ------------ | ----------------------------------------------------------------------------- |
| 작성일       | 2026-05-22                                                                    |
| 연관 PRD     | [`[PRD]잔여_deprecation_일괄_정리.md`](./[PRD]잔여_deprecation_일괄_정리.md) |
| 상태         | 제안 (Draft)                                                                  |
| 추정 작업량  | 약 1 시간 (구현 + timezone-aware 테스트 + 검증)                                |
| 채택 전략    | `DateTime(timezone=True)` + `lambda: datetime.now(UTC)`                       |

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 기준 최신 상태에서 `feature/datetime-aware` 브랜치 생성
- [ ] `uv run pytest` 현재 32/32 PASS 확인
- [ ] 변경 전 warning 카운트 측정 (기준선)

```bash
uv run pytest 2>&1 | grep -c "datetime.datetime.utcnow"
# 기준선 기록
uv run pytest 2>&1 | grep -c "Unknown config option: verbosity"
# 기준선 기록
```

---

## 1. 작업 분해

### Step 1. `app/user/models.py` — 5 곳 변경

**변경 내용**

1. `from datetime import datetime, UTC` 로 변경 (UTC 추가 import)
2. `Column(DateTime, ...)` → `Column(DateTime(timezone=True), ...)`
3. `datetime.utcnow` → `lambda: datetime.now(UTC)`

```python
# app/user/models.py (변경 후 — datetime 관련 부분만)
from datetime import datetime, UTC

class UserModel(SQLModel, table=True):
    ...
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

**검증**

```bash
uv run pytest tests/user/test_router.py -v --tb=short
```

User 라우터 테스트 (생성/조회/수정/삭제) PASS.

---

### Step 2. `app/product/models.py` — 5 곳 변경

**변경 내용**

Step 1 과 동일 패턴 적용.

```python
# app/product/models.py (변경 후 — datetime 관련 부분만)
from datetime import datetime, UTC

class ProductModel(SQLModel, table=True):
    ...
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

**검증**

```bash
uv run pytest tests/product/test_router.py -v --tb=short
```

Product 라우터 테스트 PASS.

---

### Step 3. `tests/pytest.ini` — `verbosity` 라인 삭제

```ini
# tests/pytest.ini (변경 전 — line 19)
# 테스트 실행 시 표시할 정보 설정
verbosity = 2

# 변경 후 — 두 줄 모두 삭제 (주석 + 옵션)
```

> verbose 출력이 필요하면 CLI 에서 `pytest -v`. ini 에서 강제는 안 함.

**검증**

```bash
uv run pytest 2>&1 | grep -c "Unknown config option: verbosity"
# → 0
```

---

### Step 4. 신규 회귀 가드 추가

**대상**: `tests/core/test_datetime_handling.py` (신규)

```python
"""모델의 datetime 필드가 timezone-aware UTC 로 동작하는지 검증."""
import asyncio
from datetime import UTC, datetime

import pytest

from app.user.models import UserModel


@pytest.mark.asyncio
async def test_user_created_at_is_timezone_aware(db_session):
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

    assert user.created_at.tzinfo is not None, "created_at 은 timezone-aware 이어야 함"
    # UTC 와 동일한 offset 인지 확인
    now_utc = datetime.now(UTC)
    assert user.created_at.utcoffset() == now_utc.utcoffset()


@pytest.mark.asyncio
async def test_user_updated_at_changes_on_update(db_session):
    """UserModel.updated_at 이 UPDATE 시점에 자동 갱신된다."""
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

> conftest 의 `db_session` fixture 사용. PR #1 의 `tests/conftest.py` 가 이미 비동기 세션을 제공.

**검증**

```bash
uv run pytest tests/core/test_datetime_handling.py -v --tb=short
```

2 케이스 PASS.

---

### Step 5. 전체 회귀 + warning 카운트 검증

```bash
uv run pytest -v
```

기존 32 + 신규 2 = **34 PASS** 확인.

```bash
# 변경 후 warning 카운트
uv run pytest 2>&1 | grep -c "datetime.datetime.utcnow"
# → 0

uv run pytest 2>&1 | grep -c "Unknown config option: verbosity"
# → 0

# 전체 warning 감소 확인
uv run pytest 2>&1 | tail -3
# "73 warnings" → 10 미만으로 감소 기대
```

```bash
# 코드 grep 검증
grep -rn "utcnow" app/ --include="*.py"
# → 출력 없음 (app/core/security.py 의 datetime.now(UTC) 외에 utcnow 없음)
```

---

### Step 6. API 응답 datetime 형식 수동 점검 (PRD §8-#6 리스크)

변경으로 인해 API 응답의 datetime 형식이 변화:
- 변경 전: `"2026-05-22T18:30:00.123456"` (naive)
- 변경 후: `"2026-05-22T18:30:00.123456+00:00"` (aware)

본 PR 머지 전 다음 수동 검증을 권장 (PR 본문 명시):

```bash
# 회원가입 후 응답의 created_at 형식 확인
curl -s -X POST http://localhost:8000/api/v1/users/ \
  -H "Content-Type: application/json" \
  -d '{"email":"new@example.com","username":"new","password":"passwd1234","password_confirm":"passwd1234"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['created_at'])"
# 예상: "2026-05-22T...+00:00"
```

---

## 2. 산출물 체크리스트

- [ ] `app/user/models.py` — datetime 임포트 변경 + 컬럼 5 곳 timezone-aware 로
- [ ] `app/product/models.py` — 동일 패턴 적용
- [ ] `tests/pytest.ini` — `verbosity` 옵션 + 위 주석 제거
- [ ] `tests/core/test_datetime_handling.py` (신규) — 2 케이스
- [ ] `uv run pytest -v` **34/34 PASS**
- [ ] `grep -c "datetime.datetime.utcnow"` 결과 0
- [ ] `grep -c "Unknown config option: verbosity"` 결과 0
- [ ] `grep -rn "utcnow" app/` 결과 없음

---

## 3. 테스트 케이스 (완료 판정 기준)

### 3.1 신규 (2 케이스)

| #   | 테스트                                          | 검증 포인트                                                  |
| --- | ----------------------------------------------- | ------------------------------------------------------------ |
| 1   | `test_user_created_at_is_timezone_aware`        | `created_at.tzinfo` 가 not None, UTC offset 일치             |
| 2   | `test_user_updated_at_changes_on_update`        | UPDATE 시 `updated_at` 자동 갱신 + aware 유지                |

### 3.2 기존 (32 케이스, PASS 유지)

라우터 통합 테스트 / 권한 / 재고 / 보안 등 모두 PASS 유지.

---

## 4. Warning 카운트 매트릭스

| Warning 출처                            | 변경 전 | 변경 후 |
| --------------------------------------- | ------- | ------- |
| `datetime.datetime.utcnow() is deprecated` (Pydantic 측) | 매 실행 ~ N 건 | **0 건** |
| `datetime.datetime.utcnow() is deprecated` (SQLAlchemy 측) | 매 실행 ~ N 건 | **0 건** |
| `Unknown config option: verbosity`      | 매 실행 1 건 | **0 건** |
| 전체 warning 수                         | 73      | 10 미만으로 감소 |

---

## 5. 회귀 방지 체크리스트

PR 머지 전 모두 확인.

- [ ] `uv run pytest` **34/34 PASS**
- [ ] `grep -rn "utcnow" app/ tests/` 결과 없음 (`app/core/security.py` 는 이미 `datetime.now(UTC)`)
- [ ] `grep -rn "DateTime[^(]" app/` 결과 없음 (모든 DateTime 컬럼이 `DateTime(timezone=True)`)
- [ ] `git diff main -- app/ tests/pytest.ini` 결과가 의도된 변경만 포함
- [ ] 회원가입 / 로그인 / 사용자 조회 / 상품 조회 통합 회귀 PASS
- [ ] (수동) API 응답의 `created_at`, `updated_at` 가 `+00:00` 접미사 포함하는지 확인

---

## 6. 롤백 전략

- 본 작업은 4 파일 변경 (`user/models.py`, `product/models.py`, `pytest.ini`) + 신규 1.
- 별도 브랜치 (`feature/datetime-aware`) 에서 작업. 문제 시 `git checkout main` 으로 원복.
- 두 모델 파일은 독립 — 한쪽 단독 revert 가능 (테스트도 부분 PASS).
- 만약 클라이언트가 timezone 접미사를 못 받는다고 알려지면 변경을 되돌리고 헬퍼 함수 (`utcnow_naive`) 패턴으로 재추진.

---

## 7. 후속 작업 (별도 이슈 권장)

| #   | 항목                                                                          | 권장 처리                                                  |
| --- | ----------------------------------------------------------------------------- | ---------------------------------------------------------- |
| 1   | lambda 10 곳 반복 → 헬퍼 함수 추출 (`app/core/datetime.py::utcnow_aware()`)   | 가독성 정리. 별도 청소 PR                                  |
| 2   | Alembic 첫 마이그레이션 작성 (현재 versions/ 비어있음)                       | 별도 PRD — 운영 DB 도입 시 필수                            |
| 3   | Pydantic `default_factory` 와 SQLAlchemy `default` 의 중복 평가 회피          | sa_column 만 사용하거나 default_factory 만 사용 — 별도 정리 |
| 4   | API 응답 datetime 직렬화 모드 (`mode="json"`) 명시 설정                       | 응답 일관성 강화                                            |
| 5   | pytest `addopts = -v` 추가 검토                                               | 별도 결정 — CI 출력 부피 고려                              |

---

## 8. 참고

- 관련 PRD: [`[PRD]잔여_deprecation_일괄_정리.md`](./[PRD]잔여_deprecation_일괄_정리.md)
- 핵심 코드:
  - `app/user/models.py:29-39` — 수정 대상
  - `app/product/models.py:31-39` — 수정 대상
  - `tests/pytest.ini:19` — 라인 삭제 대상
- SQLAlchemy DateTime(timezone): https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.DateTime
- Python 3.12 datetime.utcnow deprecation: https://docs.python.org/3.12/library/datetime.html#datetime.datetime.utcnow
- 선례:
  - PR #5 (passlib 제거 — 다른 deprecation 카테고리)
  - PR #6 (Pydantic .dict() → .model_dump())
