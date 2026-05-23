"""
공통 API 의존성.
"""
from typing import Optional, Union

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt.exceptions import PyJWTError

from app.core.config import settings
from app.core.exceptions import NotFoundException
from app.di.providers import get_user_service
from app.user.domain import User
from app.user.service import UserService

# OAuth2 인증 설정
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/users/token")


async def get_current_user(
        token: str = Depends(oauth2_scheme),
        user_service: UserService = Depends(get_user_service),
) -> User:
    """
    현재 인증된 사용자를 검색합니다.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # JWT 토큰 디코딩
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        user_id: Optional[int] = int(payload.get("sub"))
        if user_id is None:
            raise credentials_exception
    except (PyJWTError, ValueError):
        raise credentials_exception

    # 사용자 조회
    user = await user_service.get_user(user_id)
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    return user


async def get_optional_current_user(
        request: Request,
        user_service: UserService = Depends(get_user_service),
) -> Optional[User]:
    """공개 조회용 옵셔널 인증.

    `Authorization` 헤더가 없거나 토큰이 무효하면 ``None`` 을 반환한다
    (예외 X). 토큰이 유효하고 사용자가 활성 상태면 ``User`` 반환.

    공개 조회 엔드포인트 (예: `GET /products/...`) 에서 viewer 컨텍스트가
    있을 수도 없을 수도 있는 경우 사용한다.
    """
    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None

    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        user_id = int(payload.get("sub"))
    except (PyJWTError, ValueError, TypeError):
        return None

    try:
        user = await user_service.get_user(user_id)
    except NotFoundException:
        return None
    if not user.is_active:
        return None
    return user


