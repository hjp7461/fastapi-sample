# [PRD] Product 조회 컨텍스트 분리 (구매자 vs 관리/staff)

| 항목 | 내용 |
| --- | --- |
| 상태 | 제안 (Draft) |
| 작성일 | 2026-05-23 |
| 출처 | PR #10 §리스크 #2 후속 — 사용자 통찰로 재정의: "상품 관리용 조회와 구매자 조회의 분리" |
| 분류 | 보안 / 응답 정책 (도메인 컨텍스트 분리) |
| 추정 작업량 | 중 (1.5~2 시간, 스키마 + 라우터 분기 + staff 가드 + 회귀) |

---

## 1. 배경

### 1.1 현재 권한/응답 매트릭스

| 엔드포인트 | 권한 | 응답 |
| --- | --- | --- |
| `POST /products/` | admin | ProductResponse (전체) |
| `GET /products/{id}` | **인증 없음** | ProductResponse (전체, **inventory 포함**) |
| `PUT /products/{id}` | admin | ProductResponse (전체) |
| `DELETE /products/{id}` | admin | - |
| `GET /products/` | **인증 없음** | List[ProductResponse] (전체, **inventory 포함**) |
| `PATCH /products/{id}/inventory` | admin | ProductResponse (전체) |

### 1.2 사용자 통찰 (재정의된 후속)

PR #10 §리스크 #2 의 "Product self+admin 패턴" 은 그대로 적용하기 어렵다 (Product 에는 "self" 개념이 없음 — e-commerce 카탈로그). 그러나 후속의 진짜 의도는 다른 곳에 있다.

> "상품 관리를 위한 조회와 구매자가 상품 정보를 얻기 위한 조회가 분리되어야 하는데, 현재 이 부분에 대한 정의가 미흡. **staff 이상 권한에서는 상품의 수량(inventory)이 보일 필요가 있지만 구매를 위한 조회에선 이 부분은 필요가 없다.**"

즉 두 컨텍스트가 같은 엔드포인트/응답으로 묶여있어 다음 문제가 발생.

1. **구매자에게 inventory 노출** — 재고 수량은 영업/공급 정보. 경쟁사/스크래퍼가 즉시 파악 가능.
2. **권한 컨텍스트와 응답 컨텍스트가 분리되지 않음** — PR #15 (UserResponse PII) 에서 본인/관리자 분리한 것과 동일 패턴 필요.
3. **`is_staff_or_above` 가 정의돼있는데 미활용** — PR #4 에서 도메인 메서드로 만들었지만 product 라우터에서 한 번도 안 쓰임.

### 1.3 본 PR 의 위치

[HANDOFF] §6: "Product 도메인의 self+admin 패턴 (정책 결정 시)". 정책이 결정됐으므로 (구매자/관리 분리 + inventory 노출 통제) 실행 단계.

---

## 2. 목적

1. **응답 스키마 2종 분리**:
   - `ProductPublicView` — 구매자/공개 응답 (**inventory 제외**, name/description/price/category/is_active/created_at/updated_at)
   - `ProductResponse` — staff/admin 응답 (전체 필드, **inventory 포함**)
2. **`GET /products/{id}` 와 `GET /products/`** 가 viewer 의 권한에 따라 응답 분기:
   - 인증 없음 또는 일반 사용자 → `ProductPublicView`
   - staff 또는 admin → `ProductResponse`
3. `app/api/dependencies.py` 에 `get_staff_or_above` 의존성 신규 (또는 기존 활용) — PR #4 의 도메인 메서드 활성화.
4. 변경 작업 (POST/PUT/DELETE/PATCH inventory) 은 **admin only** 유지 — 본 PR 비목적.
5. **외부 응답 형태 변경 (의도된 변경)** — 공개 응답에서 `inventory` 키 제거.

---

## 3. 비목적

- 변경 작업의 권한 완화 (staff 가 product 생성/삭제 가능 등) — 별도 후속.
- 구매/장바구니/주문 API 도입 — 본 PR 은 조회 응답만.
- audit log (누가 product 를 언제 조회) — 별도 후속.
- 가격/할인 마스킹 — 본 PR 은 inventory 만.
- vendor 패턴 (User 가 자기 product 소유) — 별도 큰 도메인 재설계.

---

## 4. 성공 기준

