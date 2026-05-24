"""`RequestIDMiddleware` + `AccessLogMiddleware` + loguru patcher 회귀 가드.

- 헤더 없는 요청 → 응답 X-Request-ID 가 uuid hex (32자) 자동 생성
- incoming X-Request-ID → 응답 동일
- 요청 처리 중 get_request_id() 가 헤더 값과 일치 (contextvar 동작)
- text/json 로그에 request_id 자동 첨부 (loguru patcher)
- incoming 헤더 hardening (length/charset 검증)
- access log 가 request_id + elapsed_ms 포함 + uvicorn.access 비활성화
"""

import json
import logging
import re
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from loguru import logger

from app.core.config import settings
from app.core.context import get_request_id
from app.core.exceptions import (
    AppException,
    AuthorizationException,
    NotFoundException,
    ValidationException,
)
from app.core.logging import setup_logging
from app.core.middleware import MAX_LENGTH, _validate_incoming_id
from app.main import app

HEX_32 = re.compile(r"^[0-9a-f]{32}$")


# ---------------------------------------------------------------------------
# 테스트 한정 라우트 — fixture 가 등록/제거
# ---------------------------------------------------------------------------


def _read_request_id() -> dict[str, str]:
    """현재 contextvar 값을 반환하는 테스트 핸들러."""
    return {"request_id": get_request_id()}


def _log_probe() -> dict[str, bool]:
    """요청 처리 중 loguru 로그를 1줄 남기는 테스트 핸들러."""
    logger.info("probe-from-request")
    return {"ok": True}


def _raise_handler() -> None:
    """access log 예외 케이스 회귀 가드용 핸들러."""
    raise RuntimeError("intentional-test-failure")


def _raise_not_found() -> None:
    """PR #41 회귀 — 도메인 예외 → handler 변환 후 access log status=404."""
    raise NotFoundException("test resource not found")


def _raise_validation() -> None:
    """PR #41 회귀 — 도메인 예외 → handler 변환 후 access log status=400."""
    raise ValidationException("test field invalid")


def _raise_forbidden() -> None:
    """PR #41 회귀 — 도메인 예외 → handler 변환 후 access log status=403."""
    raise AuthorizationException("test forbidden")


