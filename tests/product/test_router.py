"""
상품 API 엔드포인트 테스트.
pytest==8.3.5, pytest-asyncio==0.26.0 버전에 맞게 작성되었습니다.
"""

from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.domain import UserRole


# tests/product/test_router.py 수정 예시
@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_get_product(client: AsyncClient, test_product: dict[str, Any]) -> None:
    """상품 조회 테스트."""
    # 1. 관리자 사용자 생성
    admin_data = {
        "email": "admin@example.com",
        "username": "adminuser",
        "password": "adminpassword",
        "password_confirm": "adminpassword",
        "first_name": "Admin",
        "last_name": "User",
        "role": UserRole.ADMIN.value,  # 관리자 역할 지정
        "is_active": True,
    }

    # 사용자 등록 API 호출
    register_response = await client.post("/api/v1/users/", json=admin_data)

    # 사용자 등록 확인
    if register_response.status_code != 201:
        print(f"Admin registration failed: {register_response.text}")
    assert register_response.status_code == 201

    # 2. 관리자 로그인을 통해 토큰 얻기
    login_data = {"username": admin_data["email"], "password": admin_data["password"]}

    # 폼 데이터로 변경하여 로그인 요청
    login_response = await client.post(
        "/api/v1/users/token",
        data=login_data,  # JSON이 아닌 폼 데이터로 전송
    )

    # 로그인 응답 확인
    assert login_response.status_code == 200, f"Login failed: {login_response.text}"
    token_data = login_response.json()

    # 디버깅을 위한 응답 출력
    print(f"Login response: {login_response.text}")

    # 토큰이 있는지 확인
    assert "access_token" in token_data, (
        f"access_token not found in response: {token_data}"
    )

    # 인증 헤더 생성
    admin_auth_headers = {"Authorization": f"Bearer {token_data['access_token']}"}

    # 3. 상품 등록 데이터 준비
    product_data = {
        "name": "Test Product",
        "description": "Test product description",
        "price": "99.99",
        "category": "electronics",
        "inventory": 10,
        "is_active": True,
    }

    # 4. 관리자 권한으로 상품 등록
    create_response = await client.post(
        "/api/v1/products/", json=product_data, headers=admin_auth_headers
    )

    # 응답 확인 (오류 시 자세한 정보 표시)
    if create_response.status_code != 201:
        print(f"Create product failed: {create_response.text}")

    # 5. 상품 등록 응답 확인
    assert create_response.status_code == 201
    created_product = create_response.json()["data"]
    product_id = created_product["id"]

    # 6. 등록된 상품 조회
    get_response = await client.get(f"/api/v1/products/{product_id}")

    # 7. 응답 검증
    assert get_response.status_code == 200


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_list_products(client: AsyncClient, test_product: dict[str, Any]) -> None:
    """상품 목록 조회 테스트."""
    response = await client.get("/api/v1/products/")

    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)
    assert len(data) > 0

    # 테스트 상품이 목록에 있는지 확인
    product_ids = [product["id"] for product in data]
    assert test_product["id"] in product_ids


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_create_product_unauthorized(client: AsyncClient) -> None:
    """인증되지 않은 사용자의 상품 생성 시도 테스트."""
    product_data = {
        "name": "New Product",
        "description": "New product description",
        "price": "199.99",
        "category": "electronics",
        "inventory": 50,
    }

    response = await client.post("/api/v1/products/", json=product_data)

    # 인증되지 않은 요청은 거부되어야 함
    assert response.status_code == 401


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_create_product_as_regular_user(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """일반 사용자의 상품 생성 시도 테스트."""
    product_data = {
        "name": "New Product",
        "description": "New product description",
        "price": "199.99",
        "category": "electronics",
        "inventory": 50,
    }

    response = await client.post(
        "/api/v1/products/", json=product_data, headers=auth_headers
    )

    # 일반 사용자는 상품 생성 권한이 없어야 함
    assert response.status_code == 403


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_create_product_as_admin(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    """관리자의 상품 생성 테스트."""
    product_data: dict[str, Any] = {
        "name": "Admin's Product",
        "description": "Product created by admin",
        "price": "299.99",
        "category": "electronics",
        "inventory": 100,
    }

    response = await client.post(
        "/api/v1/products/", json=product_data, headers=admin_auth_headers
    )

    # 관리자는 상품 생성이 가능해야 함
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == product_data["name"]
    assert data["description"] == product_data["description"]
    assert Decimal(data["price"]) == Decimal(product_data["price"])
    assert data["inventory"] == product_data["inventory"]


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_update_product_as_admin(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """관리자의 상품 업데이트 테스트."""
    product_id = test_product["id"]
    update_data = {
        "name": "Updated Product",
        "description": "Updated product description",
        "price": "149.99",
    }

    response = await client.put(
        f"/api/v1/products/{product_id}", json=update_data, headers=admin_auth_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == product_id
    assert data["name"] == update_data["name"]
    assert data["description"] == update_data["description"]
    assert Decimal(data["price"]) == Decimal(update_data["price"])


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_update_inventory_as_admin(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """관리자의 상품 재고 업데이트 테스트."""
    product_id = test_product["id"]
    inventory_update = {
        "quantity_change": 5  # 재고 5개 증가
    }

    # 먼저 현재 재고 확인 (admin 컨텍스트 — public view 는 inventory 없음)
    initial_response = await client.get(
        f"/api/v1/products/{product_id}", headers=admin_auth_headers
    )
    initial_inventory = initial_response.json()["data"]["inventory"]

    # 재고 업데이트
    response = await client.patch(
        f"/api/v1/products/{product_id}/inventory",
        json=inventory_update,
        headers=admin_auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == product_id
    assert data["inventory"] == initial_inventory + inventory_update["quantity_change"]


@pytest.mark.asyncio
async def test_update_inventory_exact_zero(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """quantity_change 가 현재 재고와 정확히 일치 → 200 + inventory=0."""
    # test_product fixture: inventory=10
    product_id = test_product["id"]
    response = await client.patch(
        f"/api/v1/products/{product_id}/inventory",
        headers=admin_auth_headers,
        json={"quantity_change": -10},
    )

    assert response.status_code == 200
    assert response.json()["data"]["inventory"] == 0


@pytest.mark.asyncio
async def test_update_inventory_insufficient(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """현재 재고보다 1 많이 차감 시도 → 400 + 재고는 그대로."""
    # test_product fixture: inventory=10
    product_id = test_product["id"]
    response = await client.patch(
        f"/api/v1/products/{product_id}/inventory",
        headers=admin_auth_headers,
        json={"quantity_change": -11},
    )

    assert response.status_code == 400
    data = response.json()  # error envelope (handler 가 처리, SuccessEnvelope 비적용)
    assert "detail" in data

    # silent failure 방지: 재고가 변경되지 않았는지 확인 (admin 컨텍스트 필요)
    get_response = await client.get(
        f"/api/v1/products/{product_id}", headers=admin_auth_headers
    )
    assert get_response.status_code == 200
    assert get_response.json()["data"]["inventory"] == 10


@pytest.mark.asyncio
async def test_update_inventory_concurrent_deduction(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """동시 차감 2건 (-10, -10) 시 정확히 1건만 200, 1건은 400.

    StaticPool 단일 커넥션 환경이라 실제 OS 레벨 race 재현은 어렵지만,
    조건부 UPDATE 의 시멘틱이 정상 동작하는지 구조적으로 검증한다.
    """
    import asyncio

    product_id = test_product["id"]
    # test_product fixture: inventory=10
    responses = await asyncio.gather(
        client.patch(
            f"/api/v1/products/{product_id}/inventory",
            headers=admin_auth_headers,
            json={"quantity_change": -10},
        ),
        client.patch(
            f"/api/v1/products/{product_id}/inventory",
            headers=admin_auth_headers,
            json={"quantity_change": -10},
        ),
    )

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200, 400], f"기대: [200, 400], 실제: {statuses}"

    # 최종 재고는 0 (음수 아님) — admin 컨텍스트로 확인
    get_response = await client.get(
        f"/api/v1/products/{product_id}", headers=admin_auth_headers
    )
    assert get_response.json()["data"]["inventory"] == 0


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_delete_product_as_admin(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """관리자의 상품 삭제 테스트."""
    product_id = test_product["id"]

    response = await client.delete(
        f"/api/v1/products/{product_id}", headers=admin_auth_headers
    )

    assert response.status_code == 204

    # 삭제된 상품 조회 시도
    get_response = await client.get(f"/api/v1/products/{product_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_filter_products_by_category(
    client: AsyncClient, test_product: dict[str, Any]
) -> None:
    """카테고리별 상품 필터링 테스트."""
    # 테스트 상품의 카테고리 확인
    product_response = await client.get(f"/api/v1/products/{test_product['id']}")
    product_category = product_response.json()["data"]["category"]

    # 해당 카테고리로 필터링
    response = await client.get(f"/api/v1/products/?category={product_category}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)
    assert len(data) > 0

    # 모든 상품이 요청한 카테고리에 속하는지 확인
    for product in data:
        assert product["category"] == product_category


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_filter_products_by_active_status(client: AsyncClient) -> None:
    """활성 상태별 상품 필터링 테스트."""
    # 활성 상품만 필터링
    response = await client.get("/api/v1/products/?is_active=true")

    assert response.status_code == 200
    data = response.json()["data"]

    # 모든 상품이 활성 상태인지 확인
    for product in data:
        assert product["is_active"] is True


# ----------------------------------------------------------------------------
# 조회 컨텍스트 분리 회귀 가드 (PR #19)
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_product_anonymous_returns_public_view(
    client: AsyncClient,
    test_product: dict[str, Any],
) -> None:
    """인증 없는 조회 → ProductPublicView (inventory 없음)."""
    response = await client.get(f"/api/v1/products/{test_product['id']}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == test_product["id"]
    assert data["name"] == test_product["name"]
    assert "inventory" not in data


@pytest.mark.asyncio
async def test_get_product_as_customer_returns_public_view(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """일반 사용자 조회 → ProductPublicView (inventory 없음)."""
    response = await client.get(
        f"/api/v1/products/{test_product['id']}", headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == test_product["id"]
    assert "inventory" not in data


@pytest.mark.asyncio
async def test_get_product_as_admin_returns_full(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """관리자 조회 → ProductResponse (inventory 포함)."""
    response = await client.get(
        f"/api/v1/products/{test_product['id']}", headers=admin_auth_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == test_product["id"]
    assert "inventory" in data
    assert data["inventory"] == 10  # test_product fixture


@pytest.mark.asyncio
async def test_list_products_anonymous_excludes_inventory(
    client: AsyncClient,
    test_product: dict[str, Any],
) -> None:
    """인증 없는 목록 → 모든 항목 inventory 없음."""
    response = await client.get("/api/v1/products/")

    assert response.status_code == 200
    items = response.json()["data"]
    assert isinstance(items, list)
    assert len(items) > 0
    for item in items:
        assert "inventory" not in item


@pytest.mark.asyncio
async def test_list_products_as_admin_includes_inventory(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """관리자 목록 → 모든 항목 inventory 포함."""
    response = await client.get("/api/v1/products/", headers=admin_auth_headers)

    assert response.status_code == 200
    items = response.json()["data"]
    assert isinstance(items, list)
    assert len(items) > 0
    for item in items:
        assert "inventory" in item


# ---------------------------------------------------------------------------
# staff 권한 회귀 가드 (PRD: staff 권한 정책 확장)
#
# 정책: STAFF 사용자는 product 변경 4개 (POST/PUT/DELETE/PATCH-inventory) 통과.
# customer (regular_user) 는 변경 4개 모두 403.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_product_as_staff(
    client: AsyncClient, staff_auth_headers: dict[str, str]
) -> None:
    """staff 의 상품 생성 통과 (201)."""
    product_data = {
        "name": "Staff Product",
        "description": "Product created by staff",
        "price": "49.99",
        "category": "electronics",
        "inventory": 20,
    }

    response = await client.post(
        "/api/v1/products/", json=product_data, headers=staff_auth_headers
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == product_data["name"]


@pytest.mark.asyncio
async def test_update_product_as_staff(
    client: AsyncClient,
    staff_auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """staff 의 상품 업데이트 통과 (200)."""
    product_id = test_product["id"]
    update_data = {"name": "Staff Updated Name"}

    response = await client.put(
        f"/api/v1/products/{product_id}", json=update_data, headers=staff_auth_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["name"] == update_data["name"]


@pytest.mark.asyncio
async def test_update_inventory_as_staff(
    client: AsyncClient,
    staff_auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """staff 의 재고 변경 통과 (200) — 일상 운영 시나리오의 핵심 경로."""
    product_id = test_product["id"]

    response = await client.patch(
        f"/api/v1/products/{product_id}/inventory",
        headers=staff_auth_headers,
        json={"quantity_change": 3},
    )

    assert response.status_code == 200
    assert response.json()["data"]["inventory"] == test_product.get("inventory", 10) + 3


@pytest.mark.asyncio
async def test_delete_product_as_staff(
    client: AsyncClient,
    staff_auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """staff 의 상품 삭제 통과 (204)."""
    product_id = test_product["id"]

    response = await client.delete(
        f"/api/v1/products/{product_id}", headers=staff_auth_headers
    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_update_product_as_regular_user_forbidden(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """customer 의 상품 업데이트 거부 (403)."""
    response = await client.put(
        f"/api/v1/products/{test_product['id']}",
        json={"name": "Hacked"},
        headers=auth_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_inventory_as_regular_user_forbidden(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """customer 의 재고 변경 거부 (403)."""
    response = await client.patch(
        f"/api/v1/products/{test_product['id']}/inventory",
        json={"quantity_change": -1},
        headers=auth_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_product_as_regular_user_forbidden(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_product: dict[str, Any],
) -> None:
    """customer 의 상품 삭제 거부 (403)."""
    response = await client.delete(
        f"/api/v1/products/{test_product['id']}",
        headers=auth_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_product_anonymous_unauthenticated(
    client: AsyncClient, test_product: dict[str, Any]
) -> None:
    """토큰 없는 변경 요청은 401 (가드 진입 전 인증 단계에서 차단).

    `test_create_product_unauthorized` 의 PUT 버전 — 변경 동작 전반의
    인증 회귀 가드를 명시.
    """
    response = await client.put(
        f"/api/v1/products/{test_product['id']}", json={"name": "Anon"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_products_paginated_envelope(
    client: AsyncClient, test_product: dict[str, Any]
) -> None:
    """PR #52: GET /products/ 응답이 `{data, meta: {total, skip, limit}}` 형식.

    middleware idempotent 룰 (dict + data 키 → wrap skip) 회귀 가드 겸용.
    """
    response = await client.get("/api/v1/products/?skip=0&limit=20")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "meta" in body
    assert isinstance(body["data"], list)
    assert body["meta"]["skip"] == 0
    assert body["meta"]["limit"] == 20
    assert body["meta"]["total"] >= 1  # test_product 최소 1


@pytest.mark.asyncio
async def test_list_products_filter_count_matches(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """PR #52: `is_active=true/false` 필터 시 meta.total 이 필터 후 카운트.

    전체 count 가 아니라 필터 적용 후 카운트인지 — repository.count(filter) 회귀.
    """
    from app.product.domain import ProductCategory
    from app.product.models import ProductModel

    # active=true 1건, active=false 1건 추가
    active = ProductModel(
        name="active-1",
        description="x",
        price=Decimal("1.00"),
        category=ProductCategory.ELECTRONICS,
        inventory=1,
        is_active=True,
    )
    inactive = ProductModel(
        name="inactive-1",
        description="x",
        price=Decimal("1.00"),
        category=ProductCategory.ELECTRONICS,
        inventory=1,
        is_active=False,
    )
    db_session.add_all([active, inactive])
    await db_session.commit()

    # is_active=false → inactive 만 포함
    response_inactive = await client.get(
        "/api/v1/products/?is_active=false", headers=admin_auth_headers
    )
    assert response_inactive.status_code == 200
    body_inactive = response_inactive.json()
    inactive_total = body_inactive["meta"]["total"]
    inactive_count_in_data = len(body_inactive["data"])
    # 필터 적용된 결과만 카운트 (전체 카운트 아님)
    assert inactive_total == inactive_count_in_data
    assert inactive_total >= 1  # 최소 방금 추가한 inactive 1건


@pytest.mark.parametrize(
    ("params", "expected_status", "expected_code"),
    [
        # Pydantic Query 검증 → request_validation_error
        ({"skip": -1}, 422, "request_validation_error"),
        ({"limit": 0}, 422, "request_validation_error"),
        # limit > LIST_MAX_LIMIT (default 1000) → dependency
        # 내부 HTTPException → http_422
        ({"limit": 1001}, 422, "http_422"),
        ({"skip": 0, "limit": 1000}, 200, None),
    ],
)
@pytest.mark.asyncio
async def test_list_products_query_constraints(
    client: AsyncClient,
    params: dict[str, int],
    expected_status: int,
    expected_code: str | None,
) -> None:
    """PR #52 + PR ##: product 도 동일 가드 (skip≥0 / limit≥1 Pydantic,
    limit ≤ LIST_MAX_LIMIT dependency)."""
    response = await client.get("/api/v1/products/", params=params)
    assert response.status_code == expected_status
    if expected_status == 422:
        assert response.json()["detail"]["code"] == expected_code


@pytest.mark.asyncio
async def test_list_products_page_mode_envelope(
    client: AsyncClient, test_product: dict[str, Any]
) -> None:
    """PRD §5.6 (product): GET /products/?page=&per_page= 응답이 page 모드 meta.

    `{data, meta: {total, page, per_page, total_pages}}` 형식 — offset 모드
    필드 (skip/limit) 미포함. test_product 1건 시드.
    """
    response = await client.get("/api/v1/products/?page=1&per_page=5")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "meta" in body
    meta = body["meta"]
    assert meta["page"] == 1
    assert meta["per_page"] == 5
    assert isinstance(meta["total"], int)
    assert isinstance(meta["total_pages"], int)
    assert meta["total"] >= 1
    assert "skip" not in meta
    assert "limit" not in meta


@pytest.mark.asyncio
async def test_list_products_page_mode_with_category_filter(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """PRD §5.6 (product): 필터 + page 모드 — total 이 필터 후 카운트.

    BOOK 카테고리 2건 시드 → ?category=BOOK&page=1&per_page=5 가
    필터된 항목만 data 에 포함 + meta.total 도 필터 반영.
    """
    from app.product.domain import ProductCategory
    from app.product.models import ProductModel

    books = [
        ProductModel(
            name=f"book-{i}",
            description="x",
            price=Decimal("1.00"),
            category=ProductCategory.BOOKS,
            inventory=1,
            is_active=True,
        )
        for i in range(2)
    ]
    db_session.add_all(books)
    await db_session.commit()

    response = await client.get(
        "/api/v1/products/?category=books&page=1&per_page=5",
        headers=admin_auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    meta = body["meta"]
    assert meta["page"] == 1
    assert meta["per_page"] == 5
    assert meta["total"] == len(body["data"])
    assert meta["total"] >= 2
    # 필터 적용 — data 의 모든 항목이 BOOKS
    assert all(p["category"] == "books" for p in body["data"])


@pytest.mark.parametrize(
    ("params", "expected_status", "expected_code"),
    [
        # Pydantic Query 검증 → request_validation_error
        ({"page": 0}, 422, "request_validation_error"),
        ({"page": -1, "per_page": 10}, 422, "request_validation_error"),
        ({"page": 1, "per_page": 0}, 422, "request_validation_error"),
        # per_page > LIST_MAX_LIMIT (default 1000) → enforce_per_page_max
        # 내부 HTTPException → http_422
        ({"page": 1, "per_page": 1001}, 422, "http_422"),
        ({"page": 1, "per_page": 1000}, 200, None),
    ],
)
@pytest.mark.asyncio
async def test_list_products_page_mode_query_constraints(
    client: AsyncClient,
    params: dict[str, int],
    expected_status: int,
    expected_code: str | None,
) -> None:
    """PRD §5.6 (product) + PR ##: page/per_page Query 제약 + per_page ≤
    LIST_MAX_LIMIT enforce."""
    response = await client.get("/api/v1/products/", params=params)
    assert response.status_code == expected_status
    if expected_status == 422:
        assert response.json()["detail"]["code"] == expected_code


# --- list limit default / max 환경 변수화 회귀 가드 ---


@pytest.mark.asyncio
async def test_list_products_default_limit_independent_from_user(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    test_product: dict[str, Any],
) -> None:
    """PR ##: user / product default 가 독립 — 각 자원별 factory dependency.

    `USER_LIST_DEFAULT_LIMIT=50`, `PRODUCT_LIST_DEFAULT_LIMIT=20` 설정 후
    각 endpoint 의 meta.limit 이 자원별 값으로 분리되는지 회귀 가드
    (factory 가 자원별 default_limit_attr 캡처 — 공유 상태 회귀 차단).
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "USER_LIST_DEFAULT_LIMIT", 50)
    monkeypatch.setattr(settings, "PRODUCT_LIST_DEFAULT_LIMIT", 20)

    products = await client.get("/api/v1/products/", headers=admin_auth_headers)
    users = await client.get("/api/v1/users/", headers=admin_auth_headers)

    assert products.status_code == 200
    assert users.status_code == 200
    assert products.json()["meta"]["limit"] == 20
    assert users.json()["meta"]["limit"] == 50
