# [PRD] `utcnow_aware()` 헬퍼 추출

| 항목 | 내용 |
| --- | --- |
| 상태 | 제안 (Draft) |
| 작성일 | 2026-05-23 |
| 출처 | PR #8 §4.2 (옵션 β) 후속, [HANDOFF] §6 마스터 목록 |
| 분류 | 청소 (가독성 / 중복 제거) |
| 추정 작업량 | 소 (≤ 30 분) |

---

## 1. 배경

PR #8 (`datetime.utcnow → datetime.now(UTC)`) 에서 모델 두 곳 (`app/user/models.py`, `app/product/models.py`) 에 동일한 콜러블이 10 곳 반복으로 남았다.

```python
# app/user/models.py / app/product/models.py 각 5곳, 총 10곳
default_factory=lambda: datetime.now(UTC),
default=lambda: datetime.now(UTC),
onupdate=lambda: datetime.now(UTC),
```

PR #8 PRD §4.2 에서 채택한 옵션은 α (lambda 직접) 였고, 옵션 β (헬퍼 도입) 는 명시적으로 "후속 작업으로 분리" 라고 결정됐다. 본 PRD 는 그 후속을 진행한다.

---

## 2. 목적

1. 동일 lambda 10 회 반복을 명명된 헬퍼 한 곳에 모은다.
2. "timezone-aware UTC 현재 시각" 의 의미를 콜사이트에서 한눈에 읽히게 한다 (`utcnow_aware`).
3. 향후 시간 소스를 교체하거나 (예: freezegun, 모킹) 정밀도 정책을 바꿀 때 한 지점만 손대면 되게 한다.

---

## 3. 비목적

- 시간 소스 자체의 변경 (모킹 인프라, 가짜 시계, monotonic clock 등) — 별도 PR.
- `app/core/security.py` 의 `datetime.now(UTC)` 직접 호출 (lambda 아님, 표현식 평가 시점에 즉시 호출되어야 함) — 의도된 형태이므로 변경하지 않는다.
- `Depends(lambda: Container.user_service())` 형태의 DI 컨테이너 와이어링 lambda — datetime 과 무관, 별도 청소 후보.
- 새 테스트 인프라 추가 — 기존 `tests/core/test_datetime_handling.py` 가 timezone-aware 정합성을 이미 검증.

---

## 4. 성공 기준

- [ ] `app/core/datetime.py` 에 `utcnow_aware() -> datetime` 헬퍼 신설 (timezone-aware UTC 반환).
- [ ] `app/user/models.py` 의 lambda 5 곳 → `utcnow_aware` 로 치환.
- [ ] `app/product/models.py` 의 lambda 5 곳 → `utcnow_aware` 로 치환.
- [ ] `grep -rn "lambda: datetime.now(UTC)" app/` 결과 0 건.
- [ ] 헬퍼 단위 테스트 (반환값이 timezone-aware UTC) 추가.
- [ ] 기존 회귀 테스트 39 건 + 신규 케이스 → **40+ PASS, deprecation warning 0 건** 유지.
- [ ] `from datetime import datetime, UTC` 가 더 이상 필요 없는 모델 파일은 import 정리.

---

## 5. 설계

### 5.1 헬퍼 위치 / 이름

| 결정 항목 | 채택 | 근거 |
| --- | --- | --- |
| 파일 경로 | `app/core/datetime.py` | PR #8 PRD §4.2 에서 이미 가이드. 절대 import 만 쓰므로 stdlib `datetime` 과 충돌하지 않음 |
| 함수 이름 | `utcnow_aware()` | PR #8 PRD 에 명시. "timezone-aware UTC now" 의도가 이름에 드러남 |
| 시그니처 | `def utcnow_aware() -> datetime` | 인자 없음, 매 호출 시 `datetime.now(UTC)` 반환 (콜러블이므로 SQLModel 의 `default_factory` / SQLAlchemy 의 `default` / `onupdate` 와 그대로 호환) |

### 5.2 헬퍼 구현

```python
# app/core/datetime.py
"""시간 관련 공통 헬퍼.

`utcnow_aware()` 는 timezone-aware UTC 현재 시각을 반환한다. SQLModel /
SQLAlchemy 의 `default_factory` / `default` / `onupdate` 콜러블로 직접 전달하기
위해 인자를 받지 않는다.
"""
from datetime import datetime, UTC


def utcnow_aware() -> datetime:
    return datetime.now(UTC)
```

