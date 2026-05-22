# [PLAN] `utcnow_aware()` 헬퍼 추출

| 항목 | 내용 |
| --- | --- |
| 연관 PRD | `docs/[PRD]utcnow_aware_헬퍼_추출.md` |
| 브랜치 | `feature/utcnow-aware-helper` |
| 추정 작업량 | 소 (≤ 30 분, 구현 + 테스트 + 검증) |
| 채택 전략 | `app/core/datetime.py` 신규 + 모델 10 곳 치환 |

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 기준 최신 상태에서 `feature/utcnow-aware-helper` 브랜치 생성
- [ ] `uv run pytest` 현재 39/39 PASS, deprecation warning 0 건 기준선 확인
- [ ] `grep -rn "lambda: datetime.now(UTC)" app/` 으로 치환 대상 10 곳 사전 확인
  - `app/user/models.py` 5 곳 (line 29, 32, 36, 39, 40)
  - `app/product/models.py` 5 곳 (line 31, 34, 38, 41, 42)

---

## 1. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout main
git pull --ff-only origin main
git checkout -b feature/utcnow-aware-helper
```

### Step 2 — 헬퍼 모듈 추가 (`app/core/datetime.py`)

```python
"""시간 관련 공통 헬퍼."""
from datetime import datetime, UTC


def utcnow_aware() -> datetime:
    return datetime.now(UTC)
```

**검증**

```bash
uv run python -c "from app.core.datetime import utcnow_aware; print(utcnow_aware())"
# 출력: 2026-05-23 ... +00:00 형태 (tzinfo 포함)
```

### Step 3 — 헬퍼 단위 테스트 추가 (`tests/core/test_datetime_helper.py`)

```python
"""`utcnow_aware()` 단위 테스트."""
from datetime import UTC, datetime

from app.core.datetime import utcnow_aware


def test_utcnow_aware_is_timezone_aware():
    now = utcnow_aware()
    assert now.tzinfo is not None
    assert now.utcoffset() == datetime.now(UTC).utcoffset()


def test_utcnow_aware_is_callable_default_factory():
    factory = utcnow_aware
    result = factory()
    assert isinstance(result, datetime)
    assert result.tzinfo is not None
```

**검증**

```bash
uv run pytest tests/core/test_datetime_helper.py -v
```

### Step 4 — `app/user/models.py` 치환

```python
# Before
from datetime import datetime, UTC
# ...
default_factory=lambda: datetime.now(UTC),
default=lambda: datetime.now(UTC),
onupdate=lambda: datetime.now(UTC),

# After
from datetime import datetime  # UTC import 제거
from app.core.datetime import utcnow_aware
# ...
default_factory=utcnow_aware,
default=utcnow_aware,
onupdate=utcnow_aware,
```

**검증**

```bash
uv run pytest tests/user/ tests/core/test_datetime_handling.py -v
```

### Step 5 — `app/product/models.py` 치환

`app/user/models.py` 와 동일 패턴 적용.

**검증**

```bash
uv run pytest tests/product/ tests/core/test_datetime_handling.py -v
```

### Step 6 — 전체 회귀

```bash
uv run pytest
# 기대: 39 + 2 = 41 PASS, warning 0
```

```bash
grep -rn "lambda: datetime.now(UTC)" app/
# 기대: 출력 없음
```

### Step 7 — 커밋 + 푸시 + PR

```bash
git add -f docs/'[PRD]utcnow_aware_헬퍼_추출.md' docs/'[PLAN]utcnow_aware_헬퍼_추출.md'
git add app/core/datetime.py app/user/models.py app/product/models.py tests/core/test_datetime_helper.py
git status
git commit -m "$(cat <<'EOF'
refactor(core): lambda 10곳 → `utcnow_aware()` 헬퍼 추출

PR #8 §4.2 옵션 β 후속. 모델 두 곳에 동일한 `lambda: datetime.now(UTC)` 가
10번 반복되던 부분을 명명된 헬퍼로 통합한다.

- app/core/datetime.py 신규: `utcnow_aware()` (timezone-aware UTC 반환)
- app/user/models.py: 5곳 lambda → utcnow_aware
- app/product/models.py: 5곳 lambda → utcnow_aware
- tests/core/test_datetime_helper.py: 헬퍼 단위 테스트 2건

모델 동작·DB 스키마·외부 API 모두 불변. 가독성 향상과 향후 시간 소스
교체 지점 단일화 효과.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push -u origin feature/utcnow-aware-helper
gh pr create --title "refactor(core): lambda 10곳 → utcnow_aware() 헬퍼 추출" --body "$(cat <<'EOF'
## 요약

