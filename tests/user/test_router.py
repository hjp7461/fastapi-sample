"""
사용자 API 엔드포인트 테스트.
pytest==8.3.5, pytest-asyncio==0.26.0 버전에 맞게 작성되었습니다.
"""
import pytest
from httpx import AsyncClient
from typing import Dict, Any


# pytest-asyncio 8.3.5에서는 이제 Test 클래스 대신 함수에 직접 마커를 적용
# pytestmark = pytest.mark.asyncio  # 불필요


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_create_user(client: AsyncClient):
    """사용자 생성 테스트."""
    user_data = {
        "email": "newuser@example.com",
        "username": "newuser",
        "password": "newpassword123",
        "password_confirm": "newpassword123",
    }

    response = await client.post("/api/v1/users/", json=user_data)

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == user_data["email"]
    assert data["username"] == user_data["username"]
    assert "id" in data
    assert "password" not in data


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_login(client: AsyncClient, test_user: Dict[str, Any]):
    """사용자 로그인 테스트."""
    login_data = {
        "username": test_user["email"],  # 이메일을 사용자명으로 사용
        "password": test_user["password"],
    }

    response = await client.post("/api/v1/users/token", data=login_data)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_upgrades_old_bcrypt_hash(
        client: AsyncClient,
        db_session,
):
    """저장된 비밀번호 해시가 낮은 라운드면, 로그인 직후 자동 업그레이드된다.

    PR #7 (bcrypt 라운드 환경별 설정) + 본 PR (lazy rehash) 의 시너지를 검증.
    운영자가 BCRYPT_ROUNDS 를 상향한 후, 기존 사용자의 해시가 로그인 시
    자동으로 새 라운드로 업그레이드되는 것이 핵심.
    """
    import bcrypt as _bcrypt
    from app.core.config import settings
    from app.user.models import UserModel

    plain = "passwd1234"
    # 의도적으로 낮은 라운드 (4) 로 시드 — settings 가 12 이면 자동 업그레이드 대상
    old_hash = _bcrypt.hashpw(
        plain.encode("utf-8"), _bcrypt.gensalt(rounds=4)
    ).decode("utf-8")

    user = UserModel(
        email="legacy@example.com",
        username="legacy",
        hashed_password=old_hash,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # 로그인
    response = await client.post(
        "/api/v1/users/token",
        data={"username": "legacy@example.com", "password": plain},
    )
    assert response.status_code == 200

    # DB 의 해시가 settings.BCRYPT_ROUNDS 로 업그레이드되었는지 확인
    await db_session.refresh(user)
    new_rounds = int(user.hashed_password.split("$")[2])
    assert new_rounds == settings.BCRYPT_ROUNDS, (
        f"expected {settings.BCRYPT_ROUNDS} rounds, got {new_rounds}"
    )
    assert user.hashed_password != old_hash


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_get_current_user(client: AsyncClient, auth_headers: Dict[str, str], test_user: Dict[str, Any]):
    """현재 사용자 정보 조회 테스트."""
    response = await client.get("/api/v1/users/me", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user["email"]
    assert data["username"] == test_user["username"]
    assert "password" not in data


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_update_current_user(client: AsyncClient, auth_headers: Dict[str, str], test_user: Dict[str, Any]):
    """현재 사용자 정보 업데이트 테스트."""
    update_data = {
        "username": "updateduser",
        "first_name": "Updated",
        "last_name": "User",
    }

    response = await client.put("/api/v1/users/me", headers=auth_headers, json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == update_data["username"]
    assert data["first_name"] == update_data["first_name"]
    assert data["last_name"] == update_data["last_name"]
    assert data["email"] == test_user["email"]  # 이메일은 변경되지 않음


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_get_user_by_id(client: AsyncClient, auth_headers: Dict[str, str], test_user: Dict[str, Any]):
    """특정 사용자 정보 조회 테스트."""
    user_id = test_user["id"]

    response = await client.get(f"/api/v1/users/{user_id}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id
    assert data["email"] == test_user["email"]
    assert data["username"] == test_user["username"]


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_get_nonexistent_user(client: AsyncClient, admin_auth_headers: Dict[str, str]):
    """존재하지 않는 사용자 조회 테스트. 관리자 컨텍스트에서 404 확인."""
    # 일반 사용자로 조회하면 본인이 아니므로 403 이 되어 존재 여부를 leak 하지 않음.
    # 관리자는 권한을 통과하므로 존재 확인 단계까지 진행되어 404 가 반환됨.
    non_existent_id = 9999

    response = await client.get(f"/api/v1/users/{non_existent_id}", headers=admin_auth_headers)

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_user_by_id_without_auth(client: AsyncClient, test_user: Dict[str, Any]):
    """인증 헤더 없이 호출 시 401."""
    response = await client.get(f"/api/v1/users/{test_user['id']}")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_other_user_as_regular_user(
        client: AsyncClient,
        auth_headers: Dict[str, str],
        admin_user: Dict[str, Any],
):
    """일반 사용자가 다른 사용자(admin_user) 를 조회하면 403."""
    response = await client.get(
        f"/api/v1/users/{admin_user['id']}",
        headers=auth_headers,
    )

    assert response.status_code == 403
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_self_or_admin_blocks_before_existence_check(
        client: AsyncClient,
        auth_headers: Dict[str, str],
):
    """일반 사용자가 존재하지 않는 ID 를 조회해도 403 (404 가 아님).

    권한 검사가 존재 확인보다 먼저 평가됨을 자동 회귀로 보장한다.
    이는 ID 열거 공격 차단의 핵심 가드 — PR #2 의 보안 매트릭스에서
    수동 확인으로 남겨두었던 항목.
    """
    response = await client.get(
        "/api/v1/users/9999",
        headers=auth_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_other_user_as_admin(
        client: AsyncClient,
        admin_auth_headers: Dict[str, str],
        test_user: Dict[str, Any],
):
    """관리자는 다른 사용자도 조회 가능."""
    response = await client.get(
        f"/api/v1/users/{test_user['id']}",
        headers=admin_auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user["id"]
    assert data["email"] == test_user["email"]


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_access_admin_endpoint_as_regular_user(client: AsyncClient, auth_headers: Dict[str, str]):
    """일반 사용자로 관리자 전용 엔드포인트 접근 시도 테스트."""
    # 일반 사용자가 모든 사용자 목록 조회 시도 (가정: 이 엔드포인트는 관리자 전용)
    response = await client.get("/api/v1/users/", headers=auth_headers)

    # 권한 부족으로 접근 거부되어야 함
    assert response.status_code == 403
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_access_admin_endpoint_as_admin(client: AsyncClient, admin_auth_headers: Dict[str, str]):
    """관리자로 관리자 전용 엔드포인트 접근 테스트."""
    # 관리자가 모든 사용자 목록 조회
    response = await client.get("/api/v1/users/", headers=admin_auth_headers)

    # 성공적으로 접근 가능해야 함
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0  # 최소한 관리자 자신의 계정이 있어야 함