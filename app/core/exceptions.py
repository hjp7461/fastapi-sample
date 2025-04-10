"""
애플리케이션 커스텀 예외 정의.
"""
from typing import Any, Optional


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
    def __init__(self, message: str = "Authentication failed", code: Optional[str] = None):
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
    def __init__(self, message: str = "Business logic error", code: Optional[str] = None):
        super().__init__(message=message, code=code or "business_logic_error")