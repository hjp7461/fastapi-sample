# [PRD] UserResponse PII 마스킹 (응답 스키마 다중방어)

| 항목 | 내용 |
| --- | --- |
| 상태 | 제안 (Draft) |
| 작성일 | 2026-05-23 |
| 출처 | PR #2 §7-#3 후속, [HANDOFF] §6 마스터 목록 |
| 분류 | 보안 강화 (다중방어) |
| 추정 작업량 | 중 (1.5~2 시간, 스키마 분리 + 마스킹 헬퍼 + 라우터 분기 + 테스트) |

---

## 1. 배경

### 1.1 현재 응답 구조

`UserResponse` 는 단일 스키마로 모든 사용자 조회 엔드포인트에서 사용된다.

```python
# app/user/schemas.py
class UserResponse(UserBase):  # UserBase: email, username, first_name, last_name, role, is_active
    id: int
    created_at: datetime
    updated_at: datetime
```

라우터 매트릭스:

| 엔드포인트 | 권한 가드 | 응답 |
| --- | --- | --- |
| `GET /users/me` | `get_current_user` (본인) | `UserResponse` (전체) |
| `GET /users/{id}` | `get_self_or_admin` (본인 또는 관리자) | `UserResponse` (전체) |
| `GET /users/` | `get_current_active_admin` (관리자 전용) | `List[UserResponse]` (전체) |

### 1.2 문제

**권한 가드는 충분 — 일반 사용자가 타인 PII 를 볼 수 있는 경로는 0건**.

다만 PR #2 §7-#3 은 **다중방어 (defense-in-depth)** 관점에서 추가 정책을 요구한다.

1. **관리자가 타인 상세 조회 시** — `email/first_name/last_name` 까지 평문으로 볼 필요가 적음. 관리 목적 (역할 변경, 활성/비활성) 은 `id/username/role/is_active` 만으로 충분.
2. **관리자 목록 조회 시** — 100명을 한꺼번에 본다면 `email/이름` 까지 평문 노출은 과함. 요약 정보만으로 충분.
3. **응답이 로그/캐시/디버그 도구에 우연히 노출** — 권한 가드가 우회되더라도 응답 자체에 PII 가 적으면 노출 면적이 줄어든다.

### 1.3 본 PR 의 위치

