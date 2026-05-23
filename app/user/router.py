"""
사용자 관련 API 엔드포인트.
HTTP 요청을 처리하고 적절한 서비스를 호출합니다.
"""
from typing import List, Any, Union

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.exceptions import NotFoundException, ValidationException
from app.di.providers import get_user_service
from app.api.dependencies import (
    get_current_active_admin,
    get_current_user,
    get_self_or_admin,
)
from app.user.domain import User
from app.user.schemas import (
    Token,
    UserAdminView,
    UserCreate,
    UserResponse,
    UserSummary,
    UserUpdate,
    build_admin_view,
    build_summary,
)
from app.user.service import UserService

router = APIRouter()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
        user_in: UserCreate,
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """새 사용자를 생성합니다."""
    try:
        user = await user_service.create_user(user_in.model_dump())
        return user
    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
        current_user: Any = Depends(get_current_user)
) -> Any:
    """현재 인증된 사용자 정보를 조회합니다."""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_current_user(
        user_in: UserUpdate,
        current_user: Any = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """현재 인증된 사용자 정보를 업데이트합니다."""
    try:
        user = await user_service.update_user(current_user.id, user_in.model_dump(exclude_unset=True))
        return user
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/token", response_model=Token)
async def login_for_access_token(
        form_data: OAuth2PasswordRequestForm = Depends(),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    OAuth2 호환 토큰 로그인, username 필드에 이메일 사용.
    """
    user = await user_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = user_service.create_access_token_for_user(user)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/{user_id}", response_model=Union[UserResponse, UserAdminView])
async def get_user_by_id(
        user_id: int,
        current_user: User = Depends(get_self_or_admin),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """특정 사용자 정보를 조회합니다. 본인 또는 관리자만 접근 가능.

    - 본인 조회: `UserResponse` (전체 PII)
    - 관리자가 타인 조회: `UserAdminView` (email 마스킹 + 이름 제외)
    """
    try:
        user = await user_service.get_user(user_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    if current_user.id == user.id:
        return user
    return build_admin_view(user)


@router.get("/", response_model=List[UserSummary])
async def list_users(
        skip: int = 0,
        limit: int = 100,
        _: Any = Depends(get_current_active_admin),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """사용자 목록을 조회합니다. 관리자 전용.

    응답은 `UserSummary` (PII 0건) — 목록 페이지에서 이메일/이름 무차별 노출 차단.
    """
    users = await user_service.list_users(skip=skip, limit=limit)
    return [build_summary(u) for u in users]