# UserRole enum 정합성 개선 구현 Plan

| 항목         | 내용                                                                 |
| ------------ | -------------------------------------------------------------------- |
| 작성일       | 2026-05-22                                                           |
| 연관 PRD     | [`[PRD]UserRole_enum_정합성.md`](./[PRD]UserRole_enum_정합성.md)     |
| 상태         | 제안 (Draft)                                                         |
| 추정 작업량  | 약 1.5시간 (구현 + 테스트 + 검증)                                     |
| 채택 설계    | 권한 계층 메서드 명시 (`is_admin` + `is_staff_or_above`)              |
| 시드 표현    | `UserRole.ADMIN.value` (옵션 β) 또는 enum 인스턴스 (옵션 γ) 혼용 가능 |

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 기준 최신 상태에서 `feature/userrole-enum` 브랜치 생성
- [ ] `uv run pytest` 현재 24/24 PASS 확인
- [ ] PRD §1.1 권한 계층 (CUSTOMER ⊂ STAFF ⊂ ADMIN) 의도 확인
- [ ] PRD §4.1 / §4.2 / §5.4 확정 사항 확인

---

## 1. 작업 분해

### Step 1. 도메인 메서드 추가 및 리팩토링

**대상**: `app/user/domain.py`

**변경 내용**

1. `User.is_admin()` 신규 추가 — ADMIN 전용 체크
2. `User.is_staff_or_above()` 신규 추가 — STAFF 이상 체크 (권한 계층 명시)
3. 기존 `User.can_manage_products()` 의 내부 구현을 `is_staff_or_above()` 위임으로 리팩토링 (시그니처/반환값 동일)

```python
# app/user/domain.py (변경 후 — 메서드 부분)
@dataclass
class User:
    ...

    def is_admin(self) -> bool:
        """ADMIN 전용 권한 보유 여부."""
        return self.role == UserRole.ADMIN

    def is_staff_or_above(self) -> bool:
        """STAFF 이상 권한 보유 여부 (계층 의도: STAFF ⊂ ADMIN)."""
        return self.role in (UserRole.STAFF, UserRole.ADMIN)

    def can_manage_products(self) -> bool:
        """상품 관리 권한. STAFF 이상이면 가능."""
        return self.is_staff_or_above()
```

**검증**

```bash
/usr/local/bin/mise exec -- uv run python -c "
from app.user.domain import User, UserRole
assert User(role=UserRole.ADMIN).is_admin() is True
assert User(role=UserRole.STAFF).is_admin() is False
assert User(role=UserRole.ADMIN).is_staff_or_above() is True
assert User(role=UserRole.STAFF).is_staff_or_above() is True
assert User(role=UserRole.CUSTOMER).is_staff_or_above() is False
assert User(role=UserRole.STAFF).can_manage_products() is True
print('OK')
"
```

---

### Step 2. 권한 검사 호출자 변경

**대상**: `app/api/dependencies.py`, `app/user/router.py`

**변경 내용**

```python
# app/api/dependencies.py:66 (변경 전)
if current_user.role != "admin":

# (변경 후)
if not current_user.is_admin():
```

```python
# app/user/router.py:90 (변경 전)
if current_user.id != user_id and current_user.role != "admin":

# (변경 후)
if current_user.id != user_id and not current_user.is_admin():
```

> 두 파일 모두 import 는 변경 없음 — `User` 타입이 이미 의존성 반환 타입으로 통과되고 있음.

**검증**

```bash
uv run pytest tests/user/test_router.py::test_access_admin_endpoint_as_admin \
              tests/user/test_router.py::test_access_admin_endpoint_as_regular_user \
              tests/user/test_router.py::test_get_other_user_as_regular_user \
              tests/user/test_router.py::test_get_other_user_as_admin \
              -v --tb=short
```

권한 분기 케이스 4건 PASS 확인.

---

### Step 3. 테스트 시드 enum 사용으로 정리

**대상**: `tests/conftest.py`, `tests/product/test_router.py`