def _raise_http_401() -> None:
    """PR #42 회귀 — HTTPException(401) envelope + WWW-Authenticate 보존."""
    from fastapi import HTTPException

    raise HTTPException(
        status_code=401,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _raise_http_403() -> None:
    """PR #42 회귀 — HTTPException(403) envelope (headers 없는 케이스)."""
    from fastapi import HTTPException

    raise HTTPException(status_code=403, detail="Forbidden")


class _UnregisteredException(AppException):
    """PR #45 회귀 전용 — register_exception_handlers 에 명시 등록 안 됨."""

    def __init__(self, message: str = "unregistered") -> None:
        super().__init__(message=message, code="unregistered_test")


def _raise_unregistered() -> None:
    """PR #45 회귀 — AppException 서브 등록 누락 시 fallback handler 검증."""
    raise _UnregisteredException("test fallback")


@pytest.fixture(autouse=True, scope="module")
def _probe_routes() -> Iterator[None]:
    """테스트용 임시 라우트 2개를 등록 + 모듈 종료 시 제거.

    `app.router.routes` 에 직접 추가 — fastapi 의 `add_api_route` 는 OpenAPI 까지
    갱신하므로 테스트 한정 용도엔 과함. router 의 routes 리스트만 임시 조작.
    """
    test_router = APIRouter()
    test_router.add_api_route("/__test_request_id", _read_request_id, methods=["GET"])
    test_router.add_api_route("/__test_log_probe", _log_probe, methods=["GET"])
    test_router.add_api_route("/__test_raise", _raise_handler, methods=["GET"])
    test_router.add_api_route("/__test_raise_404", _raise_not_found, methods=["GET"])
    test_router.add_api_route("/__test_raise_400", _raise_validation, methods=["GET"])
    test_router.add_api_route("/__test_raise_403", _raise_forbidden, methods=["GET"])
    test_router.add_api_route("/__test_http_401", _raise_http_401, methods=["GET"])
    test_router.add_api_route("/__test_http_403", _raise_http_403, methods=["GET"])
    test_router.add_api_route(
        "/__test_unregistered", _raise_unregistered, methods=["GET"]
    )
    app.include_router(test_router)

    yield

    # teardown: 본 router 의 routes 만 제거 (다른 라우트 영향 없도록)
    _test_paths = (
        "/__test_request_id",
        "/__test_log_probe",
        "/__test_raise",
        "/__test_raise_404",
        "/__test_raise_400",
        "/__test_raise_403",
        "/__test_http_401",
        "/__test_http_403",
        "/__test_unregistered",
    )
    app.router.routes = [
        r for r in app.router.routes if getattr(r, "path", None) not in _test_paths
    ]


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """ASGI 트랜스포트 — 라이프스팬 우회 (단위 테스트 격리)."""
    app.dependency_overrides = {}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture(autouse=True)
def restore_logger() -> Iterator[None]:
    """각 테스트 후 logger sink 상태를 default 로 복원."""
    yield
    logger.remove()
    setup_logging()


# ---------------------------------------------------------------------------
# 미들웨어 동작
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_id_generated_when_header_missing(client: AsyncClient) -> None:
    """헤더 없이 요청 → 응답 X-Request-ID 가 uuid4 hex 형식 (32자)."""
    response = await client.get("/__test_request_id")

    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert HEX_32.match(request_id), f"uuid4 hex 32자 기대, 실제: {request_id!r}"


@pytest.mark.asyncio
async def test_request_id_propagates_from_incoming_header(client: AsyncClient) -> None:
    """incoming X-Request-ID 가 있으면 그대로 수용 → 응답 동일."""
    custom_id = "my-trace-12345"
    response = await client.get(
        "/__test_request_id", headers={"X-Request-ID": custom_id}
    )

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id


@pytest.mark.asyncio
async def test_request_id_accessible_via_contextvar(client: AsyncClient) -> None:
    """요청 처리 중 get_request_id() → 응답 헤더와 일치."""
    custom_id = "ctxvar-trace-678"
    response = await client.get(
        "/__test_request_id", headers={"X-Request-ID": custom_id}
    )

    assert response.status_code == 200
    body = response.json()["data"]  # SuccessEnvelope wrap (PR #49)
    assert body["request_id"] == custom_id
    assert body["request_id"] == response.headers.get("X-Request-ID")


@pytest.mark.asyncio
async def test_request_id_resets_between_requests(client: AsyncClient) -> None:
    """연속 요청 2건의 ID 가 서로 다름 — contextvar leakage 방지."""
    r1 = await client.get("/__test_request_id")
    r2 = await client.get("/__test_request_id")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert (
        r1.json()["data"]["request_id"] != r2.json()["data"]["request_id"]
    )  # PR #49 envelope


# ---------------------------------------------------------------------------
# loguru 자동 첨부
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_id_in_text_log(
    client: AsyncClient, capfd: pytest.CaptureFixture[str]
) -> None:
    """요청 처리 중 logger.info() → text 로그에 request_id 포함."""
    setup_logging()
    custom_id = "log-text-trace-99"
    response = await client.get(
        "/__test_log_probe", headers={"X-Request-ID": custom_id}
    )

    assert response.status_code == 200
    captured = capfd.readouterr()
    assert "probe-from-request" in captured.err
    assert custom_id in captured.err, (
        f"text 로그에 request_id 미포함. 실제 stderr:\n{captured.err}"
    )


@pytest.mark.asyncio
async def test_request_id_in_json_log(
    client: AsyncClient,
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LOG_FORMAT=json 시 record.extra.request_id 가 JSON 출력에 포함."""
    monkeypatch.setattr(settings, "LOG_FORMAT", "json")
    setup_logging()
    custom_id = "log-json-trace-42"
    response = await client.get(
        "/__test_log_probe", headers={"X-Request-ID": custom_id}
    )

    assert response.status_code == 200
    captured = capfd.readouterr()

    # probe-from-request 라인만 추출 (uvicorn / intercept 노이즈 배제)
    probe_lines = [
        line
        for line in captured.err.strip().splitlines()
        if "probe-from-request" in line
    ]
    assert probe_lines, "probe-from-request JSON 라인을 찾지 못함"

    data = json.loads(probe_lines[-1])
    assert data["record"]["message"] == "probe-from-request"
    assert data["record"]["extra"]["request_id"] == custom_id


# ---------------------------------------------------------------------------
# incoming 헤더 hardening (PR #33)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_id_accepts_max_length(client: AsyncClient) -> None:
    """정확히 128자 길이의 URL-safe 헤더는 통과 (boundary)."""
    custom_id = "a" * MAX_LENGTH
    response = await client.get(
        "/__test_request_id", headers={"X-Request-ID": custom_id}
    )

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id


@pytest.mark.asyncio
async def test_request_id_rejects_oversized_header(client: AsyncClient) -> None:
    """129자 (max + 1) 헤더 → 새 uuid hex (silent fallback)."""
    oversized = "a" * (MAX_LENGTH + 1)
    response = await client.get(
        "/__test_request_id", headers={"X-Request-ID": oversized}
    )

    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert HEX_32.match(request_id), (
        f"oversized 헤더 거부 후 새 uuid 기대, 실제: {request_id!r}"
    )
    assert request_id != oversized


@pytest.mark.asyncio
async def test_request_id_rejects_invalid_charset(client: AsyncClient) -> None:
    """charset 위반 (공백 포함) → 새 uuid hex (silent fallback)."""
    bad_id = "bad id with space"
    response = await client.get("/__test_request_id", headers={"X-Request-ID": bad_id})

    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert HEX_32.match(request_id)
    assert request_id != bad_id


def test_validate_helper_rejects_control_unicode_and_special() -> None:
    """헬퍼 단위: 제어 문자 / 비ASCII / 콜론 / 빈 값 모두 None.

    httpx 클라이언트가 raw 제어 문자/비ASCII 헤더를 거부할 수 있어 미들웨어
    통과 테스트로 직접 검증 불가 — 헬퍼 단위로 격리 검증.
    """
    # 거부 케이스
    assert _validate_incoming_id(None) is None
    assert _validate_incoming_id("") is None
    assert _validate_incoming_id("value\nwith\nnewline") is None
    assert _validate_incoming_id("value\twith\ttab") is None
    assert _validate_incoming_id("trace-ü") is None  # 비ASCII
    assert _validate_incoming_id("Root=1-58:abc") is None  # AWS X-Ray 형식
    assert _validate_incoming_id("a" * (MAX_LENGTH + 1)) is None
    # 통과 케이스
    assert _validate_incoming_id("uuid-32-hex") == "uuid-32-hex"
    assert _validate_incoming_id("a" * MAX_LENGTH) == "a" * MAX_LENGTH
    assert _validate_incoming_id("Abc_123-XYZ") == "Abc_123-XYZ"


@pytest.mark.asyncio
async def test_request_id_warns_on_rejection(
    client: AsyncClient, capfd: pytest.CaptureFixture[str]
) -> None:
    """검증 실패 시 warn 로그에 사유 + 원본 prefix + 새 ID 포함."""
    setup_logging()
    bad_id = "bad id with space"
    response = await client.get("/__test_request_id", headers={"X-Request-ID": bad_id})

    assert response.status_code == 200
    captured = capfd.readouterr()
    assert "X-Request-ID rejected" in captured.err, (
        f"warn 로그 누락. 실제 stderr:\n{captured.err}"
    )
    assert bad_id in captured.err  # 원본 prefix (50자 이내)


# ---------------------------------------------------------------------------
# AccessLogMiddleware (PR #34)
# ---------------------------------------------------------------------------


ACCESS_LOG_PATTERN = re.compile(r'"GET /__test_request_id HTTP/\S+" 200 \d+\.\d+ms')


@pytest.mark.asyncio
async def test_access_log_contains_request_id(
    client: AsyncClient, capfd: pytest.CaptureFixture[str]
) -> None:
    """정상 요청 → access log 라인에 응답 헤더와 동일 request_id 포함."""
    setup_logging()
    custom_id = "access-log-trace-aaa"
    response = await client.get(
        "/__test_request_id", headers={"X-Request-ID": custom_id}
    )

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id

    captured = capfd.readouterr()
    access_lines = [
        line for line in captured.err.splitlines() if ACCESS_LOG_PATTERN.search(line)
    ]
    assert access_lines, f"access log 라인 미발견. 실제 stderr:\n{captured.err}"
    # text format 의 request_id 컬럼 ({extra[request_id]}) 에 custom_id 노출
    assert custom_id in access_lines[-1], (
        f"access log 의 request_id 누락. 실제 라인:\n{access_lines[-1]}"
    )


@pytest.mark.asyncio
async def test_access_log_format(
    client: AsyncClient, capfd: pytest.CaptureFixture[str]
) -> None:
    """access log 형식 매칭 (uvicorn 호환 + elapsed_ms 양수)."""
    setup_logging()
    await client.get("/__test_request_id")

    captured = capfd.readouterr()
    access_lines = [
        line for line in captured.err.splitlines() if ACCESS_LOG_PATTERN.search(line)
    ]
    assert access_lines, f"access log format 매칭 실패. 실제 stderr:\n{captured.err}"
    # elapsed_ms 가 양수 float 인지 확인
    match = re.search(r"(\d+\.\d+)ms", access_lines[-1])
    assert match is not None
    assert float(match.group(1)) >= 0.0


def test_uvicorn_access_logger_disabled() -> None:
    """setup_logging() 후 uvicorn.access 비활성화 (handlers=[] + propagate=False)."""
    setup_logging()
    access_logger = logging.getLogger("uvicorn.access")
    assert access_logger.handlers == [], (
        f"uvicorn.access 의 handlers 비어있어야 함. 실제: {access_logger.handlers!r}"
    )
    assert access_logger.propagate is False


# ---------------------------------------------------------------------------
# AccessLogMiddleware exception handling (PR #36)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_access_log_emitted_on_route_exception(
    client: AsyncClient, capfd: pytest.CaptureFixture[str]
) -> None:
    """라우트 핸들러가 raise 해도 access log 한 줄 출력 + status=500.

    httpx ASGITransport + starlette BaseHTTPMiddleware 조합에서 라우트 예외는
    ExceptionGroup 으로 외부 전파될 수 있음 (실제 uvicorn server 환경에서는
    ServerErrorMiddleware 가 500 응답으로 변환). 본 PR 의 핵심은 dispatch 의
    finally 가 호출되어 access log 가 누락되지 않는지 — 응답 status 가 아닌
    finally 동작 회귀 가드.
    """
    setup_logging()

    # ExceptionGroup: starlette BaseHTTPMiddleware anyio task group 경유 변종.
    # RuntimeError: 환경에 따라 ASGITransport 가 raw 예외 전파하는 경우.
    with pytest.raises((RuntimeError, ExceptionGroup)):
        await client.get("/__test_raise")

    captured = capfd.readouterr()
    matches = re.findall(r'"GET /__test_raise HTTP/\S+" 500 \d+\.\d+ms', captured.err)
    assert matches, (
        f"예외 발생 시 access log (status=500) 누락. 실제 stderr:\n{captured.err}"
    )


# ---------------------------------------------------------------------------
# Exception handler 통합 (PR #41) — access log status 정확성 회귀 가드
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_access_log_status_404_via_handler(
    client: AsyncClient, capfd: pytest.CaptureFixture[str]
) -> None:
    """NotFoundException → handler 변환 → access log status=404 + envelope."""
    setup_logging()
    response = await client.get("/__test_raise_404")
    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "message": "test resource not found",
            "code": "not_found",
        }
    }

    captured = capfd.readouterr()
    assert re.search(
        r'"GET /__test_raise_404 HTTP/\S+" 404 \d+\.\d+ms', captured.err
    ), f"access log status=404 누락. 실제 stderr:\n{captured.err}"


@pytest.mark.asyncio
async def test_access_log_status_400_via_handler(
    client: AsyncClient, capfd: pytest.CaptureFixture[str]
) -> None:
    """ValidationException → handler 변환 → access log status=400 + envelope."""
    setup_logging()
    response = await client.get("/__test_raise_400")
    assert response.status_code == 400
    assert response.json() == {
        "detail": {
            "message": "test field invalid",
            "code": "validation_error",
        }
    }

    captured = capfd.readouterr()
    assert re.search(
        r'"GET /__test_raise_400 HTTP/\S+" 400 \d+\.\d+ms', captured.err
    ), f"access log status=400 누락. 실제 stderr:\n{captured.err}"


@pytest.mark.asyncio
async def test_access_log_status_403_via_handler(
    client: AsyncClient, capfd: pytest.CaptureFixture[str]
) -> None:
    """AuthorizationException → handler 변환 → access log status=403 + envelope."""
    setup_logging()
    response = await client.get("/__test_raise_403")
    assert response.status_code == 403
    assert response.json() == {
        "detail": {
            "message": "test forbidden",
            "code": "authorization_error",
        }
    }

    captured = capfd.readouterr()
    assert re.search(
        r'"GET /__test_raise_403 HTTP/\S+" 403 \d+\.\d+ms', captured.err
    ), f"access log status=403 누락. 실제 stderr:\n{captured.err}"


# ---------------------------------------------------------------------------
# 응답 envelope 표준화 (PR #42) — HTTPException 일관 적용 + 422 default 유지
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_exception_401_envelope_with_headers(
    client: AsyncClient,
) -> None:
    """HTTPException(401) → envelope + WWW-Authenticate 헤더 보존 (OAuth2)."""
    response = await client.get("/__test_http_401")
    assert response.status_code == 401
    assert response.json() == {
        "detail": {
            "message": "Authentication required",
            "code": "http_401",
        }
    }
    # OAuth2 호환 헤더 보존 회귀 가드
    assert response.headers.get("WWW-Authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_http_exception_403_envelope(client: AsyncClient) -> None:
    """HTTPException(403) → envelope (headers 없는 케이스)."""
    response = await client.get("/__test_http_403")
    assert response.status_code == 403
    assert response.json() == {
        "detail": {
            "message": "Forbidden",
            "code": "http_403",
        }
    }


@pytest.mark.asyncio
async def test_request_validation_error_envelope(
    client: AsyncClient,
) -> None:
    """422 RequestValidationError → envelope + field별 errors + PII 차단 (PR #48).

    회귀 가드:
    - detail 이 list (FastAPI default) 가 아닌 envelope object
    - code='request_validation_error', message='Validation error'
    - errors 항목별 loc/msg/type 보존
    - raw `input` (사용자 body) 차단 (PII 누설 방지)
    """
    response = await client.post("/api/v1/users/", json={"username": "x"})
    assert response.status_code == 422
    body = response.json()

    # envelope object (이전 PR #42 까지는 list 였음)
    assert isinstance(body["detail"], dict)
    assert body["detail"]["message"] == "Validation error"
    assert body["detail"]["code"] == "request_validation_error"

    # field별 errors 보존
    errors = body["detail"]["errors"]
    assert isinstance(errors, list)
    assert len(errors) > 0
    for err in errors:
        assert "loc" in err
        assert "msg" in err
        assert "type" in err
        # PII 차단: raw input 키 응답 노출 X
        assert "input" not in err


# ---------------------------------------------------------------------------
# AppException 슈퍼 fallback (PR #45) — 등록 누락된 서브클래스 안전망
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_exception_fallback_handler_returns_envelope_500(
    client: AsyncClient, capfd: pytest.CaptureFixture[str]
) -> None:
    """등록 누락된 AppException 서브 → 500 envelope + logger.exception.

    회귀 가드: register_exception_handlers 에서 AppException 슈퍼 등록 제거 시
    이 테스트가 깨짐 (ServerErrorMiddleware 의 plain text 500 으로 회귀).
    """
    setup_logging()
    response = await client.get("/__test_unregistered")
    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "message": "test fallback",
            "code": "unregistered_test",
        }
    }
    # 운영 가시성: 등록 누락 시그널 로그
    captured = capfd.readouterr()
    assert "AppException 등록 누락" in captured.err, (
        f"등록 누락 시그널 로그 누락. 실제 stderr:\n{captured.err}"
    )
    assert "_UnregisteredException" in captured.err


# ---------------------------------------------------------------------------
# Success envelope (PR #49) — 2xx JSON 응답 wrap 회귀 가드
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_response_is_wrapped_in_data_envelope(
    client: AsyncClient,
) -> None:
    """200 JSON 응답 → `{"data": <payload>}` envelope wrap."""
    response = await client.get("/__test_request_id")
    assert response.status_code == 200
    body = response.json()
    # envelope 외층
    assert set(body.keys()) == {"data"}
    # payload 보존
    assert "request_id" in body["data"]


@pytest.mark.asyncio
async def test_204_no_content_is_not_wrapped(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    test_product: dict,
) -> None:
    """204 No Content → envelope 비적용 (body 없음).

    DELETE /products/{id} 가 204 반환. wrap 시도 시 body 추가는 spec 위반.
    """
    product_id = test_product["id"]
    response = await client.delete(
        f"/api/v1/products/{product_id}", headers=admin_auth_headers
    )
    assert response.status_code == 204
    assert response.content == b""  # body 없음 보존


@pytest.mark.asyncio
async def test_oauth2_token_endpoint_is_not_wrapped(
    client: AsyncClient,
    test_user: dict,
) -> None:
    """OAuth2 /users/token → RFC 6749 표준 응답 (envelope 비적용)."""
    response = await client.post(
        "/api/v1/users/token",
        data={"username": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200
    body = response.json()
    # RFC 6749: access_token / token_type 직접 노출
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    # envelope 외층 없음
    assert "data" not in body


@pytest.mark.asyncio
async def test_error_response_not_re_wrapped(
    client: AsyncClient,
) -> None:
    """4xx 응답은 handler 의 envelope 그대로 (SuccessEnvelope 비적용)."""
    response = await client.get("/__test_raise_404")
    assert response.status_code == 404
    body = response.json()
    # error envelope: detail object
    assert "detail" in body
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "not_found"
    # SuccessEnvelope 의 data 외층 없음
    assert "data" not in body


@pytest.mark.asyncio
async def test_list_response_is_wrapped(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """200 list 응답도 동일 envelope (list 가 data 값으로 들어감)."""
    response = await client.get("/api/v1/users/", headers=admin_auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"data"}
    assert isinstance(body["data"], list)