- [ ] `app/product/schemas.py` 에 `ProductPublicView` 신규 (inventory 제외).
- [ ] 기존 `ProductResponse` 는 staff/admin 응답으로 의미 명확화 (전체 필드 유지).
- [ ] `app/product/schemas.py` 에 `build_public_view(product) -> ProductPublicView` 빌더.
- [ ] `app/api/dependencies.py` 에 `get_staff_or_above` (또는 `get_optional_current_user`) 의존성 신규.
- [ ] `GET /products/{id}` 응답이 `Union[ProductPublicView, ProductResponse]` — viewer 권한에 따라 분기.
- [ ] `GET /products/` 응답이 `Union[List[ProductPublicView], List[ProductResponse]]` — 동일 분기.
- [ ] 기존 55 PASS 유지 + 신규 회귀 가드:
  - 인증 없이 `GET /products/{id}` → `ProductPublicView` (inventory 없음) 검증
  - 일반 사용자가 `GET /products/{id}` → `ProductPublicView` (inventory 없음) 검증
  - staff/admin 이 `GET /products/{id}` → `ProductResponse` (inventory 포함) 검증
  - 목록 조회 동일 매트릭스
- [ ] OpenAPI 스펙에 두 스키마 모두 명시.

---

## 5. 설계

### 5.1 스키마 (`app/product/schemas.py`)

```python
class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: Decimal
    category: ProductCategory = ProductCategory.OTHER
    is_active: bool = True


class ProductResponse(ProductBase):
    """관리/staff 응답 — 전체 필드 (inventory 포함).

    GET 컨텍스트:
        - viewer 가 staff/admin 인 경우
    """
    id: int
    inventory: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ProductPublicView(BaseModel):
    """구매자/공개 응답 — inventory 제외.

    영업 정보 (재고 수량) 가 외부에 노출되지 않도록 마스킹.
    """
    id: int
    name: str
    description: Optional[str] = None
    price: Decimal
    category: ProductCategory
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


def build_public_view(product) -> ProductPublicView:
    """도메인 Product 를 공개용으로 변환 (inventory 제외)."""
    return ProductPublicView(
        id=product.id,
        name=product.name,
        description=product.description,
        price=product.price,
        category=product.category,
        is_active=product.is_active,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )
```

### 5.2 의존성 (`app/api/dependencies.py`)

`get_current_user` 는 토큰이 없으면 401 을 던지므로 공개 조회와 호환되지 않는다. **옵셔널 인증** 의존성이 필요.

```python
async def get_optional_current_user(
    request: Request,
    user_service: UserService = Depends(get_user_service),
) -> Optional[User]:
    """Authorization 헤더가 없거나 토큰이 무효하면 None, 유효하면 User."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = int(payload.get("sub"))
    except (PyJWTError, ValueError, TypeError):
        return None
    user = await user_service.get_user(user_id)
    if user is None or not user.is_active:
        return None
    return user
```

별도 의존성으로 분리 — `get_current_user` 는 변경 없음 (다른 라우터에서 사용 중).

### 5.3 라우터 변경

```python
@router.get("/{product_id}", response_model=Union[ProductPublicView, ProductResponse])
async def get_product_by_id(
    product_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    product_service: ProductService = Depends(get_product_service),
):
    try:
        product = await product_service.get_product(product_id)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))

    if current_user is not None and current_user.is_staff_or_above():
        return product  # ProductResponse — inventory 포함
    return build_public_view(product)


@router.get("/", response_model=Union[List[ProductPublicView], List[ProductResponse]])
async def list_products(
    skip: int = 0,
    limit: int = 100,
    category: Optional[ProductCategory] = None,
    is_active: Optional[bool] = Query(None, description="활성화 상태 필터링"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    product_service: ProductService = Depends(get_product_service),
):
    products = await product_service.list_products(
        skip=skip, limit=limit, category=category, is_active=is_active
    )
    if current_user is not None and current_user.is_staff_or_above():
        return products  # List[ProductResponse]
    return [build_public_view(p) for p in products]
```

변경 작업 (POST/PUT/DELETE/PATCH inventory) 은 **변화 없음** — admin only 유지.

### 5.4 권한 매트릭스 (변경 후)

| 엔드포인트 | 권한 | 응답 (변경) |
| --- | --- | --- |
| `POST /products/` | admin | ProductResponse (전체) — **변화 없음** |
| `GET /products/{id}` | 누구나 | **ProductPublicView** (anonymous/customer) 또는 **ProductResponse** (staff/admin) |
| `PUT /products/{id}` | admin | ProductResponse — **변화 없음** |
| `DELETE /products/{id}` | admin | - |
| `GET /products/` | 누구나 | **List[ProductPublicView]** 또는 **List[ProductResponse]** |
| `PATCH /products/{id}/inventory` | admin | ProductResponse — **변화 없음** |

### 5.5 회귀 매트릭스

