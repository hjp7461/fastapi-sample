"""
사용자 관련 Pydantic 모델 (요청/응답 스키마).
"""

from datetime import datetime
from typing import Optional, cast

from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator

from app.core.config import settings
from app.user.domain import User, UserRole
from app.user.masking import mask_email


class UserBase(BaseModel):
    """사용자 기본 속성."""

    email: EmailStr
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[UserRole] = UserRole.CUSTOMER
    is_active: Optional[bool] = True


class UserCreate(UserBase):
    """사용자 생성 요청."""

    password: str = Field(..., min_length=8, max_length=64)
    password_confirm: str

    @field_validator("password_confirm")
    @classmethod
    def passwords_match(cls, v: str, info: ValidationInfo) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("비밀번호가 일치하지 않습니다")
        return v


class UserUpdate(BaseModel):
    """사용자 정보 업데이트 요청."""

    email: Optional[EmailStr] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=64)


class UserResponse(UserBase):
    """본인 조회 응답 — 전체 PII 노출 (email, 이름 포함).

    `GET /users/me` 및 `GET /users/{id}` 에서 viewer 가 본인일 때 사용.
    """

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserAdminView(BaseModel):
    """관리자가 타인을 상세 조회할 때의 응답 — PII 최소화.

    - email 은 기본 마스킹 (`a***@e***.com`).
      `settings.USER_ADMIN_EMAIL_MASKING=false` 면 raw email 노출 (dev 디버깅용).
    - first_name / last_name 은 응답에서 제외 (스키마 자체 — 토글 불가)
    """

    id: int
    username: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserSummary(BaseModel):
    """관리자 목록 조회 — PII 0건.

    `GET /users/` 에서 사용. id/username/role/is_active/created_at 만 노출.
    """

    id: int
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


def build_admin_view(user: User) -> UserAdminView:
    """도메인 User 를 관리자용 응답으로 변환.

    email 마스킹은 `settings.USER_ADMIN_EMAIL_MASKING` 에 따라 결정.
    기본 True (마스킹 ON, 운영 안전). False 명시 시 raw email.

    DB 에서 가져온 user 의 id/created_at/updated_at 은 항상 not None 이지만
    도메인 모델이 Optional 로 선언 — builder 호출 시점에서 cast.
    """
    email = mask_email(user.email) if settings.USER_ADMIN_EMAIL_MASKING else user.email
    return UserAdminView(
        id=cast(int, user.id),
        username=user.username,
        email=email,
        role=user.role,
        is_active=user.is_active,
        created_at=cast(datetime, user.created_at),
        updated_at=cast(datetime, user.updated_at),
    )


def build_summary(user: User) -> UserSummary:
    """도메인 User 를 요약 응답으로 변환 (PII 0건).

    DB 에서 가져온 user 는 id/created_at not None — cast 로 builder 시점 narrow.
    """
    return UserSummary(
        id=cast(int, user.id),
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=cast(datetime, user.created_at),
    )


class Token(BaseModel):
    """인증 토큰."""

    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """토큰 내용."""

    sub: int
    exp: datetime
