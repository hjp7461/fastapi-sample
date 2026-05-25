"""error code matrix drift CI 가드 (PR #53).

`register_exception_handlers` (app/core/exceptions.py) 의 코드-코드 일관성을
CI 시점에 정적으로 검증한다. 새 `AppException` 서브클래스 추가 시 등록 누락 /
default code 오타 / envelope 구조 변경을 PR 머지 전 차단.

비목적:
- RUNBOOK §10 ↔ 코드 자동 동기화 (docs/ untrack 정책 유지, §9.5 7번 manual)
- pre-commit 별도 hook (pytest 가 이미 양쪽에서 실행됨)
- 단일 진실원 모듈 신설 (`app/core/error_codes.py` registry) — 표면 회피
"""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    AppException,
    AuthenticationException,
    AuthorizationException,
    BusinessLogicException,
    NotFoundException,
    ValidationException,
    register_exception_handlers,
)

# ---------------------------------------------------------------------------
# 헬퍼 + reference 매트릭스
# ---------------------------------------------------------------------------


def _registered_handlers() -> dict[type[Exception], Callable[..., Any]]:
    """register_exception_handlers 적용 후 app.exception_handlers 추출."""
    app = FastAPI()
    register_exception_handlers(app)
    return dict(app.exception_handlers)


# (exception class, (status, code, default_message)) — handler 의 등록 상태와
# 인스턴스의 default 값 양쪽을 검증하는 단일 진실원 reference.
DOMAIN_EXCEPTION_MATRIX: dict[type[AppException], tuple[int, str, str]] = {
    NotFoundException: (404, "not_found", "Resource not found"),
    ValidationException: (400, "validation_error", "Validation error"),
    BusinessLogicException: (400, "business_logic_error", "Business logic error"),
    AuthenticationException: (401, "authentication_error", "Authentication failed"),
    AuthorizationException: (403, "authorization_error", "Not authorized"),
}


# ---------------------------------------------------------------------------
# 1. 등록 누락 가드 — AppException 서브클래스 자동 수집 ↔ 등록 비교
# ---------------------------------------------------------------------------


def test_all_app_exception_subclasses_are_registered() -> None:
    """AppException 의 모든 서브클래스 (production 정의) 가 등록됨.

    PR #45 의 슈퍼 fallback 은 runtime 안전망이지만, CI 시점에 등록 누락을
    정적 catch 하여 코드 리뷰 부담 감소.

    범위 한정: `app.core.exceptions` 모듈 내부에 정의된 서브클래스만 검사.
    테스트 모듈 내부의 시뮬레이션용 서브클래스 (예: PR #45 의 회귀 가드용
    `_UnregisteredException`) 는 제외 — 등록 누락 시뮬레이션이 본 가드를 깨지
    않도록.
    """
    registered: set[type[Exception]] = set(_registered_handlers().keys())
    production_subclasses: set[type[Exception]] = {
        cls
        for cls in AppException.__subclasses__()
        if cls.__module__ == "app.core.exceptions"
    }
    missing = production_subclasses - registered
    assert not missing, (
        f"AppException 서브클래스 등록 누락: {missing}. "
        f"`app/core/exceptions.py::register_exception_handlers` 에 추가하세요."
    )


def test_app_exception_super_fallback_is_registered() -> None:
    """AppException 자체가 슈퍼 fallback handler 로 등록됨 (PR #45 안전망)."""
    registered = _registered_handlers()
    assert AppException in registered, (
        "AppException 슈퍼 fallback 미등록 — 등록 누락된 서브클래스의 500 안전망 깨짐"
    )


# ---------------------------------------------------------------------------
# 2~4. 도메인 5종 default code / message / status 매핑
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc_cls,expected",
    DOMAIN_EXCEPTION_MATRIX.items(),
    ids=[c.__name__ for c in DOMAIN_EXCEPTION_MATRIX],
)
def test_domain_exception_default_code(
    exc_cls: type[AppException], expected: tuple[int, str, str]
) -> None:
    """5종 도메인 예외의 default `code` 회귀 가드 — envelope 응답에 노출되는 분류 키."""
    _, expected_code, _ = expected
    instance = exc_cls()
    assert instance.code == expected_code


