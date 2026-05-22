# UserRole enum 정합성 개선 PRD

| 항목       | 내용                                                                 |
| ---------- | -------------------------------------------------------------------- |
| 작성일     | 2026-05-22                                                           |
| 작성자     | conner                                                               |
| 상태       | 제안 (Draft)                                                         |
| 도메인     | User (모든 권한 검사 경로에 영향)                                    |
| 대상 범위  | 권한 비교 / 테스트 시드의 `"admin"` 문자열 4개 위치                  |
| 관련 발견  | 테스트 아키텍처 PRD §7-#3, 사용자 조회 인증 PRD §7-#2 의 잔여 이슈   |

---

## 1. 배경

### 1.1 권한 모델 (도메인 의도)

본 프로젝트는 **계층형 권한 모델** 을 채택한다.

```
CUSTOMER ⊂ STAFF ⊂ ADMIN
```

- `ADMIN` 은 `STAFF` 의 모든 권한을 포함한다. (manager 가 STAFF 인 동시에 ADMIN 권한도 가질 수 있는 운영 시나리오)
- "STAFF 이상" 권한 체크는 **ADMIN 도 통과** 시켜야 한다.
- "ADMIN 전용" 권한 체크는 **ADMIN 만** 통과 시킨다.

이 의도에 따라 현재 도메인은 다음과 같이 정의되어 있다.

```python
# app/user/domain.py:11
class UserRole(str, Enum):
    ADMIN = "admin"
    STAFF = "staff"
    CUSTOMER = "customer"

@dataclass
class User:
    ...
    def can_manage_products(self) -> bool:
        # STAFF 이상 — 상품 관리는 STAFF 도 가능
        return self.role in (UserRole.ADMIN, UserRole.STAFF)
```

### 1.2 문제 — 응용/인프라 계층의 enum 우회

권한 검사 코드와 테스트 시드는 **enum 이 아니라 raw 문자열** (`"admin"`) 로 비교/할당하고 있다.