#### 3.1 `tests/conftest.py`

```python
# (변경 전)
user_data = {
    "username": "adminuser",
    "email": "admin@example.com",
    "password": "adminpassword",
    "role": "admin",
}
db_user = UserModel(
    ...
    role=user_data["role"],
)

# (변경 후)
user_data = {
    "username": "adminuser",
    "email": "admin@example.com",
    "password": "adminpassword",
    "role": UserRole.ADMIN.value,
}
db_user = UserModel(
    ...
    role=UserRole.ADMIN,
)
```

import 추가 (파일 상단의 기존 import 그룹에 합류):

```python
from app.user.domain import UserRole
```

> dict 의 `role` 값은 `.value` (string), `UserModel` 직접 인스턴스화 시는 enum 인스턴스. SQLModel 의 `Enum(UserRole)` 컬럼은 양쪽 모두 받음.

#### 3.2 `tests/product/test_router.py`

```python
# (변경 전 — line 27)
"role": "admin",  # 관리자 역할 지정

# (변경 후)
"role": UserRole.ADMIN.value,  # 관리자 역할 지정
```

import 추가:

```python
from app.user.domain import UserRole
```

**검증**

```bash
uv run pytest -k "admin" --tb=short
```

admin 시드를 사용하는 모든 테스트 PASS 확인.

---

### Step 4. 신규 회귀 가드 테스트 추가

**대상**: `tests/user/test_role.py` (신규)

```python
"""UserRole / User 도메인 권한 메서드 회귀 가드.

권한 계층 (CUSTOMER ⊂ STAFF ⊂ ADMIN) 의 의도가 코드에 정확히 표현되어 있는지 검증.
"""
from app.user.domain import User, UserRole


def test_user_is_admin():
    """is_admin 은 ADMIN 만 True."""
    assert User(role=UserRole.ADMIN).is_admin() is True
    assert User(role=UserRole.STAFF).is_admin() is False
    assert User(role=UserRole.CUSTOMER).is_admin() is False


def test_user_is_staff_or_above():
    """is_staff_or_above 는 ADMIN, STAFF 둘 다 True (계층 의도: STAFF ⊂ ADMIN)."""
    assert User(role=UserRole.ADMIN).is_staff_or_above() is True
    assert User(role=UserRole.STAFF).is_staff_or_above() is True
    assert User(role=UserRole.CUSTOMER).is_staff_or_above() is False


def test_can_manage_products_delegates_to_staff_or_above():
    """can_manage_products 는 is_staff_or_above 와 동일한 결과를 반환 (위임)."""
    for role in UserRole:
        user = User(role=role)
        assert user.can_manage_products() == user.is_staff_or_above()
```

> 이 파일은 동기 (`def`) 테스트로 충분 — 도메인 객체 메서드만 검증하므로 `async`/`pytest-asyncio` 불요. pytest-asyncio 의 `auto` 모드는 `async def` 만 자동 처리하므로 충돌 없음.

**검증**

```bash
uv run pytest tests/user/test_role.py -v --tb=short
```

3 케이스 PASS 확인.

---

### Step 5. 시퀀스 다이어그램 노트 갱신

**대상**: `docs/diagram/인증_및_권한.md`, `docs/diagram/사용자_프로필.md`

#### 5.1 `docs/diagram/인증_및_권한.md`

핵심 포인트 섹션의 다음 라인을 갱신.

```
변경 전:
- **`role` 비교는 문자열 매칭** (`"admin"`) 이다. `app/user/domain.py` 의 `UserRole` enum 과의 정합성은 별도 점검 필요 (PRD 잔여 이슈 #1).

변경 후:
- **`role` 비교는 도메인 메서드 (`User.is_admin()`) 로 캡슐화** 되어 있다. 권한 계층 (STAFF ⊂ ADMIN) 은 `User.is_staff_or_above()` 로 표현. 기능 단위 권한 (예: `can_manage_products`) 은 계층 메서드에 위임한다.
```