@pytest.mark.parametrize(
    "exc_cls,expected",
    DOMAIN_EXCEPTION_MATRIX.items(),
    ids=[c.__name__ for c in DOMAIN_EXCEPTION_MATRIX],
)
def test_domain_exception_default_message(
    exc_cls: type[AppException], expected: tuple[int, str, str]
) -> None:
    """5종 도메인 예외의 default message 회귀 가드 (메시지 정책 변경 차단)."""
    _, _, expected_message = expected
    instance = exc_cls()
    assert instance.message == expected_message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_cls,expected_status",
    [(cls, matrix[0]) for cls, matrix in DOMAIN_EXCEPTION_MATRIX.items()],
    ids=[c.__name__ for c in DOMAIN_EXCEPTION_MATRIX],
)
async def test_domain_exception_handler_status_mapping(
    exc_cls: type[AppException], expected_status: int
) -> None:
    """5종 도메인 예외의 status 매핑 회귀 — handler closure 캡처값 검증."""
    handlers = _registered_handlers()
    handler = handlers[exc_cls]
    response = await handler(None, exc_cls("test message"))
    assert isinstance(response, JSONResponse)
    assert response.status_code == expected_status


# ---------------------------------------------------------------------------
# 5. HTTPException fallback envelope (PR #42)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_exception_fallback_envelope() -> None:
    """HTTPException → envelope (`{detail: {message, code: 'http_<status>'}}`)."""
    handlers = _registered_handlers()
    handler = handlers[StarletteHTTPException]
    exc = StarletteHTTPException(status_code=403, detail="Forbidden test")
    response = await handler(None, exc)
    body = json.loads(response.body)
    assert response.status_code == 403
    assert body == {"detail": {"message": "Forbidden test", "code": "http_403"}}


@pytest.mark.asyncio
async def test_http_exception_preserves_headers() -> None:
    """HTTPException headers (예: WWW-Authenticate) envelope 응답 보존 (PR #42)."""
    handlers = _registered_handlers()
    handler = handlers[StarletteHTTPException]
    exc = StarletteHTTPException(
        status_code=401,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Bearer"},
    )
    response = await handler(None, exc)
    assert response.headers["WWW-Authenticate"] == "Bearer"


# ---------------------------------------------------------------------------
# 6. 422 RequestValidationError envelope (PR #48)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_validation_error_envelope_structure() -> None:
    """422 envelope: code='request_validation_error' + errors 배열 + raw input 차단."""
    handlers = _registered_handlers()
    handler = handlers[RequestValidationError]
    # 실제 RequestValidationError 모사 — `input` 키는 raw body (PII 차단 대상)
    fake_errors: list[dict[str, Any]] = [
        {
            "loc": ("body", "email"),
            "msg": "field required",
            "type": "missing",
            "input": {"password": "secret-leak-must-not-appear"},
        }
    ]
    exc = RequestValidationError(errors=fake_errors)
    response = await handler(None, exc)
    body = json.loads(response.body)
    assert response.status_code == 422
    assert body["detail"]["code"] == "request_validation_error"
    assert body["detail"]["message"] == "Validation error"
    assert isinstance(body["detail"]["errors"], list)
    assert len(body["detail"]["errors"]) == 1
    item = body["detail"]["errors"][0]
    assert item == {
        "loc": ["body", "email"],
        "msg": "field required",
        "type": "missing",
    }
    # PII 차단 회귀 가드 — raw input 이 응답 어디에도 없음
    raw_response = response.body.decode("utf-8")
    assert "secret-leak-must-not-appear" not in raw_response
    assert "input" not in item


# ---------------------------------------------------------------------------
# 7. AppException 슈퍼 fallback (PR #45)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_exception_fallback_handler_500() -> None:
    """등록 누락된 AppException 서브클래스 → 슈퍼 fallback (500 + envelope, PR #45).

    실제 등록 누락 시 logger.exception + 500 응답. 동작 회귀 가드.
    """
    handlers = _registered_handlers()
    handler = handlers[AppException]

    # 가상의 등록 누락 서브클래스 (테스트 내부 정의 — 등록 누락 시뮬레이션)
    class _SimulatedUnregisteredException(AppException):
        def __init__(self) -> None:
            super().__init__(message="simulated unregistered", code="simulated")

    response = await handler(None, _SimulatedUnregisteredException())
    body = json.loads(response.body)
    assert response.status_code == 500
    assert body == {
        "detail": {"message": "simulated unregistered", "code": "simulated"}
    }


# ---------------------------------------------------------------------------
# 8. AuthenticationException 의 WWW-Authenticate 자동 첨부 (PR #46, RFC 7235)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authentication_exception_handler_includes_www_authenticate() -> None:
    """401 응답에 `WWW-Authenticate: Bearer` 자동 첨부 (RFC 7235 MUST, PR #46)."""
    handlers = _registered_handlers()
    handler = handlers[AuthenticationException]
    response = await handler(None, AuthenticationException("auth fail"))
    assert isinstance(response, JSONResponse)
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.status_code == 401
