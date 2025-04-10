"""
상품 API 엔드포인트 테스트.
pytest==8.3.5, pytest-asyncio==0.26.0 버전에 맞게 작성되었습니다.
"""
import pytest
from httpx import AsyncClient
from typing import Dict, Any
from decimal import Decimal


# pytest 8.3.5에서는 이제 Test 클래스 대신 함수에 직접 마커를 적용합니다
# pytestmark = pytest.mark.asyncio  # 불필요


# tests/product/test_router.py 수정 예시
@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_get_product(client, test_product):
    """상품 조회 테스트."""
    # 1. 관리자 사용자 생성
    admin_data = {
        "email": "admin@example.com",
        "username": "adminuser",
        "password": "adminpassword",
        "password_confirm": "adminpassword",
        "first_name": "Admin",
        "last_name": "User",
        "role": "admin",  # 관리자 역할 지정
        "is_active": True
    }

    # 사용자 등록 API 호출
    register_response = await client.post(
        "/api/v1/users/",
        json=admin_data
    )

    # 사용자 등록 확인
    if register_response.status_code != 201:
        print(f"Admin registration failed: {register_response.text}")
    assert register_response.status_code == 201
    admin_user = register_response.json()

    # 2. 관리자 로그인을 통해 토큰 얻기
    login_data = {
        "username": admin_data["email"],
        "password": admin_data["password"]
    }

    # 폼 데이터로 변경하여 로그인 요청
    login_response = await client.post(
        "/api/v1/users/token",
        data=login_data  # JSON이 아닌 폼 데이터로 전송
    )

    # 로그인 응답 확인
    assert login_response.status_code == 200, f"Login failed: {login_response.text}"
    token_data = login_response.json()

    # 디버깅을 위한 응답 출력
    print(f"Login response: {login_response.text}")

    # 토큰이 있는지 확인
    assert "access_token" in token_data, f"access_token not found in response: {token_data}"

    # 인증 헤더 생성
    admin_auth_headers = {"Authorization": f"Bearer {token_data['access_token']}"}

    # 3. 상품 등록 데이터 준비
    product_data = {
        "name": "Test Product",
        "description": "Test product description",
        "price": "99.99",
        "category": "electronics",
        "inventory": 10,
        "is_active": True
    }

    # 4. 관리자 권한으로 상품 등록
    create_response = await client.post(
        "/api/v1/products/",
        json=product_data,
        headers=admin_auth_headers
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
    product = get_response.json()


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_list_products(client: AsyncClient, test_product: Dict[str, Any]):
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
async def test_create_product_unauthorized(client: AsyncClient):
    """인증되지 않은 사용자의 상품 생성 시도 테스트."""
    product_data = {
        "name": "New Product",
        "description": "New product description",
        "price": "199.99",
        "category": "electronics",
        "inventory": 50
    }

    response = await client.post("/api/v1/products/", json=product_data)

    # 인증되지 않은 요청은 거부되어야 함
    assert response.status_code == 401


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_create_product_as_regular_user(client: AsyncClient, auth_headers: Dict[str, str]):
    """일반 사용자의 상품 생성 시도 테스트."""
    product_data = {
        "name": "New Product",
        "description": "New product description",
        "price": "199.99",
        "category": "electronics",
        "inventory": 50
    }

    response = await client.post("/api/v1/products/", json=product_data, headers=auth_headers)

    # 일반 사용자는 상품 생성 권한이 없어야 함
    assert response.status_code == 403


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_create_product_as_admin(client: AsyncClient, admin_auth_headers: Dict[str, str]):
    """관리자의 상품 생성 테스트."""
    product_data = {
        "name": "Admin's Product",
        "description": "Product created by admin",
        "price": "299.99",
        "category": "electronics",
        "inventory": 100
    }

    response = await client.post("/api/v1/products/", json=product_data, headers=admin_auth_headers)

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
        test_product: Dict[str, Any]
):
    """관리자의 상품 업데이트 테스트."""
    product_id = test_product["id"]
    update_data = {
        "name": "Updated Product",
        "description": "Updated product description",
        "price": "149.99"
    }

    response = await client.put(
        f"/api/v1/products/{product_id}",
        json=update_data,
        headers=admin_auth_headers
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
        test_product: Dict[str, Any]
):
    """관리자의 상품 재고 업데이트 테스트."""
    product_id = test_product["id"]
    inventory_update = {
        "quantity_change": 5  # 재고 5개 증가
    }

    # 먼저 현재 재고 확인
    initial_response = await client.get(f"/api/v1/products/{product_id}")
    initial_inventory = initial_response.json()["inventory"]

    # 재고 업데이트
    response = await client.patch(
        f"/api/v1/products/{product_id}/inventory",
        json=inventory_update,
        headers=admin_auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == product_id
    assert data["inventory"] == initial_inventory + inventory_update["quantity_change"]


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_delete_product_as_admin(
        client: AsyncClient,
        admin_auth_headers: Dict[str, str],
        test_product: Dict[str, Any]
):
    """관리자의 상품 삭제 테스트."""
    product_id = test_product["id"]

    response = await client.delete(
        f"/api/v1/products/{product_id}",
        headers=admin_auth_headers
    )

    assert response.status_code == 204

    # 삭제된 상품 조회 시도
    get_response = await client.get(f"/api/v1/products/{product_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_filter_products_by_category(client: AsyncClient, test_product: Dict[str, Any]):
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
async def test_filter_products_by_active_status(client: AsyncClient):
    """활성 상태별 상품 필터링 테스트."""
    # 활성 상품만 필터링
    response = await client.get("/api/v1/products/?is_active=true")

    assert response.status_code == 200
    data = response.json()

    # 모든 상품이 활성 상태인지 확인
    for product in data:
        assert product["is_active"] is True