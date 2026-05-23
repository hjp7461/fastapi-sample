# [PLAN] UserResponse PII 마스킹 (응답 스키마 다중방어)

| 항목 | 내용 |
| --- | --- |
| 연관 PRD | `docs/[PRD]UserResponse_PII_마스킹.md` |
| 브랜치 | `feature/user-response-pii-masking` |
| 추정 작업량 | 중 (1.5~2 시간) |
| 채택 전략 | 마스킹 헬퍼 + 스키마 3분리 + 라우터 분기 + 회귀 가드 |

---

## 0. 사전 점검 (Pre-flight)

- [x] `get_self_or_admin` 이 이미 `current_user: User` 반환 → 의존성 조정 불필요
- [ ] `main` 최신, 46 PASS 기준선 확인
- [ ] 새 브랜치 `feature/user-response-pii-masking` 생성

---

## 1. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout -b feature/user-response-pii-masking
```

### Step 2 — `app/user/masking.py` 신규

PRD §5.1 코드 그대로.

```python
def mask_email(email: str) -> str:
    ...
```

### Step 3 — `tests/user/test_masking.py` 신규 (마스킹 단위 테스트)

```python
from app.user.masking import mask_email


def test_mask_email_basic():
    assert mask_email("alice@example.com") == "a***@e***.com"
    assert mask_email("a@x.com") == "a***@x***.com"


def test_mask_email_malformed():
    assert mask_email("") == "***"
    assert mask_email("no-at-sign") == "***"
    assert mask_email("no-tld@host") == "***"


def test_mask_email_empty_local():
    # 로컬 빈 → 보수적
    assert mask_email("@example.com").startswith("***")
