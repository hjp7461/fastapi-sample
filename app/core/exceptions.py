"""
애플리케이션 커스텀 예외 정의 + handler 등록.
"""

from collections.abc import Awaitable, Callable
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppException(Exception):
    """
    애플리케이션 기본 예외 클래스.
    """

    def __init__(self, message: str = "An error occurred", code: Optional[str] = None):
        self.message = message
        self.code = code
        super().__init__(self.message)


class NotFoundException(AppException):
    """
    리소스를 찾을 수 없을 때 발생하는 예외.
    """

    def __init__(self, message: str = "Resource not found", code: Optional[str] = None):
        super().__init__(message=message, code=code or "not_found")


class ValidationException(AppException):
    """
    데이터 검증 실패 시 발생하는 예외.
    """

    def __init__(self, message: str = "Validation error", code: Optional[str] = None):
        super().__init__(message=message, code=code or "validation_error")


class AuthenticationException(AppException):
    """
    인증 실패 시 발생하는 예외.
    """

    def __init__(
        self, message: str = "Authentication failed", code: Optional[str] = None
    ):
        super().__init__(message=message, code=code or "authentication_error")


class AuthorizationException(AppException):
    """
    권한 부족 시 발생하는 예외.
    """

    def __init__(self, message: str = "Not authorized", code: Optional[str] = None):
        super().__init__(message=message, code=code or "authorization_error")


class BusinessLogicException(AppException):
    """
    비즈니스 로직 오류 시 발생하는 예외.
    """

    def __init__(
        self, message: str = "Business logic error", code: Optional[str] = None
    ):
        super().__init__(message=message, code=code or "business_logic_error")


# ---------------------------------------------------------------------------
# Exception handler 등록 (도메인 예외 → HTTP status 단일 진실원)
# ---------------------------------------------------------------------------


def _make_handler(
    status_code: int,
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    """도메인 예외를 envelope 응답으로 변환하는 핸들러 생성 (PR #42).

    응답 형식: {"detail": {"message": str(exc), "code": exc.code}}
    `code` 는 `AppException.code` (예: 'not_found', 'validation_error').
    """

    async def handler(request: Request, exc: Exception) -> JSONResponse:
        code = exc.code if isinstance(exc, AppException) else "unknown"
        return JSONResponse(
            status_code=status_code,
            content={
                "detail": {
                    "message": str(exc),
                    "code": code,
                }
            },
        )

    return handler


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """HTTPException (starlette/FastAPI) → envelope 응답 변환 (PR #42).

    code 는 `http_<status>` fallback (예: 'http_401', 'http_403').
    `headers` (예: WWW-Authenticate) 는 OAuth2 호환을 위해 보존.
    """
    assert isinstance(exc, StarletteHTTPException)
    detail = exc.detail
    message = detail if isinstance(detail, str) else str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": {
                "message": message,
                "code": f"http_{exc.status_code}",
            }
        },
        headers=getattr(exc, "headers", None),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """앱 시작 시 도메인 예외 + HTTPException → envelope 응답 매핑 등록.

    단일 진실원: 모든 도메인 예외 / HTTPException 은 본 등록을 통해 정확한
    status + envelope 으로 자동 변환. 라우터 본문의 try/except 보일러플레이트
    불필요 (PR #41).

    응답 형식 (PR #42): {"detail": {"message": str, "code": str}}
    - 도메인 예외 5종: code = AppException.code (예: 'not_found')
    - HTTPException: code = 'http_<status>' (예: 'http_401')
    """
    app.add_exception_handler(NotFoundException, _make_handler(404))
    app.add_exception_handler(ValidationException, _make_handler(400))
    app.add_exception_handler(BusinessLogicException, _make_handler(400))
    app.add_exception_handler(AuthenticationException, _make_handler(401))
    app.add_exception_handler(AuthorizationException, _make_handler(403))
    # HTTPException (starlette 등록 → FastAPI HTTPException 자동 catch 서브클래스)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
