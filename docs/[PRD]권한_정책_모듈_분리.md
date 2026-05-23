# [PRD] 권한 정책 모듈 분리 (`app/api/permissions.py`)

| 항목 | 내용 |
| --- | --- |
| 상태 | 제안 (Draft) |
| 작성일 | 2026-05-23 |
| 출처 | PR #4 §7-#3 후속, [HANDOFF] §6 마스터 목록 |
| 분류 | 구조 (계층 책임 정리) |
| 추정 작업량 | 소~중 (1~1.5 시간, 파일 분할 + import 갱신 + 회귀) |

---

## 1. 배경

### 1.1 현재 분포

`app/api/dependencies.py` 한 파일이 **인증** 과 **권한** 의존성을 모두 보유.

```python
# app/api/dependencies.py — 의존성 4종
async def get_current_user(...)             # 인증
async def get_optional_current_user(...)    # 인증 (옵셔널)
async def get_current_active_admin(...)     # 권한 (admin 가드)
async def get_self_or_admin(user_id, ...)   # 권한 (self+admin 가드)
```

### 1.2 문제 / 후속 의도

PR #4 §7-#3: "의존성 5+ 시 권한 정책 모듈 신설 검토" → 임계치 근처. 향후 PR #19 후속 (staff 변경 권한), audit log 가드 등이 추가될 것으로 예상.

현재 구조의 문제는 **계층 책임 혼재**:
- 인증 = "누구인지 확인" (요청자 신원)
- 권한 = "허용되는 동작인지 결정" (요청 컨텍스트 + 정책)

두 책임이 같은 파일에 있어 가드가 늘어날수록 의도 파악이 어려워진다.

### 1.3 본 PR 의 위치

분리 시점을 잡아서 **인증 (dependencies.py)** vs **권한 (permissions.py)** 모듈 경계를 명시. 향후 신규 가드는 자연스럽게 permissions.py 에 누적.

---

## 2. 목적

1. `app/api/permissions.py` 신규 — 권한 가드 의존성 전용.
2. `get_current_active_admin`, `get_self_or_admin` 을 permissions.py 로 이관.
3. `dependencies.py` 는 인증 (`get_current_user`, `get_optional_current_user`) 만 보유.
4. 호출처 (user/router.py, product/router.py) 의 import 갱신 — 의존성 그래프 / 동작은 그대로.
5. permissions.py docstring 에 **권한 가드 매트릭스 + 신규 가드 추가 가이드** 명시.
6. 외부 동작 / 응답 / DB / 테스트 결과 모두 불변.

---

## 3. 비목적

- 가드 함수 이름 변경 (예: `require_admin`, `require_self_or_admin`) — 호출처 영향이 커 별도 후속.
- 정책 함수 계층 신설 (`can_view_full_product` 등 비즈니스 룰) — 옵션 B 였지만 사용자가 옵션 A 채택. over-engineering 회피.
- User 도메인의 `is_admin` / `is_staff_or_above` / `can_manage_products` 이전 — 도메인 책임이라 그대로.
- 새 권한 가드 도입 (staff_or_admin 등) — 본 PR 은 분리만, 신규는 별도.
- 권한 정책의 문서화 (docs/POLICY.md) — 옵션 C 의 별도 선택지로 남김.

---

## 4. 성공 기준

- [ ] `app/api/permissions.py` 신규 생성.
- [ ] `get_current_active_admin`, `get_self_or_admin` 이 permissions.py 로 이관.
- [ ] `dependencies.py` 에서 두 함수 제거 (deprecation 별칭은 두지 않음 — 호출처 직접 갱신).
- [ ] `app/user/router.py` 와 `app/product/router.py` 의 import 갱신 (`from app.api.permissions import ...`).
- [ ] permissions.py 의 모듈 docstring 에 다음 명시:
  - 권한 가드 매트릭스 (함수명 / 통과 조건 / 사용처)
  - 신규 가드 추가 가이드 (네이밍 / 위치 / 회귀 가드)
- [ ] 기존 60 PASS 유지 (의미 변경 0, import 경로만 변경).
- [ ] `grep -rn "from app.api.dependencies import" app/` 결과에 `get_current_active_admin` / `get_self_or_admin` 0건.
- [ ] OpenAPI 스펙 변화 없음.

---

## 5. 설계

### 5.1 `app/api/permissions.py` (신규)

