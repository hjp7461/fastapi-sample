"""
공통 API 의존성.
"""
from typing import Optional, Union

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt.exceptions import PyJWTError

from app.core.config import settings
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


async def get_current_active_admin(
        current_user: User = Depends(get_current_user),
) -> User:
    """
    현재 인증된 사용자가 관리자인지 확인합니다.
    """
    if not current_user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


async def get_self_or_admin(
        user_id: int,
        current_user: User = Depends(get_current_user),
) -> User:
    """본인 또는 관리자만 통과하는 권한 가드.

    `user_id` 는 라우터의 path parameter 와 같은 이름으로 FastAPI 가 자동 주입.

    - 본인 (`current_user.id == user_id`) → 통과
    - 관리자 (`current_user.is_admin()`) → 통과
    - 그 외 → 403 Forbidden

    권한 검사는 자원의 존재 확인보다 먼저 평가되어 ID 열거 공격을 차단한다.
    """
    if current_user.id != user_id and not current_user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user