### 5.3 모델 치환 패턴

```python
# app/user/models.py / app/product/models.py
from app.core.datetime import utcnow_aware

# Before
default_factory=lambda: datetime.now(UTC),
default=lambda: datetime.now(UTC),
onupdate=lambda: datetime.now(UTC),

# After
default_factory=utcnow_aware,
default=utcnow_aware,
onupdate=utcnow_aware,
```

`datetime.now(UTC)` 가 모델 파일에서 더 이상 직접 호출되지 않으면 `from datetime import datetime, UTC` 의 `UTC` import 는 제거 (필드 타입 어노테이션용 `datetime` 만 유지).

### 5.4 단위 테스트

`tests/core/test_datetime_handling.py` 는 모델 단위 동작을 검증하므로, 헬퍼 자체의 단위 테스트는 같은 파일이 아닌 새 파일 (`tests/core/test_datetime_helper.py`) 에 분리하는 것보다 같은 디렉토리 / 파일에 함수 단위 테스트를 추가하는 편이 응집도가 높다. 단, 헬퍼는 책임이 다르므로 별도 모듈로 분리한다.

```python
# tests/core/test_datetime_helper.py (신규)
from datetime import UTC, datetime
from app.core.datetime import utcnow_aware


def test_utcnow_aware_is_timezone_aware():
    now = utcnow_aware()
    assert now.tzinfo is not None
    assert now.utcoffset() == datetime.now(UTC).utcoffset()


def test_utcnow_aware_is_callable_default_factory():
    """SQLModel `default_factory` 에 그대로 전달 가능한 시그니처임을 보장."""
    factory = utcnow_aware
    result = factory()  # 인자 없이 호출 가능해야 함
    assert isinstance(result, datetime)
    assert result.tzinfo is not None
```

---

## 6. 영향

| 영역 | 영향 |
| --- | --- |
| 모델 동작 | **변화 없음** — `utcnow_aware` 는 `lambda: datetime.now(UTC)` 와 의미적으로 동일 |
| 마이그레이션 | 없음 — DB 스키마/컬럼 타입 불변 |
| 테스트 | +2 케이스 (헬퍼 단위), 기존 통과 |
| 외부 API | 변화 없음 |
| 가독성 | 모델 필드 정의에서 "지금" 의 의미가 명시적으로 드러남 |

---

## 7. 리스크

| 리스크 | 가능성 | 대응 |
| --- | --- | --- |
| `app/core/datetime.py` 가 stdlib `datetime` 과 혼동 | 매우 낮음 | 절대 import (`from app.core.datetime import utcnow_aware`) 만 사용. 모듈 내에서 `from datetime import datetime, UTC` 는 stdlib 우선 |
| `default_factory` / `default` / `onupdate` 시그니처 비호환 | 매우 낮음 | 셋 다 인자 0 콜러블 기대. `utcnow_aware()` 가 정확히 그 시그니처 |
| import 누락으로 `NameError` | 낮음 | pytest 회귀 (전체 39+ 케이스) 가 즉시 잡음 |

---

## 8. 결정 사항 (확정)

- [x] 헬퍼 파일: `app/core/datetime.py`
- [x] 헬퍼 이름: `utcnow_aware`
- [x] 헬퍼는 인자 없는 함수 (콜러블), 매 호출 시 `datetime.now(UTC)` 반환
- [x] 모델 5쌍 × 2파일 = 10 곳 모두 치환
- [x] 헬퍼 단위 테스트는 `tests/core/test_datetime_helper.py` 신규 파일에 추가
- [x] `app/core/security.py` 의 `datetime.now(UTC)` 직접 호출은 변경하지 않음 (즉시 평가 의도)

---

## 9. 참고

- PR #8 PRD §4.2 "lambda 반복 vs 헬퍼" (옵션 β 후속 분리 결정)
- [HANDOFF]세션_이어가기.md §6 마스터 목록 "lambda 10곳 → `utcnow_aware()` 헬퍼 추출"
- `tests/core/test_datetime_handling.py` — 모델 단위 timezone-aware 동작 검증 (유지)