다이어그램 본문의 `alt user.role != "admin"` 표기를 `alt not user.is_admin()` 로 변경.

#### 5.2 `docs/diagram/사용자_프로필.md`

핵심 포인트의 마지막 라인 갱신.

```
변경 전:
- `role == "admin"` 문자열 비교는 `app/api/dependencies.py:66` 의 admin 가드와 동일한 패턴. enum 정합성은 별도 이슈.

변경 후:
- 권한 비교는 도메인 메서드 (`User.is_admin()`) 로 표현됨. STAFF ⊂ ADMIN 계층은 `User.is_staff_or_above()` 로 분리.
```

다이어그램 본문의 `alt current_user.id != user_id AND role != "admin"` 를 `alt user_id != current_user.id AND not current_user.is_admin()` 로 변경.

---

### Step 6. 전체 회귀 검증

```bash
uv run pytest -v
uv run pytest --cov=app/user --cov-report=term-missing
```

- 기존 24 + 신규 3 = **27 PASS** 확인
- `app/user/domain.py` 의 신규 메서드 (`is_admin`, `is_staff_or_above`) 가 100% 커버되는지 확인
- `app/api/dependencies.py:66`, `app/user/router.py:90` 의 변경된 분기 둘 다 통과 케이스 + 미통과 케이스 커버 확인

---

## 2. 산출물 체크리스트

- [ ] `app/user/domain.py` — `is_admin`, `is_staff_or_above` 메서드 추가, `can_manage_products` 위임 리팩토링
- [ ] `app/api/dependencies.py:66` — `not user.is_admin()` 으로 교체
- [ ] `app/user/router.py:90` — `not current_user.is_admin()` 으로 교체
- [ ] `tests/conftest.py` — admin 시드를 enum 사용으로 변경 + `UserRole` import
- [ ] `tests/product/test_router.py` — admin 시드를 enum 사용으로 변경 + `UserRole` import
- [ ] `tests/user/test_role.py` (신규) — 3 케이스
- [ ] `docs/diagram/인증_및_권한.md`, `docs/diagram/사용자_프로필.md` — 노트/분기 표기 갱신
- [ ] `uv run pytest -v` **27/27 PASS**

---

## 3. 테스트 케이스 (완료 판정 기준)

다음 케이스가 모두 PASS 해야 한다.

### 3.1 신규 권한 메서드 단위 테스트 (3 케이스)

| #   | 테스트                                                  | 입력 (role)            | 기대 결과                                          |
| --- | ------------------------------------------------------- | ---------------------- | -------------------------------------------------- |
| 1   | `test_user_is_admin`                                    | ADMIN / STAFF / CUSTOMER | True / False / False                              |
| 2   | `test_user_is_staff_or_above`                           | ADMIN / STAFF / CUSTOMER | True / True / False                               |
| 3   | `test_can_manage_products_delegates_to_staff_or_above`  | 모든 role             | `can_manage_products() == is_staff_or_above()`     |

### 3.2 권한 분기 통합 테스트 (기존, PASS 유지)

| 테스트                                                          | 호출자                            | 기대        |
| --------------------------------------------------------------- | --------------------------------- | ----------- |
| `test_access_admin_endpoint_as_admin`                           | admin 토큰 → `GET /users/`        | 200         |
| `test_access_admin_endpoint_as_regular_user`                    | 일반 토큰 → `GET /users/`         | 403         |
| `test_get_other_user_as_regular_user`                           | 일반 토큰 → `GET /users/{타인}`   | 403         |
| `test_get_other_user_as_admin`                                  | admin 토큰 → `GET /users/{타인}`  | 200         |
| 상품 관리 admin 케이스 4건 (`create/update/update_inventory/delete`) | admin 토큰 → 상품 라우터    | 정상 동작   |

### 3.3 회귀 — 기존 24 케이스 (PASS 유지)

전체 `uv run pytest` 24 케이스 PASS 가 유지되어야 한다.

---

## 4. 권한 계층 검증 매트릭스

도메인 의도가 코드에서 일관되게 표현되었는지 검증.

