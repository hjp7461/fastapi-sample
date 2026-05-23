# [PLAN] Product 조회 컨텍스트 분리 (구매자 vs 관리/staff)

| 항목 | 내용 |
| --- | --- |
| 연관 PRD | `docs/[PRD]Product_조회_컨텍스트_분리.md` |
| 브랜치 | `feature/product-view-context-split` |
| 추정 작업량 | 중 (1.5~2 시간) |
| 채택 전략 | 스키마 분리 + get_optional_current_user + 라우터 viewer 분기 + 기존 2건 정정 |

---

## 0. 사전 점검 (Pre-flight)

- [x] `is_staff_or_above` 가 User domain 에 존재 (PR #4)
- [x] 기존 테스트 2건 (`test_update_inventory_as_admin`, `test_update_inventory_insufficient`) 이 anonymous 조회로 inventory 확인 — admin_auth_headers 추가 필요
- [ ] `main` 최신, 55 PASS 기준선 확인
- [ ] 새 브랜치 `feature/product-view-context-split` 생성

---

## 1. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout -b feature/product-view-context-split
```

### Step 2 — `app/product/schemas.py` 에 ProductPublicView + build_public_view 추가

PRD §5.1 그대로.

### Step 3 — `app/api/dependencies.py` 에 get_optional_current_user 신규

`get_current_user` 의 토큰 검증 로직을 부분 재사용하되, 토큰이 없거나 무효하면 None 반환 (예외 X).

```python
async def get_optional_current_user(
    request: Request,
    user_service: UserService = Depends(get_user_service),
) -> Optional[User]:
    """Authorization 헤더가 없거나 토큰이 무효하면 None.

    공개 조회 엔드포인트에서 viewer 컨텍스트가 있을 수 있고 없을 수도 있는 경우 사용.
    """
    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = int(payload.get("sub"))
    except (PyJWTError, ValueError, TypeError):
        return None
    user = await user_service.get_user(user_id)
    if user is None or not user.is_active:
        return None
    return user
```

`Request` import 추가 (`from fastapi import Request`).

### Step 4 — `app/product/router.py` 의 GET 두 곳 viewer 분기 추가

PRD §5.3 그대로. POST/PUT/DELETE/PATCH inventory 는 변경 없음.

### Step 5 — 기존 product 테스트 2건 정정

- `test_update_inventory_as_admin` (L216): `client.get(...)` → `client.get(..., headers=admin_auth_headers)`
- `test_update_inventory_insufficient` (L271): 동일

### Step 6 — 신규 회귀 가드 +5

PRD §5.5 의 5 케이스 추가 (`tests/product/test_router.py` 끝에).

### Step 7 — 전체 회귀

```bash
uv run pytest
# 기대: 55 + 5 = 60 PASS, warning 0
```

### Step 8 — 커밋 + 푸시 + PR

```bash
git add -f docs/'[PRD]Product_조회_컨텍스트_분리.md' docs/'[PLAN]Product_조회_컨텍스트_분리.md'
git add app/product/schemas.py app/product/router.py app/api/dependencies.py tests/product/test_router.py
git commit ...
git push -u origin feature/product-view-context-split
gh pr create ...
```

---

## 2. 산출물 체크리스트

| 산출물 | 위치 | 상태 |
| --- | --- | --- |
| PRD | `docs/[PRD]Product_조회_컨텍스트_분리.md` | ✅ |
| PLAN | `docs/[PLAN]Product_조회_컨텍스트_분리.md` | ✅ |
| ProductPublicView + build_public_view | `app/product/schemas.py` | ⬜ |
| get_optional_current_user | `app/api/dependencies.py` | ⬜ |
| 라우터 viewer 분기 (GET 두 곳) | `app/product/router.py` | ⬜ |
| 기존 2건 정정 + 신규 5건 회귀 가드 | `tests/product/test_router.py` | ⬜ |

---

## 3. 신규 테스트 매트릭스

| # | 시나리오 | 기대 응답 |
| --- | --- | --- |
| 1 | anonymous GET /products/{id} | ProductPublicView (inventory 없음) |
| 2 | customer GET /products/{id} | ProductPublicView (inventory 없음) |
| 3 | admin GET /products/{id} | ProductResponse (inventory 포함) |
| 4 | anonymous GET /products/ | List[ProductPublicView] (모두 inventory 없음) |
| 5 | admin GET /products/ | List[ProductResponse] (모두 inventory 포함) |

---

## 4. 회귀 방지

| 회귀 시나리오 | 가드 |
| --- | --- |
| 공개 조회에 inventory 누설 | 신규 #1, #2, #4 |
| 관리자 조회에서 inventory 누락 | 신규 #3, #5 |
| 인증 토큰 무효 시 401 → 공개 조회 차단 | 새 `get_optional_current_user` 가 None 반환 (예외 X) — #1 케이스가 검증 |
| Union 응답 직렬화 잘못된 모델 | viewer 분기에서 명시적 다른 객체 반환 — #1, #3 가 양쪽 검증 |
| `is_staff_or_above` 가 잘못된 role 에 True | 기존 `tests/user/test_role.py` 가드 (PR #4) |

---

## 5. 롤백

단일 머지 revert. 외부 API 변경 (공개 조회 inventory 제거) 이 있지만 데모 단계라 영향 0.

---

## 6. 후속 작업 후보

- 가격/할인 마스킹 정책 검토 (대량 구매 가격 등)
- audit log (누가 product 를 언제 조회) — 운영 추적성
- staff 권한으로 변경 작업 일부 허용 (정책 결정 시)

---

## 7. 참고

- PRD: `docs/[PRD]Product_조회_컨텍스트_분리.md`
- `docs/[PRD]UserResponse_PII_마스킹.md` (PR #15) — 동일 응답 분리 패턴