| 위치                                       | 코드                                          | 평가                                  |
| ------------------------------------------ | --------------------------------------------- | ------------------------------------- |
| `app/api/dependencies.py:66`               | `if current_user.role != "admin":`            | 권한 가드의 핵심 — 문자열 비교        |
| `app/user/router.py:90`                    | `current_user.role != "admin"`                | 본인/관리자 분기 (PR #2 추가)         |
| `tests/conftest.py:137,144`                | `"role": "admin"`, `role=user_data["role"]`   | admin 시드 데이터                     |
| `tests/product/test_router.py:27`          | `"role": "admin"`                             | admin 사용자 생성 페이로드            |

`UserRole` 이 `str` 을 상속한 enum 이라 `UserRole.ADMIN == "admin"` 이 **True 로 평가** 되어 동작은 한다. 하지만 다음 문제가 있다.

1. **타입 안전성 부족**: `current_user.role != "admn"` 같은 오타가 정적 분석으로 잡히지 않는다. enum 비교라면 IDE/mypy 가 즉시 경고.
2. **새 role 추가 시 누락 위험**: enum 멤버 변경 시 IDE refactoring 이 raw 문자열을 갱신하지 못한다.
3. **Clean Architecture 위반**: 도메인이 정의한 어휘를 응용/인프라 계층이 무시하고 있음.
4. **유지보수성**: `"admin"` 의 의미를 알려면 컨텍스트를 추적해야 한다. `UserRole.ADMIN` 은 자체 문서화.
5. **권한 계층의 암묵적 표현**: `can_manage_products` 의 멤버 리스트 (`{ADMIN, STAFF}`) 는 "상품 관리 권한이 누구에게 있는지" 만 보여주고 "STAFF 이상" 이라는 계층 의미를 코드로 표현하지 않는다.

---

## 2. 목적

- 권한 비교를 **도메인의 어휘 (enum + 메서드) 로 일관** 한다.
- 오타와 타입 오류를 정적 분석으로 잡을 수 있게 한다.
- 권한 정책을 변경할 때 한 곳만 수정하면 되도록 캡슐화한다.
- **권한 계층 (STAFF ⊂ ADMIN) 을 도메인 메서드 이름으로 명시적으로 드러낸다.**
- 테스트 시드도 동일 패턴으로 정렬한다.

### 비목적

- 새로운 권한 정책 도입 (예: 새 role 추가, 기존 정책 변경) — 본 PRD 는 현재 정책을 코드로 더 잘 표현하는 데 집중.
- 권한 분기를 의존성으로 추출 (`get_self_or_admin`) — 본 PRD 와 직교적인 리팩토링이므로 별도 이슈.
- audit log, UserResponse 마스킹 등 다른 사용자 관련 후속 작업.
- 권한 계층의 일반화 (`has_role(min_role)` 형태) — 사용처가 늘어나면 도입 검토.

---

## 3. 성공 기준

| 지표                                                                                   | 목표값                |
| -------------------------------------------------------------------------------------- | --------------------- |
| 권한 검사 코드의 `"admin"` raw 문자열 사용                                             | 0건                   |
| 테스트 시드의 `"admin"` raw 문자열 사용                                                | 0건 (또는 호환 유지 — §5 검토) |
| 도메인 메서드 `User.is_admin()` / `User.is_staff_or_above()` 도입                      | 2건 (신규 추가)       |
| `User.can_manage_products()` 가 `is_staff_or_above()` 위임으로 리팩토링                | 1건                   |
| `app/api/dependencies.py` / `app/user/router.py` 에서 도메인 메서드 호출               | 2건                   |
| 기존 회귀 테스트                                                                       | 24/24 PASS 유지       |
| 추가 회귀 가드 (도메인 메서드의 권한 계층 검증)                                        | 신규 3 케이스         |

---

## 4. 설계 옵션

### 4.1 권한 비교 표현 — **확정: 권한 계층 메서드 명시**

도메인 의도(STAFF ⊂ ADMIN)를 메서드 이름으로 드러내는 방향으로 확정.

```python
# app/user/domain.py
@dataclass
class User:
    ...

    def is_admin(self) -> bool:
        """ADMIN 전용 권한 보유 여부."""
        return self.role == UserRole.ADMIN

    def is_staff_or_above(self) -> bool:
        """STAFF 이상 권한 보유 여부 (계층 의도 명시: STAFF ⊂ ADMIN)."""
        return self.role in (UserRole.STAFF, UserRole.ADMIN)

    def can_manage_products(self) -> bool:
        """상품 관리 권한. STAFF 이상이면 가능."""
        return self.is_staff_or_above()
```

**채택 이유**

- 권한 계층 (STAFF ⊂ ADMIN) 이 메서드 이름에서 명시적으로 드러난다.
- 향후 "STAFF 이상" 권한 체크가 필요한 새 기능이 추가될 때 재사용 가능 (현재는 `can_manage_products` 만 사용 중이지만 도메인 의도는 더 일반적).
- 기존 `can_manage_products` 는 _기능_ 메서드, `is_staff_or_above` 는 _계층_ 메서드로 역할 분리 — 기능 메서드가 계층 메서드를 위임.
- 검토한 대안:
  - **순서 비교 가능한 enum** (`role >= UserRole.STAFF`): 가장 유연하나 도메인 메서드가 안 보이고 enum 이 너무 많은 일을 함. 도입 보류.
  - **기능별 메서드만** (`is_admin`, `can_manage_products`): 계층 의도가 코드에 안 드러남. 도입 보류.

### 4.2 테스트 시드 표현 옵션

| 옵션 | 표현                                                | 비고                                                                       |
| ---- | --------------------------------------------------- | -------------------------------------------------------------------------- |
| α    | `"role": "admin"` (현재) 유지 + 모델 단에서 enum 변환 | SQLAlchemy `Enum(UserRole)` 컬럼이 문자열 → enum 변환을 자동 처리 — 동작함 |
| β    | `"role": UserRole.ADMIN.value` (**Recommended**)     | 의도가 명확. 향후 enum 값 변경 시 자동 추적                                |
| γ    | `"role": UserRole.ADMIN`                              | 가장 타입 안전. SQLAlchemy 가 enum 인스턴스를 받을 수 있는지 확인 필요     |

**권장: 옵션 β** — `.value` 사용으로 의도 명시 + 안전성 확보.

> γ 도 SQLModel 환경에서 동작하지만 dict 직렬화 단계에서 미묘한 차이가 있을 수 있으므로 안전한 β 채택. 직접 시드 시 (UserModel 인스턴스화) γ 도 OK.

---

## 5. 설계 상세

### 5.1 도메인 메서드 변경

§4.1 의 확정안에 따라 `User` 도메인 클래스에 두 개의 권한 메서드를 추가하고, 기존 `can_manage_products` 를 위임 형태로 리팩토링.

```python
# app/user/domain.py (변경 후)
@dataclass
class User:
    ...

    def is_admin(self) -> bool:
        """ADMIN 전용 권한 보유 여부."""
        return self.role == UserRole.ADMIN

    def is_staff_or_above(self) -> bool:
        """STAFF 이상 권한 보유 여부 (계층 의도 명시: STAFF ⊂ ADMIN)."""
        return self.role in (UserRole.STAFF, UserRole.ADMIN)

    def can_manage_products(self) -> bool:
        """상품 관리 권한. STAFF 이상이면 가능."""
        return self.is_staff_or_above()
```

> `can_manage_products` 는 외부 호출자 시그니처를 유지한 채 내부 구현만 위임으로 바꿈 → 기존 호출자 영향 없음.

### 5.2 호출자 변경

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

### 5.3 테스트 시드 변경

```python
# tests/conftest.py (변경 전)
user_data = {
    ...
    "role": "admin",
}
db_user = UserModel(
    ...
    role=user_data["role"],
)

# (변경 후)
user_data = {
    ...
    "role": UserRole.ADMIN.value,
}
db_user = UserModel(
    ...
    role=UserRole.ADMIN,
)
```

```python
# tests/product/test_router.py:27 (변경 전)
"role": "admin",

# (변경 후)
"role": UserRole.ADMIN.value,
```

import 추가:
```python
from app.user.domain import UserRole
```

### 5.4 회귀 가드 — 권한 계층 검증 단위 테스트

도메인 의도(STAFF ⊂ ADMIN) 가 코드로 정확히 표현되었는지 검증.

```python
# tests/user/test_role.py (신규)
from app.user.domain import User, UserRole


def test_user_is_admin():
    """is_admin 은 ADMIN 만 True."""
    assert User(role=UserRole.ADMIN).is_admin() is True
    assert User(role=UserRole.STAFF).is_admin() is False
    assert User(role=UserRole.CUSTOMER).is_admin() is False


def test_user_is_staff_or_above():
    """is_staff_or_above 는 ADMIN, STAFF 둘 다 True (계층: STAFF ⊂ ADMIN)."""
    assert User(role=UserRole.ADMIN).is_staff_or_above() is True
    assert User(role=UserRole.STAFF).is_staff_or_above() is True
    assert User(role=UserRole.CUSTOMER).is_staff_or_above() is False


def test_can_manage_products_delegates_to_staff_or_above():
    """can_manage_products 는 is_staff_or_above 와 동일한 결과를 반환."""
    for role in UserRole:
        user = User(role=role)
        assert user.can_manage_products() == user.is_staff_or_above()
```

---

## 6. 영향 받는 파일

| 파일                                | 변경 종류                                                      | 비고                                                              |
| ----------------------------------- | -------------------------------------------------------------- | ----------------------------------------------------------------- |
| `app/user/domain.py`                | 메서드 추가 (`is_admin`, `is_staff_or_above`) + `can_manage_products` 위임 리팩토링 | 신규 2 메서드 + 기존 1 메서드 내부 변경                          |
| `app/api/dependencies.py`           | 권한 비교 표현 변경 (`!= "admin"` → `not user.is_admin()`)    | 1줄                                                               |
| `app/user/router.py`                | 권한 비교 표현 변경                                            | 1줄                                                               |
| `tests/conftest.py`                 | 시드 데이터 enum 사용                                          | `admin_user` 픽스처 + import                                      |
| `tests/product/test_router.py`      | 시드 페이로드 enum 사용                                        | 1줄 + import                                                      |
| `tests/user/test_role.py` (신규)    | 권한 계층 회귀 가드 테스트                                    | 3 케이스                                                          |
| `docs/diagram/인증_및_권한.md`      | 본문의 `"admin"` 비교 노트 갱신                                | 1~2 줄                                                            |
| `docs/diagram/사용자_프로필.md`     | `GET /users/{id}` 섹션의 노트 갱신                             | 1~2 줄                                                            |

---

## 7. 테스트 영향

| 기존 테스트                              | 영향                                                                |
| ---------------------------------------- | ------------------------------------------------------------------- |
| `test_access_admin_endpoint_as_admin`    | 시드만 enum 으로 변경. 동작 동일 → PASS 유지                        |
| `test_access_admin_endpoint_as_regular_user` | 변경 없음 → PASS 유지                                              |
| `test_get_other_user_as_admin`           | 시드만 enum 으로 변경. PASS 유지                                    |
| 기타 admin 사용 케이스                   | 모두 PASS 유지                                                      |

신규 테스트 (선택): `test_user_is_admin_helper`, `test_user_role_equality_with_raw_string`.

---

## 8. 리스크 및 미해결 이슈

| #   | 항목                                                                            | 대응                                                                       |
| --- | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| 1   | `UserRole` 이 `str` 상속이므로 변경 후에도 `role == "admin"` 비교가 계속 동작   | 호환 유지 — 본 PRD 는 모든 사용처를 enum 으로 정렬하는 것이 목적           |
| 2   | DB 에 이미 저장된 row 의 `role` 컬럼 값                                         | SQLAlchemy `Enum(UserRole)` 컬럼이 양방향 변환 처리. 마이그레이션 불필요   |
| 3   | dependency_injector / FastAPI 응답 직렬화에서 enum 처리                          | `UserRole` 이 `str` 상속이라 JSON 직렬화 시 자동 문자열화 — 영향 없음 확인 |
| 4   | `User` dataclass 에 메서드 추가 시 dataclass 데코레이터와의 호환성              | 데코레이터는 메서드 추가 무관 — 영향 없음                                  |
| 5   | `is_staff_or_above` 가 현재 1 곳 (`can_manage_products`) 에서만 사용 — 과한 추상화 우려 | YAGNI 관점의 자기 검토: 계층 의도가 코드에 드러나는 가치가 있고, 추가 비용이 메서드 1개라 채택 |

### 결정 사항 (확정)

- [x] §4.1 권한 비교 표현 — **권한 계층 메서드 명시 (`is_admin` + `is_staff_or_above`)**
- [x] §4.2 테스트 시드 표현 — **`UserRole.ADMIN.value` (β)**
- [x] §5.4 회귀 가드 테스트 — **추가** (3 케이스)

---

## 9. 참고

- `UserRole` 정의: `app/user/domain.py:11`
- 기존 도메인 메서드: `app/user/domain.py:38 can_manage_products`
- 권한 의존성: `app/api/dependencies.py:60 get_current_active_admin`
- 사용자 조회 PR 의 권한 분기: `app/user/router.py:88-93`
- 선례:
  - PR #2 — `GET /users/{user_id}` admin 가드 추가 (`"admin"` 문자열 비교를 도입한 PR)
  - PR #1 — `GET /users/` admin 가드 추가 (동일 패턴 첫 도입)