| role     | `is_admin()` | `is_staff_or_above()` | `can_manage_products()` | `get_current_active_admin` 통과 |
| -------- | ------------ | --------------------- | ----------------------- | ------------------------------- |
| ADMIN    | True         | True                  | True                    | ✓                               |
| STAFF    | False        | True                  | True                    | ✗ (403)                         |
| CUSTOMER | False        | False                 | False                   | ✗ (403)                         |

> `can_manage_products()` 와 `is_staff_or_above()` 의 컬럼이 항상 같아야 함. Step 4 의 신규 테스트가 이를 명시적으로 검증.

---

## 5. 회귀 방지 체크리스트

PR 머지 전 모두 확인.

- [ ] `uv run pytest` **27/27 PASS**
- [ ] `git diff main` 결과에서 `"admin"` raw 문자열이 권한 검사 코드에 남아있지 않음
  - 검증 명령: `git diff main -- app/api/dependencies.py app/user/router.py | grep '"admin"'` → 출력 없어야 함
- [ ] `User.can_manage_products()` 의 시그니처/반환 타입이 변경되지 않음 (다른 호출자가 있을 경우 영향 없음)
- [ ] 기존 `test_user_role_to_string_compat` 같은 호환 검증 가드는 없지만, `UserRole.ADMIN == "admin"` 이 여전히 True 임은 enum 정의 자체에서 보장됨
- [ ] 다이어그램 mermaid 렌더링 확인

---

## 6. 롤백 전략

- 본 작업은 5 파일 변경 (프로덕션 3 + 테스트 2) + 신규 1 + 다이어그램 2.
- 별도 브랜치 (`feature/userrole-enum`) 에서 작업. 문제 시 `git checkout main` 으로 원복.
- 프로덕션 코드만 단독 revert 하려면 `git checkout HEAD -- app/user/domain.py app/api/dependencies.py app/user/router.py` 로 가능. 단 도메인 메서드를 없애면 호출자가 깨지므로 **반드시 3 파일을 함께 revert.**

---

## 7. 후속 작업 (별도 이슈 권장)

| #   | 항목                                                                                        | 권장 처리                                                                    |
| --- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 1   | 권한 분기를 의존성으로 추출 (`get_self_or_admin(user_id)`)                                  | 같은 패턴이 1곳 이상 추가 발생 시 클린업                                     |
| 2   | 권한 계층의 일반화 (`User.has_role(min_role)`)                                              | `is_staff_or_above` 외 추가 계층 체크가 필요해질 때 도입                     |
| 3   | `current_user.role` 직접 접근을 라우터에서 제거 (예외: `permissions.py` 같은 정책 모듈로 통합) | 권한 정책 모듈 별도 도입 검토                                                |
| 4   | Pydantic 응답에서 `role` 필드 직렬화 확인 (Enum → str 자동 변환 검증)                       | 본 PR 의 응답 회귀 테스트로 어느 정도 보장. 별도 명시 케이스는 향후 도입     |
| 5   | `audit log` (누가 admin 가드를 통과/실패했는지 기록)                                        | 별도 PRD                                                                     |

---

## 8. 참고

- 관련 PRD: [`[PRD]UserRole_enum_정합성.md`](./[PRD]UserRole_enum_정합성.md)
- 관련 다이어그램:
  - [`docs/diagram/인증_및_권한.md`](./diagram/인증_및_권한.md)
  - [`docs/diagram/사용자_프로필.md`](./diagram/사용자_프로필.md)
- 핵심 코드:
  - `app/user/domain.py:11 UserRole`
  - `app/user/domain.py:38 can_manage_products` (이미 존재 — 리팩토링 대상)
  - `app/api/dependencies.py:66`
  - `app/user/router.py:90`
- 선례:
  - PR #1 — `GET /users/` admin 가드 추가 (`"admin"` 문자열 비교를 처음 도입)
  - PR #2 — `GET /users/{user_id}` admin 가드 추가 (동일 패턴)