[HANDOFF] §6: "UserResponse 필드 마스킹 (PII) — PR #2 §7-#3, 보안 강화, 중". 권한 분기 (PR #2, #10) 와 lazy rehash 정책 (PR #11, #13) 에 이어 응답 layer 의 다중방어를 채워넣는다.

---

## 2. 목적

1. **본인 조회 시에는 전체 필드** 그대로 노출 (UX 손해 없음).
2. **관리자가 타인 상세 조회 시** PII (`email`, `first_name`, `last_name`) 를 최소화 — `email` 은 마스킹, 이름은 응답에서 제외.
3. **관리자 목록 조회 시** PII 를 0건 — 요약 정보만 반환.
4. 마스킹 정책을 **헬퍼 함수로 분리**해 테스트 가능하고 다른 모듈에서 재사용 가능하게 한다.
5. OpenAPI 스펙에서 응답 형태가 명확히 표현되어야 한다 (Union 으로 두 형태 노출).

---

## 3. 비목적

- 관리자가 본인이 본인을 조회하는 케이스의 특별 처리 — `viewer.id == user.id` 분기에 자연스럽게 포함.
- audit log — 별도 마스터 목록 항목.
- 마스킹 정책의 환경 변수화 (개발 환경에서는 마스킹 해제 등) — 본 PR 은 정책 고정.
- 응답 자체의 캐싱/HTTP 헤더 정책 (Cache-Control 등) — 별도 관심사.
- 마스킹 헬퍼의 generic 화 (다른 도메인에서 재사용) — `app/user/` 안에 두고 필요 시 후속에서 승격.
- 패스워드/토큰 마스킹 — 이미 응답 스키마에 포함 안 됨.

---

## 4. 성공 기준

- [ ] `app/user/masking.py::mask_email(email) -> str` 헬퍼 — `a***@e***.com` 형식 반환.
- [ ] `UserAdminView` 스키마 — `id, username, email (masked), role, is_active, created_at, updated_at` (first_name/last_name 제외).
- [ ] `UserSummary` 스키마 — `id, username, role, is_active, created_at` (모든 PII 제외).
- [ ] `UserResponse` 는 본인용 / 단독 노출에만 사용 — 본인의 모든 필드 노출.
- [ ] `GET /users/me` → `UserResponse`.
- [ ] `GET /users/{id}` → 본인이면 `UserResponse`, 타인 (관리자) 이면 `UserAdminView`.
- [ ] `GET /users/` → `List[UserSummary]`.
- [ ] 기존 46 PASS 유지 + 신규 회귀 가드:
  - `mask_email` 단위 테스트 (정상, 짧은 로컬, malformed)
  - `GET /users/{id}` 본인 조회 응답에 first_name/last_name 포함 검증
  - `GET /users/{id}` 관리자가 타인 조회 시 응답에 first_name/last_name 없음 + email 마스킹 검증
  - `GET /users/` 응답이 `UserSummary` 필드만 포함 (email/이름 없음) 검증
- [ ] OpenAPI 스펙에 `UserAdminView`, `UserSummary` 가 명시 (Union 타입 노출).

---

## 5. 설계

### 5.1 마스킹 헬퍼 (`app/user/masking.py`)

```python
"""사용자 PII 마스킹 유틸리티."""


def mask_email(email: str) -> str:
    """이메일을 `a***@e***.com` 형태로 마스킹한다.

    - 로컬 파트: 첫 글자만 노출, 나머지 ***
    - 도메인의 호스트: 첫 글자만 노출, 나머지 ***
    - 도메인의 TLD: 그대로 유지

    정상 입력 외 (로컬 빈 문자열, '@' 0개 등) 은 보수적으로 ``"***"`` 반환.
    """
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    if "." not in domain:
        return "***"
    host, _, tld = domain.partition(".")
    masked_local = f"{local[0]}***" if local else "***"
    masked_host = f"{host[0]}***" if host else "***"
    return f"{masked_local}@{masked_host}.{tld}"
```

### 5.2 스키마 (`app/user/schemas.py`)

```python
class UserResponse(UserBase):
    """본인 조회 응답 — 전체 PII 노출."""
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class UserAdminView(BaseModel):
    """관리자가 타인을 상세 조회할 때의 응답 — PII 최소화.

    - email 은 마스킹된 형태 (`a***@e***.com`)
    - first_name / last_name 은 응답에서 제외
    """
    id: int
    username: str
    email: str  # 마스킹된 값 → EmailStr 검증을 피하기 위해 str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class UserSummary(BaseModel):
    """관리자 목록 조회 — PII 0건."""
    id: int
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}
```

### 5.3 빌더 함수 (`app/user/schemas.py` 또는 별도)

```python
def build_admin_view(user) -> UserAdminView:
    return UserAdminView(
        id=user.id,
        username=user.username,
        email=mask_email(user.email),
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def build_summary(user) -> UserSummary:
    return UserSummary(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )
```

`build_summary` 와 `build_admin_view` 는 schemas.py 가 도메인 모델을 직접 참조하지 않도록 하기 위해 `model_config = {"from_attributes": True}` 활용 가능. 빌더는 명시 + 마스킹 적용을 위해 유지.

### 5.4 라우터 변경 (`app/user/router.py`)

```python
from typing import Union

from app.user.schemas import UserResponse, UserAdminView, UserSummary, build_admin_view, build_summary


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user=Depends(get_current_user)):
    return current_user


@router.get("/{user_id}", response_model=Union[UserResponse, UserAdminView])
async def get_user_by_id(
    user_id: int,
    current_user=Depends(get_self_or_admin),  # get_self_or_admin 이 user 객체를 반환하도록 조정 필요
    user_service: UserService = Depends(lambda: Container.user_service()),
):
    try:
        user = await user_service.get_user(user_id)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))

    if current_user.id == user.id:
        return user  # UserResponse 로 직렬화
    # 관리자가 타인 조회
    return build_admin_view(user)


@router.get("/", response_model=List[UserSummary])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    _: Any = Depends(get_current_active_admin),
    user_service: UserService = Depends(lambda: Container.user_service()),
):
    users = await user_service.list_users(skip=skip, limit=limit)
    return [build_summary(u) for u in users]
```

**핵심 변경 #1**: `get_self_or_admin` 의존성이 현재는 권한만 검증하고 반환값은 사용 안 됐다 (라우터에서 `_: Any` 무시). 본 PR 에서는 viewer 정보가 필요하므로 의존성을 `get_current_user` 로 바꾸고 권한 검증은 별도 처리 — 또는 `get_self_or_admin` 이 current_user 를 반환하도록 조정.

`get_self_or_admin` 현재 코드 확인 후 결정. 만약 이미 current_user 를 반환하면 그대로 사용. 안 하면 minor 조정.

**핵심 변경 #2**: `response_model=Union[UserResponse, UserAdminView]` — FastAPI 가 OpenAPI 에 두 형태를 모두 노출. 응답 직렬화 시 객체 타입에 맞게 자동 선택.

### 5.5 테스트 매트릭스

```python
# tests/user/test_masking.py (신규)
def test_mask_email_basic():
    assert mask_email("alice@example.com") == "a***@e***.com"
    assert mask_email("a@x.com") == "a***@x***.com"

def test_mask_email_malformed():
    assert mask_email("") == "***"
    assert mask_email("no-at-sign") == "***"
    assert mask_email("no-tld@host") == "***"
    assert mask_email("@example.com").startswith("***")  # 로컬 없음


# tests/user/test_router.py (추가)
async def test_get_self_returns_full_user_response(...):
    """본인 조회 시 first_name/last_name 까지 응답에 포함."""
    # test_user 가 first_name="Test", last_name="User" 라고 가정
    response = await client.get(f"/users/{test_user.id}", headers=test_user_auth)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email  # 마스킹 X
    assert "first_name" in data and data["first_name"] == "Test"
    assert "last_name" in data and data["last_name"] == "User"


async def test_get_other_user_as_admin_returns_masked_view(...):
    """관리자가 타인 조회 시 email 마스킹 + 이름 제외."""
    response = await client.get(f"/users/{test_user.id}", headers=admin_auth)
    assert response.status_code == 200
    data = response.json()
    assert "@" in data["email"]
    assert "***" in data["email"]  # 마스킹됨
    assert "first_name" not in data
    assert "last_name" not in data


async def test_list_users_returns_summary_only(...):
    """관리자 목록 조회 시 PII 필드 0건."""
    response = await client.get("/users/", headers=admin_auth)
    assert response.status_code == 200
    items = response.json()
    for item in items:
        assert "email" not in item
        assert "first_name" not in item
        assert "last_name" not in item
        # 요약 필드는 있음
        assert "id" in item
        assert "username" in item
        assert "role" in item
```

### 5.6 `get_self_or_admin` 의존성 검토

PR #10 에서 도입된 `get_self_or_admin` 의 현재 형태를 확인하고 (current_user 반환 여부), 라우터에서 viewer 정보를 받을 수 있도록 한다. 가능한 형태:

옵션 A: 의존성이 current_user 반환 → 라우터에서 그대로 사용
옵션 B: 라우터가 `get_current_user` 의존성 사용 + 권한 검증을 본문 안에서 (의존성 추상화 후퇴)

PR #10 의 의도가 "라우터 본문 권한 분기 0줄" 이므로 옵션 A 가 더 적절. 의존성에 minor 조정.

### 5.7 도메인 모델 가정

`User` 도메인 객체에 `first_name`, `last_name`, `email`, `username`, `role`, `is_active`, `created_at`, `updated_at` 이 있음을 가정. UserModel 과 동일. 확인 필요.

---

## 6. 영향

| 영역 | 영향 |
| --- | --- |
| `app/user/masking.py` | 신규 — `mask_email` 헬퍼 |
| `app/user/schemas.py` | `UserAdminView`, `UserSummary` 신규 + `build_admin_view`, `build_summary` 빌더 |
| `app/user/router.py` | `GET /users/{id}`, `GET /users/` 의 응답 분기 추가 |
| `app/api/dependencies.py` | `get_self_or_admin` 이 current_user 반환하도록 조정 (필요 시) |
| 외부 API 호환성 | **변화 (의도)** — `GET /users/` 응답에서 PII 제거, `GET /users/{id}` 가 본인/관리자 컨텍스트에 따라 다른 형태 |
| OpenAPI 스펙 | `UserAdminView`, `UserSummary` 추가, `GET /users/{id}` 가 Union 응답 |
| DB 스키마 | 변화 없음 |
| 테스트 | 신규 4~6 케이스 |

---

## 7. 리스크

| 리스크 | 가능성 | 대응 |
| --- | --- | --- |
| API 클라이언트가 `GET /users/` 응답에서 email 을 기대 | 중 | 본 프로젝트는 데모 단계 — 외부 클라이언트 없음. PR description 에 변경 매트릭스 명시. 후속 PR 에서 정책 옵션화 가능 |
| `Union[UserResponse, UserAdminView]` 직렬화가 잘못된 모델로 (예: 본인인데도 UserAdminView 로) | 중 | Pydantic v2 의 Union 직렬화는 "객체 형 기반" — 라우터에서 명시적으로 다른 객체를 반환하므로 안정. 회귀 가드가 첫 케이스에서 검출 |
| `get_self_or_admin` 의존성 조정이 다른 라우터에 영향 | 낮음 | 본 의존성 사용처는 현재 `GET /users/{id}` 한 곳 (PR #10 으로 추출). 영향 범위 명확 |
| `mask_email` 이 이상한 입력에 NoneType 등 던짐 | 낮음 | 단위 테스트가 malformed 케이스 커버. 보수적으로 `***` 반환 |

---

## 8. 결정 사항 (확정)

- [x] 스키마 3분리: `UserResponse` (본인용), `UserAdminView` (관리자가 타인), `UserSummary` (목록)
- [x] 마스킹 정책: email 마스킹 (`a***@e***.com`), first_name/last_name 응답에서 제외
- [x] `GET /users/{id}` 의 `response_model=Union[UserResponse, UserAdminView]` (OpenAPI 두 형태 노출)
- [x] `GET /users/` 의 `response_model=List[UserSummary]` (PII 0건)
- [x] 본인 조회 vs 관리자가 타인 조회 구분 — 라우터에서 viewer.id 비교
- [x] 마스킹 정책은 코드 고정, 환경 변수 미사용 (별도 후속에서 옵션화 가능)
- [x] `mask_email` 헬퍼는 `app/user/masking.py` (도메인 안에 한정, 외부 노출은 후속)
- [x] `get_self_or_admin` 의존성이 current_user 를 반환하도록 (필요 시) 조정

---

## 9. 참고

- `docs/[PRD]사용자_조회_인증_누락.md` (PR #2)
- `docs/[PRD]권한_분기_의존성_추출.md` (PR #10, `get_self_or_admin`)
- `app/user/schemas.py`, `app/user/router.py`, `app/api/dependencies.py`
- FastAPI Union response_model: https://fastapi.tiangolo.com/advanced/additional-responses/