PR #8 §4.2 에서 옵션 β 로 명시한 후속 작업. `lambda: datetime.now(UTC)` 가 모델 두 곳에 10번 반복되던 부분을 `app/core/datetime.py` 의 `utcnow_aware()` 헬퍼로 통합한다.

- 문서: `docs/[PRD]utcnow_aware_헬퍼_추출.md`, `docs/[PLAN]utcnow_aware_헬퍼_추출.md`

## 변경 매트릭스

| 영역 | 변경 |
| --- | --- |
| `app/core/datetime.py` | 신규 — `utcnow_aware()` 헬퍼 |
| `app/user/models.py` | lambda 5곳 → `utcnow_aware`, 불필요한 `UTC` import 제거 |
| `app/product/models.py` | lambda 5곳 → `utcnow_aware`, 불필요한 `UTC` import 제거 |
| `tests/core/test_datetime_helper.py` | 신규 — 헬퍼 단위 테스트 2건 |

## 테스트 플랜 (리뷰어용)

```bash
uv run pytest                                    # 41 PASS, warning 0
grep -rn "lambda: datetime.now(UTC)" app/        # 출력 없음
```

## 비목적

- 시간 소스 자체의 교체 (모킹/freezegun) — 별도 PR
- `app/core/security.py` 의 `datetime.now(UTC)` 직접 호출 — 의도된 즉시 평가
- DI 컨테이너 와이어링 `Depends(lambda: Container...)` lambda — datetime 무관, 별도 청소 후보

## 후속

없음. `app/core/datetime.py` 가 시간 정책 단일 지점이 되므로 향후 모킹 인프라/정밀도 변경이 필요할 때 한 곳만 손대면 된다.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## 2. 산출물 체크리스트

| 산출물 | 위치 | 상태 |
| --- | --- | --- |
| PRD | `docs/[PRD]utcnow_aware_헬퍼_추출.md` | ✅ (이미 작성) |
| PLAN | `docs/[PLAN]utcnow_aware_헬퍼_추출.md` | ✅ (본 파일) |
| 헬퍼 모듈 | `app/core/datetime.py` | ⬜ |
| 모델 치환 (user) | `app/user/models.py` | ⬜ |
| 모델 치환 (product) | `app/product/models.py` | ⬜ |
| 헬퍼 단위 테스트 | `tests/core/test_datetime_helper.py` | ⬜ |

---

## 3. 테스트 케이스 (신규)

| # | 케이스 | 위치 |
| --- | --- | --- |
| 1 | `utcnow_aware()` 가 timezone-aware datetime 을 반환 (tzinfo not None, UTC 오프셋) | `tests/core/test_datetime_helper.py::test_utcnow_aware_is_timezone_aware` |
| 2 | `utcnow_aware` 가 인자 0 콜러블이며 `default_factory` 와 호환 (호출 시 `datetime` 인스턴스 반환, tzinfo 포함) | `tests/core/test_datetime_helper.py::test_utcnow_aware_is_callable_default_factory` |

---

## 4. 회귀 방지

| 회귀 시나리오 | 가드 |
| --- | --- |
| 모델 생성 시 `created_at`/`updated_at` 이 naive datetime 으로 변함 | 기존 `tests/core/test_datetime_handling.py::test_default_factory_returns_timezone_aware` |
| `updated_at` 이 UPDATE 시 자동 갱신되지 않음 (onupdate 콜러블 호환성) | 기존 `tests/core/test_datetime_handling.py::test_user_updated_at_changes_on_update` |
| 다른 곳에 새 `lambda: datetime.now(UTC)` 가 추가됨 | PR 본문 / 본 PLAN 의 `grep` 가드. CI 통합은 별도 PR (필요 시) |

---

## 5. 롤백

본 변경은 의미적으로 동일한 리팩토링이므로 롤백 시 1 커밋 revert 로 충분.

```bash
git revert <merge-commit-sha>
```

---

## 6. 후속 작업 후보

- (없음 — PRD §3 비목적 참조)
- 단, `Depends(lambda: Container.user_service())` 형태의 DI 와이어링 lambda 청소는 별도 후보로 마스터 목록 추가 검토 가능 (datetime 무관).

---

## 7. 참고

- `docs/[PRD]utcnow_aware_헬퍼_추출.md`
- `docs/[PRD]잔여_deprecation_일괄_정리.md` §4.2
- `tests/core/test_datetime_handling.py`
