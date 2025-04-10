"""
보안 관련 유틸리티 함수.
암호화, 토큰 생성 및 검증 등을 포함합니다.
"""
# from datetime import datetime, timedelta
from datetime import datetime, timedelta, UTC
from typing import Any, Dict, Optional, Union

import jwt
from passlib.context import CryptContext

from app.core.config import settings

# 비밀번호 해싱을 위한 컨텍스트
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    일반 텍스트 비밀번호와 해시된 비밀번호를 비교합니다.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    비밀번호를 해시합니다.
    """
    return pwd_context.hash(password)


def create_access_token(
        subject: Union[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """
    JWT 액세스 토큰을 생성합니다.

    Args:
        subject: 토큰의 주체 (일반적으로 사용자 ID)
        expires_delta: 토큰의 만료 기간

    Returns:
        str: 인코딩된 JWT 토큰
    """
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    JWT 액세스 토큰을 디코딩합니다.

    Args:
        token: 디코딩할 JWT 토큰

    Returns:
        Dict: 디코딩된 토큰 페이로드

    Raises:
        jwt.PyJWTError: 토큰이 유효하지 않을 경우
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM]
    )