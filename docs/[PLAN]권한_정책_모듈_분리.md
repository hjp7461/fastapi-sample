# [PLAN] 권한 정책 모듈 분리 (`app/api/permissions.py`)

| 항목 | 내용 |
| --- | --- |
| 연관 PRD | `docs/[PRD]권한_정책_모듈_분리.md` |
| 브랜치 | `feature/permissions-module-split` |
| 추정 작업량 | 소~중 (1~1.5 시간) |
| 채택 전략 | permissions.py 신규 + 2 함수 이관 + 2 라우터 import 갱신 + 기존 60 PASS 회귀 가드 |

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 최신, 60 PASS 기준선 확인
- [ ] `get_current_active_admin`, `get_self_or_admin` 호출처 grep 으로 정확 매트릭스 확인
- [ ] 새 브랜치 `feature/permissions-module-split` 생성

---

## 1. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout -b feature/permissions-module-split
```

### Step 2 — `app/api/permissions.py` 신규 작성

PRD §5.1 코드 그대로 + 매트릭스 docstring.

### Step 3 — `app/api/dependencies.py` 에서 2 함수 제거

`get_current_active_admin`, `get_self_or_admin` 정의 + 관련 import 정리.

### Step 4 — `app/user/router.py` import 갱신

```python
# Before
from app.api.dependencies import (
    get_current_active_admin,
    get_current_user,
    get_self_or_admin,
)

# After
from app.api.dependencies import get_current_user
from app.api.permissions import get_current_active_admin, get_self_or_admin
```

### Step 5 — `app/product/router.py` import 갱신

```python
# Before
from app.api.dependencies import (
    get_current_active_admin,
    get_current_user,
    get_optional_current_user,
)

# After
from app.api.dependencies import get_current_user, get_optional_current_user
from app.api.permissions import get_current_active_admin
```

### Step 6 — grep 가드 + 전체 회귀

```bash
# 이관된 함수가 dependencies.py 에서 import 되지 않음 확인
grep -rn "from app.api.dependencies import.*get_current_active_admin\|from app.api.dependencies import.*get_self_or_admin" app/

uv run pytest
# 기대: 60 PASS (변화 없음 — 신규 케이스 0)
```

### Step 7 — 커밋 + 푸시 + PR

```bash
git add -f docs/'[PRD]권한_정책_모듈_분리.md' docs/'[PLAN]권한_정책_모듈_분리.md'
git add app/api/permissions.py app/api/dependencies.py app/user/router.py app/product/router.py
git commit ...
git push -u origin feature/permissions-module-split
gh pr create ...
```

---

## 2. 산출물 체크리스트

| 산출물 | 위치 | 상태 |
| --- | --- | --- |
| PRD | `docs/[PRD]권한_정책_모듈_분리.md` | ✅ |
| PLAN | `docs/[PLAN]권한_정책_모듈_분리.md` | ✅ |
| permissions.py 신규 | `app/api/permissions.py` | ⬜ |
| dependencies.py 2 함수 제거 | `app/api/dependencies.py` | ⬜ |
| user router import 갱신 | `app/user/router.py` | ⬜ |
| product router import 갱신 | `app/product/router.py` | ⬜ |

---

## 3. 회귀 방지

| 회귀 시나리오 | 가드 |
| --- | --- |
| ImportError (이관 누락) | 통합 테스트 60건 collection 단계에서 즉시 검출 |
| 순환 import | dependencies → permissions 단방향 (역방향 없음) — PRD §7 검증됨 |
| 권한 가드 동작 변경 | 통합 테스트 60건이 admin/self/anon 매트릭스 검증 |
| 호출처 외 deprecated 함수 사용 | grep 가드로 0건 확인 |

---

## 4. 롤백

단일 머지 revert. 의미 변경 0 이므로 안전.

---

## 5. 후속 작업 후보

- 가드 함수 이름 변경 (`require_admin`, `require_self_or_admin` 등) — 큰 영향
- 정책 함수 계층 신설 (`can_view_full_product` 등 비즈니스 룰) — 옵션 B 부활 시
- `app/core/permissions.py` 로 승격 (다른 패키지에서 사용 시) — 시점 도래 시
- `staff_or_admin` 가드 도입 (PR #19 후속 — staff 변경 권한 허용 정책 결정 후)

---

## 6. 참고

- PRD: `docs/[PRD]권한_정책_모듈_분리.md`
- `app/api/dependencies.py`, `app/user/router.py`, `app/product/router.py`
