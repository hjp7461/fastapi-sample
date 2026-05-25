"""
사용자 API 엔드포인트 테스트.
pytest==8.3.5, pytest-asyncio==0.26.0 버전에 맞게 작성되었습니다.
"""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# pytest-asyncio 8.3.5에서는 이제 Test 클래스 대신 함수에 직접 마커를 적용
# pytestmark = pytest.mark.asyncio  # 불필요


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_create_user(client: AsyncClient) -> None:
    """사용자 생성 테스트."""
    user_data = {
        "email": "newuser@example.com",
        "username": "newuser",
        "password": "newpassword123",
        "password_confirm": "newpassword123",
    }

    response = await client.post("/api/v1/users/", json=user_data)

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["email"] == user_data["email"]
    assert data["username"] == user_data["username"]
    assert "id" in data
    assert "password" not in data


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_login(client: AsyncClient, test_user: dict[str, Any]) -> None:
    """사용자 로그인 테스트."""
    login_data = {
        "username": test_user["email"],  # 이메일을 사용자명으로 사용
        "password": test_user["password"],
    }

    response = await client.post("/api/v1/users/token", data=login_data)

    assert response.status_code == 200
    # OAuth2 token (/users/token) 은 RFC 6749 표준 응답 유지 (envelope 비적용)
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_upgrades_old_bcrypt_hash(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
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
    old_hash = _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt(rounds=4)).decode(
        "utf-8"
    )

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