```python
# tests/product/test_router.py — 신규 케이스

async def test_get_product_anonymous_returns_public_view(client, test_product):
    """인증 없이 조회 → inventory 키 없음."""
    response = await client.get(f"/api/v1/products/{test_product['id']}")
    assert response.status_code == 200
    assert "inventory" not in response.json()


async def test_get_product_as_customer_returns_public_view(client, auth_headers, test_product):
    """일반 사용자 조회 → inventory 키 없음."""
    response = await client.get(f"/api/v1/products/{test_product['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert "inventory" not in response.json()


async def test_get_product_as_admin_returns_full(client, admin_auth_headers, test_product):
    """관리자 조회 → inventory 포함."""
    response = await client.get(f"/api/v1/products/{test_product['id']}", headers=admin_auth_headers)
    assert response.status_code == 200
    assert "inventory" in response.json()


async def test_list_products_anonymous_excludes_inventory(client):
    """인증 없는 목록 → 모든 항목 inventory 없음."""
    response = await client.get("/api/v1/products/")
    assert response.status_code == 200
    for item in response.json():
        assert "inventory" not in item


async def test_list_products_as_admin_includes_inventory(client, admin_auth_headers):
    """관리자 목록 → 모든 항목 inventory 포함."""
    response = await client.get("/api/v1/products/", headers=admin_auth_headers)
    assert response.status_code == 200
    for item in response.json():
        assert "inventory" in item
```

### 5.6 기존 product 라우터 테스트 영향

기존 13 케이스 중 일부가 anonymous 조회로 inventory 를 기대할 수 있음 — 그 케이스들을 검토하고 admin_auth_headers 추가 또는 의미 정정 필요. PLAN 단계에서 정확 매트릭스 확인.

---

## 6. 영향

| 영역 | 영향 |
| --- | --- |
| `app/product/schemas.py` | `ProductPublicView` 신규 + `build_public_view` 빌더. `ProductResponse` 의미 명확화 |
| `app/product/router.py` | `GET /products/{id}` 와 `GET /products/` 에 viewer 분기 추가 |
| `app/api/dependencies.py` | `get_optional_current_user` 의존성 신규 |
| `app/user/domain.py::User.is_staff_or_above` | **활용** (변경 없음, 사용처 추가) |
| 외부 API | **변화 (의도)** — 공개 조회 응답에서 `inventory` 키 제거 |
| OpenAPI 스펙 | `ProductPublicView` 추가, Union 응답 명시 |
| DB 스키마 | 변화 없음 |
| 신규 테스트 | +5 케이스 |

---

## 7. 리스크

| 리스크 | 가능성 | 대응 |
| --- | --- | --- |
| 기존 클라이언트가 공개 조회 응답에서 `inventory` 기대 | 중 | 본 프로젝트는 데모. PR description 에 변경 매트릭스 명시. 후속에서 환경 변수 옵션화 가능 |
| `get_optional_current_user` 의 토큰 검증 로직 중복 | 중 | `get_current_user` 의 로직을 share — 내부 헬퍼 추출 검토 (본 PR 범위 안). 또는 PLAN 단계에서 결정 |
| Union 응답이 잘못된 모델로 직렬화 | 낮음 | viewer 분기에서 명시적으로 다른 객체 반환 — 회귀 가드 #1, #3 가 검증 |
| `is_staff_or_above` 가 STAFF / ADMIN 만 True 인지 확인 | 낮음 | PR #4 의 도메인 메서드 확인 — 이미 정확히 정의 |
| 테스트의 anonymous client (헤더 없음) 와 fixture 의 admin_auth_headers 분리 | 낮음 | conftest 의 client fixture 가 그대로 사용 가능. anonymous 는 headers 없이 호출 |

---

## 8. 결정 사항 (확정)

- [x] 스키마 분리: `ProductPublicView` (공개) vs `ProductResponse` (관리/staff)
- [x] 공개 응답에서 **inventory 제외** (`price`, `is_active` 는 그대로 노출)
- [x] viewer 분기 기준: `current_user.is_staff_or_above()` — STAFF + ADMIN 통과
- [x] 인증 없이도 접근 가능 — `get_optional_current_user` 의존성 신규
- [x] 변경 작업 (POST/PUT/DELETE/PATCH inventory) 은 admin only 유지 (본 PR 비목적)
- [x] `GET /products/{id}` 의 `response_model=Union[ProductPublicView, ProductResponse]` (OpenAPI 두 형태 노출)
- [x] `GET /products/` 의 `response_model=Union[List[ProductPublicView], List[ProductResponse]]`
- [x] 신규 의존성 `get_optional_current_user` 는 `get_current_user` 의 토큰 검증을 재사용 (헬퍼 추출 또는 직접 구현) — PLAN 단계에서 결정

---

## 9. 참고

- `docs/[PRD]권한_분기_의존성_추출.md` (PR #10)
- `docs/[PRD]UserResponse_PII_마스킹.md` (PR #15) — 동일 응답 분리 패턴 참고
- `docs/[PRD]UserRole_enum_정합성.md` (PR #4) — `is_staff_or_above` 도메인 메서드
- `app/product/schemas.py`, `app/product/router.py`, `app/api/dependencies.py`