```

**검증**

```bash
uv run pytest tests/user/test_masking.py -v
```

### Step 4 — `app/user/schemas.py` 에 새 스키마 + 빌더 추가

- `UserAdminView` 스키마
- `UserSummary` 스키마
- `build_admin_view(user) -> UserAdminView`
- `build_summary(user) -> UserSummary`

기존 `UserResponse` 는 그대로 유지 (본인용으로 의미만 명확화 — docstring 갱신).

### Step 5 — `app/user/router.py` 분기 추가

PRD §5.4 의 매트릭스대로 변경.

- `GET /users/me` — 변경 없음 (`UserResponse`)
- `GET /users/{user_id}` — `response_model=Union[UserResponse, UserAdminView]`. 의존성을 `get_self_or_admin` 으로 유지 (current_user 반환), 본인이면 `user` 그대로, 아니면 `build_admin_view(user)` 반환
- `GET /users/` — `response_model=List[UserSummary]`. 응답을 `[build_summary(u) for u in users]` 로 변환

**검증**

```bash
uv run pytest tests/user/test_router.py -v
# 기존 케이스는 통과해야 함 — 본인 조회 응답이 UserResponse 형태이므로 변화 없음.
# 단, 관리자 목록 조회 케이스 (test_access_admin_endpoint_as_admin) 가
# UserSummary 형태로 바뀌므로 응답 검증을 갱신 필요할 수 있음.
```

### Step 6 — 기존 라우터 테스트 회귀 정합성 확인

`test_access_admin_endpoint_as_admin` 이 응답 리스트 길이/형태만 검증하는 형태인지 확인.

```python
# tests/user/test_router.py::test_access_admin_endpoint_as_admin
assert response.status_code == 200
data = response.json()
assert isinstance(data, list)
assert len(data) > 0  # 최소한 관리자 자신의 계정이 있어야 함
```

→ 이 정도면 변화 없음. PASS 유지.

`test_get_other_user_as_admin` 은 관리자가 타인 조회.

```python
# tests/user/test_router.py::test_get_other_user_as_admin
assert response.status_code == 200
data = response.json()
assert data["id"] == test_user["id"]
assert data["email"] == test_user["email"]  # ← 마스킹 적용으로 깨질 가능성
```

이 테스트가 `email` 평문 일치를 기대하면 깨진다. 본 PR 에서 의미 정정 — 마스킹 형태 검증으로 변경.

### Step 7 — 신규 라우터 회귀 가드 (3건)

`tests/user/test_router.py` 끝에 추가.

```python
@pytest.mark.asyncio
async def test_get_self_returns_full_user_response(
    client, auth_headers, test_user
):
    """본인 조회 시 first_name/last_name 까지 응답에 포함."""
    response = await client.get(
        f"/api/v1/users/{test_user['id']}", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user["email"]
    # first_name/last_name 은 fixture 에서 설정 안 됐을 수 있어 key 만 검증
    assert "first_name" in data
    assert "last_name" in data


@pytest.mark.asyncio
async def test_get_other_user_as_admin_returns_masked_view(
    client, admin_auth_headers, test_user
):
    """관리자가 타인 조회 시 email 마스킹 + 이름 응답 제외."""
    response = await client.get(
        f"/api/v1/users/{test_user['id']}", headers=admin_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user["id"]
    assert "***" in data["email"]
    assert data["email"] != test_user["email"]
    assert "first_name" not in data
    assert "last_name" not in data
    # 비PII 필드는 그대로
    assert "username" in data
    assert "role" in data


@pytest.mark.asyncio
async def test_list_users_returns_summary_without_pii(
    client, admin_auth_headers
):
    """관리자 목록 조회 시 PII 필드 0건 (요약 응답)."""
    response = await client.get("/api/v1/users/", headers=admin_auth_headers)
    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    for item in items:
        assert "email" not in item
        assert "first_name" not in item
        assert "last_name" not in item
        assert "id" in item
        assert "username" in item
        assert "role" in item
```

### Step 8 — 기존 `test_get_other_user_as_admin` 의미 정정

```python
# 기존
assert data["email"] == test_user["email"]

# 변경 후 — 마스킹 적용된 응답을 기대
assert data["id"] == test_user["id"]
# email 은 마스킹돼 있으므로 평문 비교 불가. masked view 신규 케이스에서 별도 검증.
```

직접적으로 `email` 라인을 삭제 또는 변경.

### Step 9 — 전체 회귀

```bash
uv run pytest
# 기대: 46 + 마스킹 단위 3 + 라우터 신규 3 = 52 PASS, warning 0
```

### Step 10 — 커밋 + 푸시 + PR

```bash
git add -f docs/'[PRD]UserResponse_PII_마스킹.md' docs/'[PLAN]UserResponse_PII_마스킹.md'
git add app/user/masking.py app/user/schemas.py app/user/router.py
git add tests/user/test_masking.py tests/user/test_router.py
git commit ...
git push -u origin feature/user-response-pii-masking
gh pr create ...
```

---

## 2. 산출물 체크리스트

| 산출물 | 위치 | 상태 |
| --- | --- | --- |
| PRD | `docs/[PRD]UserResponse_PII_마스킹.md` | ✅ |
| PLAN | `docs/[PLAN]UserResponse_PII_마스킹.md` | ✅ |
| 마스킹 헬퍼 | `app/user/masking.py` | ⬜ |
| 스키마 + 빌더 | `app/user/schemas.py` | ⬜ |
| 라우터 응답 분기 | `app/user/router.py` | ⬜ |
| 마스킹 단위 테스트 | `tests/user/test_masking.py` | ⬜ |
| 라우터 회귀 가드 +3 | `tests/user/test_router.py` | ⬜ |
| 기존 `test_get_other_user_as_admin` 의미 정정 | `tests/user/test_router.py` | ⬜ |

---

## 3. 신규 테스트 케이스 매트릭스

| # | 위치 | 케이스 |
| --- | --- | --- |
| 1 | `tests/user/test_masking.py::test_mask_email_basic` | 정상 입력 → `a***@e***.com` |
| 2 | `tests/user/test_masking.py::test_mask_email_malformed` | 빈 문자열 / '@' 없음 / TLD 없음 → `***` |
| 3 | `tests/user/test_masking.py::test_mask_email_empty_local` | 로컬 빈 → 보수적 |
| 4 | `tests/user/test_router.py::test_get_self_returns_full_user_response` | 본인 조회: first_name/last_name 포함 + email 평문 |
| 5 | `tests/user/test_router.py::test_get_other_user_as_admin_returns_masked_view` | 관리자 → 타인: email 마스킹 + 이름 응답 제외 |
| 6 | `tests/user/test_router.py::test_list_users_returns_summary_without_pii` | 관리자 목록: email/이름 0건 |

---

## 4. 회귀 방지

| 회귀 시나리오 | 가드 |
| --- | --- |
| 마스킹이 본인 응답에도 적용되는 잘못 분기 | 케이스 #4 |
| 관리자가 타인 조회에 마스킹 없이 평문 노출 | 케이스 #5 |
| 목록 조회에 PII 잔존 | 케이스 #6 |
| Union 응답이 잘못된 모델로 직렬화 | 케이스 #4 와 #5 가 양쪽 모두 검증 |
| mask_email 이상한 입력에 예외 전파 | 케이스 #2, #3 |

---

## 5. 롤백

단일 머지 revert. 외부 API 호환성 변화가 있지만, 데모 단계라 영향 0.

---

## 6. 후속 작업 후보

- 마스킹 정책 환경 변수화 (개발 환경에서 해제 옵션)
- audit log (누가 누구의 정보를 언제 조회했는지)
- 다른 도메인의 PII 처리 (Product 도메인은 PII 없음 — 현재는 불요)
- 마스킹 헬퍼의 `app/core/masking.py` 로 승격 (다른 도메인 사용 시점에)

---

## 7. 참고

- `docs/[PRD]UserResponse_PII_마스킹.md`
- `app/api/dependencies.py::get_self_or_admin` (current_user 반환 확인됨)
- FastAPI Union response_model