@pytest.mark.asyncio
async def test_login_logs_warning_on_downgrade(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """저장된 해시 라운드가 현재 settings 보다 높으면 다운그레이드 차단 + warning 로깅.

    운영자가 BCRYPT_ROUNDS 를 낮춰도 강한 해시는 그대로 유지되어야 하고,
    스킵 사실은 logger.warning 으로 가시화되어야 한다.
    """
    import bcrypt as _bcrypt

    from app.core.config import settings
    from app.user.models import UserModel

    warnings: list = []
    monkeypatch.setattr(
        "app.user.service.logger.warning",
        lambda *args, **kwargs: warnings.append((args, kwargs)),
    )

    plain = "passwd1234"
    high_rounds = settings.BCRYPT_ROUNDS + 2
    high_hash = _bcrypt.hashpw(
        plain.encode("utf-8"), _bcrypt.gensalt(rounds=high_rounds)
    ).decode("utf-8")

    user = UserModel(
        email="strong@example.com",
        username="strong",
        hashed_password=high_hash,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    response = await client.post(
        "/api/v1/users/token",
        data={"username": "strong@example.com", "password": plain},
    )
    assert response.status_code == 200

    # 해시는 그대로 유지되어야 함 (다운그레이드 차단)
    await db_session.refresh(user)
    assert user.hashed_password == high_hash

    # logger.warning 이 호출되었고 메시지 템플릿 + args 에 라운드 정보 포함
    assert warnings, "logger.warning was not called"
    call_args, _ = warnings[0]
    msg_template, *positional = call_args
    assert "downgrade detected" in msg_template
    assert high_rounds in positional
    assert settings.BCRYPT_ROUNDS in positional


@pytest.mark.asyncio
async def test_login_logs_exception_on_rehash_failure(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """재해시 중 repository.update 가 실패해도 인증은 성공하고 logger.exception 으로
    기록되는지 검증한다.

    PR #11 의 except 블록에 로깅을 더해, 운영자가 재해시 실패를 가시적으로
    모니터링할 수 있도록 한다.
    """
    import bcrypt as _bcrypt

    from app.user.models import UserModel

    exceptions: list = []
    monkeypatch.setattr(
        "app.user.service.logger.exception",
        lambda *args, **kwargs: exceptions.append((args, kwargs)),
    )

    plain = "passwd1234"
    # 의도적으로 낮은 라운드 (업그레이드 대상)
    old_hash = _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt(rounds=4)).decode(
        "utf-8"
    )

    user = UserModel(
        email="failupgrade@example.com",
        username="failupgrade",
        hashed_password=old_hash,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # repository.update 가 예외를 던지도록 패치 — 재해시 흐름의 update 만 잡힘.
    async def _raise(*_a: object, **_kw: object) -> None:
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr("app.user.repository.UserRepository.update", _raise)

    response = await client.post(
        "/api/v1/users/token",
        data={"username": "failupgrade@example.com", "password": plain},
    )
    # 재해시 실패해도 인증은 성공
    assert response.status_code == 200

    # 기존 해시 보존 (실패한 업데이트가 commit 되지 않음)
    await db_session.refresh(user)
    assert user.hashed_password == old_hash

    # logger.exception 호출 + 메시지 템플릿에 "rehash failed" 포함
    assert exceptions, "logger.exception was not called"
    call_args, _ = exceptions[0]
    msg_template = call_args[0]
    assert "rehash failed" in msg_template


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_get_current_user(
    client: AsyncClient, auth_headers: dict[str, str], test_user: dict[str, Any]
) -> None:
    """현재 사용자 정보 조회 테스트."""
    response = await client.get("/api/v1/users/me", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == test_user["email"]
    assert data["username"] == test_user["username"]
    assert "password" not in data


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_update_current_user(
    client: AsyncClient, auth_headers: dict[str, str], test_user: dict[str, Any]
) -> None:
    """현재 사용자 정보 업데이트 테스트."""
    update_data = {
        "username": "updateduser",
        "first_name": "Updated",
        "last_name": "User",
    }

    response = await client.put(
        "/api/v1/users/me", headers=auth_headers, json=update_data
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["username"] == update_data["username"]
    assert data["first_name"] == update_data["first_name"]
    assert data["last_name"] == update_data["last_name"]
    assert data["email"] == test_user["email"]  # 이메일은 변경되지 않음


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_get_user_by_id(
    client: AsyncClient, auth_headers: dict[str, str], test_user: dict[str, Any]
) -> None:
    """특정 사용자 정보 조회 테스트."""
    user_id = test_user["id"]

    response = await client.get(f"/api/v1/users/{user_id}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == user_id
    assert data["email"] == test_user["email"]
    assert data["username"] == test_user["username"]


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_get_nonexistent_user(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    """존재하지 않는 사용자 조회 테스트. 관리자 컨텍스트에서 404 확인."""
    # 일반 사용자로 조회하면 본인이 아니므로 403 이 되어 존재 여부를 leak 하지 않음.
    # 관리자는 권한을 통과하므로 존재 확인 단계까지 진행되어 404 가 반환됨.
    non_existent_id = 9999

    response = await client.get(
        f"/api/v1/users/{non_existent_id}", headers=admin_auth_headers
    )

    assert response.status_code == 404
    data = response.json()  # error envelope (handler 가 처리, SuccessEnvelope 비적용)
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_user_by_id_without_auth(
    client: AsyncClient, test_user: dict[str, Any]
) -> None:
    """인증 헤더 없이 호출 시 401."""
    response = await client.get(f"/api/v1/users/{test_user['id']}")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_other_user_as_regular_user(
    client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user: dict[str, Any],
) -> None:
    """일반 사용자가 다른 사용자(admin_user) 를 조회하면 403."""
    response = await client.get(
        f"/api/v1/users/{admin_user['id']}",
        headers=auth_headers,
    )

    assert response.status_code == 403
    data = response.json()  # error envelope (handler 가 처리, SuccessEnvelope 비적용)
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_self_or_admin_blocks_before_existence_check(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
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
    admin_auth_headers: dict[str, str],
    test_user: dict[str, Any],
) -> None:
    """관리자는 다른 사용자도 조회 가능 (UserAdminView 응답).

    응답의 email 은 마스킹되어 있고 first_name/last_name 은 제외된다.
    상세 매트릭스는 `test_get_other_user_as_admin_returns_masked_view` 에서.
    """
    response = await client.get(
        f"/api/v1/users/{test_user['id']}",
        headers=admin_auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == test_user["id"]


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_access_admin_endpoint_as_regular_user(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """일반 사용자로 관리자 전용 엔드포인트 접근 시도 테스트."""
    # 일반 사용자가 모든 사용자 목록 조회 시도 (가정: 이 엔드포인트는 관리자 전용)
    response = await client.get("/api/v1/users/", headers=auth_headers)

    # 권한 부족으로 접근 거부되어야 함
    assert response.status_code == 403
    data = response.json()  # error envelope (handler 가 처리, SuccessEnvelope 비적용)
    assert "detail" in data


@pytest.mark.asyncio  # 명시적으로 asyncio 마커 추가
async def test_access_admin_endpoint_as_admin(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    """관리자로 관리자 전용 엔드포인트 접근 테스트."""
    # 관리자가 모든 사용자 목록 조회
    response = await client.get("/api/v1/users/", headers=admin_auth_headers)

    # 성공적으로 접근 가능해야 함
    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)
    assert len(data) > 0  # 최소한 관리자 자신의 계정이 있어야 함


@pytest.mark.asyncio
async def test_access_admin_endpoint_as_staff_forbidden(
    client: AsyncClient, staff_auth_headers: dict[str, str]
) -> None:
    """staff 가 GET /users/ 접근 시 거부 (403).

    staff 권한 정책 회귀 가드 — staff 는 product 변경은 가능하지만
    사용자 관리 (목록 조회 포함) 는 admin 전용으로 유지된다.
    """
    response = await client.get("/api/v1/users/", headers=staff_auth_headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_other_user_as_staff_is_forbidden(
    client: AsyncClient,
    staff_auth_headers: dict[str, str],
    admin_user: dict[str, Any],
) -> None:
    """staff 가 다른 사용자 (admin_user) 조회 시 거부 (403).

    `require_self_or_admin` 회귀 가드 — staff 는 본인 외 조회에 admin 권한이
    없으므로 통과 불가. 사용자 PII 노출 면적이 admin only 로 유지됨을 보장.
    """
    response = await client.get(
        f"/api/v1/users/{admin_user['id']}", headers=staff_auth_headers
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_self_returns_full_user_response(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_user: dict[str, Any],
) -> None:
    """본인 조회 시 first_name/last_name 까지 포함된 UserResponse 반환."""
    response = await client.get(
        f"/api/v1/users/{test_user['id']}", headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == test_user["email"]  # 본인은 평문
    assert "first_name" in data
    assert "last_name" in data
    assert "role" in data
    assert "is_active" in data


@pytest.mark.asyncio
async def test_get_other_user_as_admin_returns_masked_view(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    test_user: dict[str, Any],
) -> None:
    """관리자가 타인 조회 시 UserAdminView — email 마스킹 + 이름 제외."""
    response = await client.get(
        f"/api/v1/users/{test_user['id']}", headers=admin_auth_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]

    assert data["id"] == test_user["id"]
    # email 마스킹 (평문과 다름 + *** 포함)
    assert "***" in data["email"]
    assert data["email"] != test_user["email"]
    # 이름 필드는 응답에서 제외
    assert "first_name" not in data
    assert "last_name" not in data
    # 비-PII 필드는 그대로
    assert data["username"] == test_user["username"]
    assert "role" in data
    assert "is_active" in data


@pytest.mark.asyncio
async def test_admin_view_email_raw_when_masking_disabled(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    test_user: dict[str, Any],
) -> None:
    """USER_ADMIN_EMAIL_MASKING=false 토글 시 관리자→타인 응답 email 이 raw.

    기본 (마스킹 ON) 케이스는 `test_get_other_user_as_admin_returns_masked_view`
    가 커버. 본 케이스는 토글 해제만 검증.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "USER_ADMIN_EMAIL_MASKING", False)

    response = await client.get(
        f"/api/v1/users/{test_user['id']}", headers=admin_auth_headers
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == test_user["email"]
    assert "***" not in data["email"]


@pytest.mark.asyncio
async def test_list_users_returns_summary_without_pii(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """관리자 목록 조회는 UserSummary 응답 — PII 필드 0건."""
    response = await client.get("/api/v1/users/", headers=admin_auth_headers)

    assert response.status_code == 200
    items = response.json()["data"]
    assert isinstance(items, list)
    assert len(items) > 0

    for item in items:
        # PII 필드 0건
        assert "email" not in item
        assert "first_name" not in item
        assert "last_name" not in item
        # 요약 필드는 있음
        assert "id" in item
        assert "username" in item
        assert "role" in item
        assert "is_active" in item
        assert "created_at" in item


# ---------------------------------------------------------------------------
# login 의 AuthenticationException 전환 (PR #46) — envelope + WWW-Authenticate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_with_invalid_credentials_returns_envelope_401(
    client: AsyncClient, test_user: dict[str, Any]
) -> None:
    """잘못된 비번 → AuthenticationException → 401 envelope + WWW-Authenticate.

    PR #46 회귀 가드: login 의 HTTPException(401) → AuthenticationException 전환.
    code='authentication_error' (도메인 예외 분류) + RFC 7235 WWW-Authenticate Bearer.
    """
    response = await client.post(
        "/api/v1/users/token",
        data={"username": test_user["email"], "password": "wrong_password"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": {
            "message": "Incorrect email or password",
            "code": "authentication_error",
        }
    }
    # RFC 7235 MUST: 401 응답에 WWW-Authenticate 헤더 필수 (OAuth2 호환)
    assert response.headers.get("WWW-Authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_login_with_unknown_email_returns_envelope_401(
    client: AsyncClient,
) -> None:
    """존재하지 않는 이메일 → 동일 401 envelope (정보 누설 방지)."""
    response = await client.post(
        "/api/v1/users/token",
        data={"username": "nobody@example.com", "password": "anything"},
    )

    assert response.status_code == 401
    body = response.json()  # error envelope (SuccessEnvelope 비적용)
    assert body["detail"]["code"] == "authentication_error"
    # 동일 메시지로 정보 누설 방지 (이메일 존재 여부 leak 차단)
    assert body["detail"]["message"] == "Incorrect email or password"
    assert response.headers.get("WWW-Authenticate") == "Bearer"


# ---------------------------------------------------------------------------
# require_* / credentials 의 도메인 예외 전환 (PR #47) — envelope code 회귀
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_token_returns_envelope_authentication_error(
    client: AsyncClient,
) -> None:
    """잘못된 토큰 → get_current_user 가 AuthenticationException → envelope.

    PR #47 회귀 가드: credentials_exception 의 HTTPException → AuthenticationException
    전환. code='authentication_error' (이전: 'http_401') + WWW-Authenticate Bearer 자동.
    """
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer not.a.valid.jwt"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": {
            "message": "Could not validate credentials",
            "code": "authentication_error",
        }
    }
    # PR #46 handler 가 자동 첨부
    assert response.headers.get("WWW-Authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_require_admin_denied_returns_envelope_authorization_error(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """일반 사용자 → require_admin 거부 → AuthorizationException envelope.

    PR #47 회귀 가드: require_* 의 HTTPException → AuthorizationException 전환.
    code='authorization_error' (이전: 'http_403').
    """
    response = await client.get("/api/v1/users/", headers=auth_headers)

    assert response.status_code == 403
    assert response.json() == {
        "detail": {
            "message": "Not enough permissions",
            "code": "authorization_error",
        }
    }


@pytest.mark.asyncio
async def test_inactive_user_returns_401_envelope(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_user: dict[str, Any],
    db_session: AsyncSession,
) -> None:
    """inactive user 의 보호 엔드포인트 요청 → 401 envelope + WWW-Authenticate.

    PR #50 회귀 가드: HTTPException(400) → AuthenticationException(401) 전환.
    토큰은 활성 시점 발급, 이후 is_active=False 로 deactivate (운영 시나리오:
    토큰 만료 전에 운영자가 계정을 비활성화한 경우).
    """
    from app.user.models import UserModel

    # Arrange: 활성 시점에 발급된 토큰을 가진 사용자를 deactivate
    db_user = await db_session.get(UserModel, test_user["id"])
    assert db_user is not None
    db_user.is_active = False
    await db_session.commit()

    # Act: 보호 엔드포인트 요청
    response = await client.get("/api/v1/users/me", headers=auth_headers)

    # Assert: 401 + envelope + WWW-Authenticate Bearer
    assert response.status_code == 401
    assert response.json() == {
        "detail": {
            "message": "Inactive user account",
            "code": "authentication_error",
        }
    }
    assert response.headers.get("WWW-Authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_inactive_user_message_differs_from_credentials_fail(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_user: dict[str, Any],
    db_session: AsyncSession,
) -> None:
    """inactive vs 토큰 무효 — 같은 code 내에서 message 분기 가능 회귀 가드.

    PR #50: 클라이언트가 재활성화 안내 vs 재로그인 안내를 분기할 수 있도록
    message 차별화 (code 는 동일하게 'authentication_error').
    """
    from app.user.models import UserModel

    # Case 1: inactive user
    db_user = await db_session.get(UserModel, test_user["id"])
    assert db_user is not None
    db_user.is_active = False
    await db_session.commit()

    response_inactive = await client.get("/api/v1/users/me", headers=auth_headers)
    assert response_inactive.status_code == 401
    inactive_body = response_inactive.json()["detail"]

    # Case 2: 잘못된 토큰
    response_invalid = await client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer invalid_token"}
    )
    assert response_invalid.status_code == 401
    invalid_body = response_invalid.json()["detail"]

    # Assert: 같은 code, 다른 message
    assert inactive_body["code"] == "authentication_error"
    assert invalid_body["code"] == "authentication_error"
    assert inactive_body["message"] == "Inactive user account"
    assert invalid_body["message"] == "Could not validate credentials"
    assert inactive_body["message"] != invalid_body["message"]


@pytest.mark.asyncio
async def test_list_users_paginated_envelope(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """PR #52: GET /users/ 응답이 `{data, meta: {total, skip, limit}}` 형식.

    middleware idempotent 룰 (dict + data 키 → wrap skip) 회귀 가드 겸용:
    응답의 `data` 가 list (UserSummary 배열) 이고 `meta` 는 동일 수준.
    이중 wrap 이면 `data["data"]` 형태가 됨 → 즉시 fail.
    """
    response = await client.get(
        "/api/v1/users/?skip=0&limit=20", headers=admin_auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "meta" in body
    assert isinstance(body["data"], list)
    assert body["meta"]["skip"] == 0
    assert body["meta"]["limit"] == 20
    assert body["meta"]["total"] >= 1  # admin 본인 최소 1


@pytest.mark.parametrize(
    "params,expected_status",
    [
        ({"skip": -1}, 422),
        ({"limit": 0}, 422),
        ({"limit": 1001}, 422),
        ({"skip": 0, "limit": 1000}, 200),  # 경계값 OK
    ],
)
@pytest.mark.asyncio
async def test_list_users_query_constraints(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    params: dict[str, int],
    expected_status: int,
) -> None:
    """PR #52: skip≥0, 1≤limit≤1000 Query 제약 회귀 가드 (DoS / 무효 입력)."""
    response = await client.get(
        "/api/v1/users/", headers=admin_auth_headers, params=params
    )
    assert response.status_code == expected_status
    if expected_status == 422:
        assert response.json()["detail"]["code"] == "request_validation_error"


@pytest.mark.asyncio
async def test_list_users_meta_total_matches_actual_count(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    test_user: dict[str, Any],
) -> None:
    """PR #52: meta.total 이 실제 DB 행 수와 일치 — 빈 결과나 다중 사용자 모두."""
    response = await client.get(
        "/api/v1/users/?skip=0&limit=1000", headers=admin_auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    # total 이 정수이고, data 길이와 일치 (limit=1000 이므로 모든 행 포함)
    assert isinstance(body["meta"]["total"], int)
    assert body["meta"]["total"] == len(body["data"])
    assert body["meta"]["total"] >= 2  # admin + test_user