```python
"""권한 가드 의존성.

라우터에서 사용하는 권한 가드를 한 곳에 모은다. 인증 (요청자 신원 확인) 은
`app/api/dependencies.py` 의 `get_current_user` / `get_optional_current_user`
가 담당하고, 본 모듈은 그 위에 **누가 무엇을 할 수 있는가** 정책을 표현.

## 권한 가드 매트릭스

| 가드 | 통과 조건 | 실패 응답 | 주요 사용처 |
| --- | --- | --- | --- |
| `get_current_active_admin` | `current_user.is_admin()` | 403 | POST/PUT/DELETE /products/*, GET /users/ |
| `get_self_or_admin` | `current_user.id == user_id` 또는 admin | 403 | GET /users/{id} |

## 신규 가드 추가 가이드

- 네이밍: `get_<역할/조건>_<목적>` (예: `get_staff_or_admin`, `get_owner_or_admin`)
- 위치: 본 파일에 함수 정의 + 매트릭스에 한 줄 추가
- 회귀 가드: 통합 테스트로 통과 / 실패 양쪽 검증 (예: `test_*_as_admin`, `test_*_as_regular_user`)
- 도메인 메서드 활용: `User.is_admin()`, `User.is_staff_or_above()` 등 — 가드는 도메인 정책을 호출만
"""
from fastapi import Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.user.domain import User


async def get_current_active_admin(
        current_user: User = Depends(get_current_user),
) -> User:
    """현재 인증된 사용자가 관리자인지 확인합니다."""
    if not current_user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


async def get_self_or_admin(
        user_id: int,
        current_user: User = Depends(get_current_user),
) -> User:
    """본인 또는 관리자만 통과하는 권한 가드.

    `user_id` 는 라우터의 path parameter 와 같은 이름으로 FastAPI 가 자동 주입.

    - 본인 (`current_user.id == user_id`) → 통과
    - 관리자 (`current_user.is_admin()`) → 통과
    - 그 외 → 403 Forbidden

    권한 검사는 자원의 존재 확인보다 먼저 평가되어 ID 열거 공격을 차단한다.
    """
    if current_user.id != user_id and not current_user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user
```

### 5.2 `app/api/dependencies.py` 변경

- `get_current_active_admin`, `get_self_or_admin` 정의 제거.
- 인증 의존성 (`get_current_user`, `get_optional_current_user`) 만 남김.
- import 정리: `HTTPException`, `status` 는 여전히 인증에서 사용 — 유지.

### 5.3 호출처 import 갱신

**`app/user/router.py`**

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

**`app/product/router.py`**

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

### 5.4 회귀 / 테스트

본 PR 은 import 경로 + 파일 분할만. 의미적 변경 0. 기존 60 PASS 그대로 통과해야 함.

신규 회귀 가드 불필요 — 통합 테스트 60건이 권한 가드의 동작을 이미 검증.

---

## 6. 영향

| 영역 | 영향 |
| --- | --- |
| `app/api/permissions.py` | **신규** — 권한 가드 의존성 + 매트릭스 docstring |
| `app/api/dependencies.py` | `get_current_active_admin`, `get_self_or_admin` 제거 |
| `app/user/router.py` | import 갱신 (2 함수 → permissions.py 에서) |
| `app/product/router.py` | import 갱신 (1 함수 → permissions.py 에서) |
| 외부 API / 응답 / DB / OpenAPI | **모두 불변** |
| 신규 테스트 | 불요 — 기존 60건이 회귀 가드 |

---

## 7. 리스크

| 리스크 | 가능성 | 대응 |
| --- | --- | --- |
| import 갱신 누락으로 ImportError | 낮음 | 통합 테스트 60건이 collection 단계에서 즉시 검출 |
| 순환 import (`permissions.py` ↔ `dependencies.py`) | 낮음 | permissions.py 가 dependencies.py 의 `get_current_user` 만 import — 단방향. 검증 ✓ |
| User 도메인 import 가 순환 유발 | 매우 낮음 | dependencies.py 도 이미 User import 중. permissions.py 도 동일 — 순환 없음 |
| 호출처 외부 패키지에서 deprecated 함수 import 시도 | 매우 낮음 | 본 프로젝트는 데모. 외부 의존성 없음 |

---

## 8. 결정 사항 (확정)

- [x] 모듈명: `app/api/permissions.py` (`authorization.py` 또는 `policies.py` 보다 짧고 명확)
- [x] 위치: `app/api/` (의존성에 가까움. core 로 승격은 후속 검토)
- [x] 이관 항목: `get_current_active_admin`, `get_self_or_admin` 만
- [x] `dependencies.py` 는 인증만 유지 — deprecation 별칭 없음 (호출처 직접 갱신)
- [x] 가드 함수 이름 변경 (`require_*`) 은 별도 후속 (큰 영향)
- [x] User 도메인 메서드 (`is_admin`, `is_staff_or_above`) 는 그대로 도메인 책임
- [x] 정책 함수 계층 신설은 본 PR 비목적 (옵션 B 폐기)
- [x] permissions.py docstring 에 매트릭스 + 신규 가드 추가 가이드 포함

---

## 9. 참고

- `docs/[PRD]UserRole_enum_정합성.md` (PR #4) — `is_admin`, `is_staff_or_above` 도메인 메서드 도입
- `docs/[PRD]권한_분기_의존성_추출.md` (PR #10) — `get_self_or_admin` 도입
- `docs/[PRD]Product_조회_컨텍스트_분리.md` (PR #19) — `get_optional_current_user` 도입
- `app/api/dependencies.py`, `app/user/domain.py`
