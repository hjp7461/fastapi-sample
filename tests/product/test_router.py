"""
상품 API 엔드포인트 테스트.
pytest==8.3.5, pytest-asyncio==0.26.0 버전에 맞게 작성되었습니다.
"""

from decimal import Decimal
from typing import Any, Dict

import pytest
from httpx import AsyncClient

from app.user.domain import UserRole

# pytest 8.3.5에서는 이제 Test 클래스 대신 함수에 직접 마커를 적용합니다
# pytestmark = pytest.mark.asyncio  # 불필요


# tests/product/test_router.py 수정 예시
@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_get_product(client: AsyncClient, test_product: Dict[str, Any]) -> None:
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
    created_product = create_response.json()
    product_id = created_product["id"]

    # 6. 등록된 상품 조회
    get_response = await client.get(f"/api/v1/products/{product_id}")

    # 7. 응답 검증
    assert get_response.status_code == 200


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_list_products(client: AsyncClient, test_product: Dict[str, Any]) -> None:
    """상품 목록 조회 테스트."""
    response = await client.get("/api/v1/products/")

    assert response.status_code == 200
    data = response.json()
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
    client: AsyncClient, auth_headers: Dict[str, str]
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
    client: AsyncClient, admin_auth_headers: Dict[str, str]
) -> None:
    """관리자의 상품 생성 테스트."""
    product_data: Dict[str, Any] = {
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
    data = response.json()
    assert data["name"] == product_data["name"]
    assert data["description"] == product_data["description"]
    assert Decimal(data["price"]) == Decimal(product_data["price"])
    assert data["inventory"] == product_data["inventory"]


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_update_product_as_admin(
    client: AsyncClient,
    admin_auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
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
    data = response.json()
    assert data["id"] == product_id
    assert data["name"] == update_data["name"]
    assert data["description"] == update_data["description"]
    assert Decimal(data["price"]) == Decimal(update_data["price"])


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_update_inventory_as_admin(
    client: AsyncClient,
    admin_auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
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
    initial_inventory = initial_response.json()["inventory"]

    # 재고 업데이트
    response = await client.patch(
        f"/api/v1/products/{product_id}/inventory",
        json=inventory_update,
        headers=admin_auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == product_id
    assert data["inventory"] == initial_inventory + inventory_update["quantity_change"]


@pytest.mark.asyncio
async def test_update_inventory_exact_zero(
    client: AsyncClient,
    admin_auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
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
    assert response.json()["inventory"] == 0


@pytest.mark.asyncio
async def test_update_inventory_insufficient(
    client: AsyncClient,
    admin_auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
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
    data = response.json()
    assert "detail" in data

    # silent failure 방지: 재고가 변경되지 않았는지 확인 (admin 컨텍스트 필요)
    get_response = await client.get(
        f"/api/v1/products/{product_id}", headers=admin_auth_headers
    )
    assert get_response.status_code == 200
    assert get_response.json()["inventory"] == 10


@pytest.mark.asyncio
async def test_update_inventory_concurrent_deduction(
    client: AsyncClient,
    admin_auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
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
    assert get_response.json()["inventory"] == 0


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_delete_product_as_admin(
    client: AsyncClient,
    admin_auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
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
    client: AsyncClient, test_product: Dict[str, Any]
) -> None:
    """카테고리별 상품 필터링 테스트."""
    # 테스트 상품의 카테고리 확인
    product_response = await client.get(f"/api/v1/products/{test_product['id']}")
    product_category = product_response.json()["category"]

    # 해당 카테고리로 필터링
    response = await client.get(f"/api/v1/products/?category={product_category}")

    assert response.status_code == 200
    data = response.json()
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
    data = response.json()

    # 모든 상품이 활성 상태인지 확인
    for product in data:
        assert product["is_active"] is True


# ----------------------------------------------------------------------------
# 조회 컨텍스트 분리 회귀 가드 (PR #19)
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_product_anonymous_returns_public_view(
    client: AsyncClient,
    test_product: Dict[str, Any],
) -> None:
    """인증 없는 조회 → ProductPublicView (inventory 없음)."""
    response = await client.get(f"/api/v1/products/{test_product['id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_product["id"]
    assert data["name"] == test_product["name"]
    assert "inventory" not in data


@pytest.mark.asyncio
async def test_get_product_as_customer_returns_public_view(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
) -> None:
    """일반 사용자 조회 → ProductPublicView (inventory 없음)."""
    response = await client.get(
        f"/api/v1/products/{test_product['id']}", headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_product["id"]
    assert "inventory" not in data


@pytest.mark.asyncio
async def test_get_product_as_admin_returns_full(
    client: AsyncClient,
    admin_auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
) -> None:
    """관리자 조회 → ProductResponse (inventory 포함)."""
    response = await client.get(
        f"/api/v1/products/{test_product['id']}", headers=admin_auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_product["id"]
    assert "inventory" in data
    assert data["inventory"] == 10  # test_product fixture


@pytest.mark.asyncio
async def test_list_products_anonymous_excludes_inventory(
    client: AsyncClient,
    test_product: Dict[str, Any],
) -> None:
    """인증 없는 목록 → 모든 항목 inventory 없음."""
    response = await client.get("/api/v1/products/")

    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    assert len(items) > 0
    for item in items:
        assert "inventory" not in item


@pytest.mark.asyncio
async def test_list_products_as_admin_includes_inventory(
    client: AsyncClient,
    admin_auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
) -> None:
    """관리자 목록 → 모든 항목 inventory 포함."""
    response = await client.get("/api/v1/products/", headers=admin_auth_headers)

    assert response.status_code == 200
    items = response.json()
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
    client: AsyncClient, staff_auth_headers: Dict[str, str]
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
    data = response.json()
    assert data["name"] == product_data["name"]


@pytest.mark.asyncio
async def test_update_product_as_staff(
    client: AsyncClient,
    staff_auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
) -> None:
    """staff 의 상품 업데이트 통과 (200)."""
    product_id = test_product["id"]
    update_data = {"name": "Staff Updated Name"}

    response = await client.put(
        f"/api/v1/products/{product_id}", json=update_data, headers=staff_auth_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == update_data["name"]


@pytest.mark.asyncio
async def test_update_inventory_as_staff(
    client: AsyncClient,
    staff_auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
) -> None:
    """staff 의 재고 변경 통과 (200) — 일상 운영 시나리오의 핵심 경로."""
    product_id = test_product["id"]

    response = await client.patch(
        f"/api/v1/products/{product_id}/inventory",
        headers=staff_auth_headers,
        json={"quantity_change": 3},
    )

    assert response.status_code == 200
    assert response.json()["inventory"] == test_product.get("inventory", 10) + 3


@pytest.mark.asyncio
async def test_delete_product_as_staff(
    client: AsyncClient,
    staff_auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
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
    auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
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
    auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
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
    auth_headers: Dict[str, str],
    test_product: Dict[str, Any],
) -> None:
    """customer 의 상품 삭제 거부 (403)."""
    response = await client.delete(
        f"/api/v1/products/{test_product['id']}",
        headers=auth_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_product_anonymous_unauthenticated(
    client: AsyncClient, test_product: Dict[str, Any]
) -> None:
    """토큰 없는 변경 요청은 401 (가드 진입 전 인증 단계에서 차단).

    `test_create_product_unauthorized` 의 PUT 버전 — 변경 동작 전반의
    인증 회귀 가드를 명시.
    """
    response = await client.put(
        f"/api/v1/products/{test_product['id']}", json={"name": "Anon"}
    )

    assert response.status_code == 401
