"""
공통 API 의존성.
"""

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import PyJWTError

from app.core.config import settings
from app.core.exceptions import AuthenticationException, NotFoundException
from app.di.providers import get_user_service
from app.user.domain import User
from app.user.service import UserService

# OAuth2 인증 설정
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/users/token")

# 인증 실패 시 동일 메시지로 정보 누설 방지 (사용자 존재 여부 / 토큰 오류 등 구분 X).
# PR #46 의 handler 가 401 응답에 WWW-Authenticate Bearer 헤더 자동 첨부.
_CREDENTIALS_FAIL_MESSAGE = "Could not validate credentials"


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_service: UserService = Depends(get_user_service),
) -> User:
    """
    현재 인증된 사용자를 검색합니다.
    """
    try:
        # JWT 토큰 디코딩
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: int | None = int(payload.get("sub"))
        if user_id is None:
            raise AuthenticationException(_CREDENTIALS_FAIL_MESSAGE)
    except (PyJWTError, ValueError) as e:
        raise AuthenticationException(_CREDENTIALS_FAIL_MESSAGE) from e

    # 사용자 조회 — NotFoundException 도 동일 메시지로 변환 (사용자 존재 누설 방지)
    try:
        user = await user_service.get_user(user_id)
    except NotFoundException as e:
        raise AuthenticationException(_CREDENTIALS_FAIL_MESSAGE) from e

    if not user.is_active:
        # 본 PR 비범위 — inactive user 의 status (400 vs 401/403) 정책 결정은 별도.
        # PR #42 의 _http_exception_handler 가 envelope 형식 (`http_400`) 으로 변환.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user"
        )

    return user


async def get_optional_current_user(
    request: Request,
    user_service: UserService = Depends(get_user_service),
) -> User | None:
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
