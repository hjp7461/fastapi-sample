"""
사용자 관련 Pydantic 모델 (요청/응답 스키마).
"""

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator

from app.core.config import settings
from app.user.domain import User, UserRole
from app.user.masking import mask_email


@dataclass(frozen=True)
class UserListFilters:
    """User 리스트 필터 표면 (PR #66: filter/sort 표준화).

    service / repository 시그니처가 인자 폭증하지 않도록 dataclass 로 묶는다.
    schemas.py 에 위치한 이유: repository ↔ service 순환 import 회피
    (repository 가 service 의 dataclass 를 직접 import 가능).
    """

    role: UserRole | None = None
    is_active: bool | None = None
    q: str | None = None


class UserBase(BaseModel):
    """사용자 기본 속성."""

    email: EmailStr
    username: str
    first_name: str | None = None
    last_name: str | None = None
    role: UserRole | None = UserRole.CUSTOMER
    is_active: bool | None = True


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

    # PRD §5.6: PII 안전 — *@example.com / dummy 비밀번호 / 한국 통상 가명.
    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "newbie@example.com",
                "username": "newbie",
                "first_name": "길동",
                "last_name": "홍",
                "role": "customer",
                "is_active": True,
                "password": "dummy-secret-please-change",
                "password_confirm": "dummy-secret-please-change",
            }
        }
    }


class UserUpdate(BaseModel):
    """사용자 정보 업데이트 요청."""

    email: EmailStr | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=8, max_length=64)

    model_config = {
        "json_schema_extra": {
            "example": {
                "first_name": "길동",
                "last_name": "홍",
            }
        }
    }


class UserResponse(UserBase):
    """본인 조회 응답 — 전체 PII 노출 (email, 이름 포함).

    `GET /users/me` 및 `GET /users/{id}` 에서 viewer 가 본인일 때 사용.
    """

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 1,
                "email": "newbie@example.com",
                "username": "newbie",
                "first_name": "길동",
                "last_name": "홍",
                "role": "customer",
                "is_active": True,
                "created_at": "2026-05-26T09:00:00Z",
                "updated_at": "2026-05-26T09:00:00Z",
            }
        },
    }


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

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 2,
                "username": "veteran",
                "email": "v***@e***.com",
                "role": "staff",
                "is_active": True,
                "created_at": "2026-05-26T09:00:00Z",
                "updated_at": "2026-05-26T09:00:00Z",
            }
        },
    }


class UserSummary(BaseModel):
    """관리자 목록 조회 — PII 0건.

    `GET /users/` 에서 사용. id/username/role/is_active/created_at 만 노출.
    """

    id: int
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 1,
                "username": "newbie",
                "role": "customer",
                "is_active": True,
                "created_at": "2026-05-26T09:00:00Z",
            }
        },
    }


def build_admin_view(user: User) -> UserAdminView:
    """도메인 User 를 관리자용 응답으로 변환.

    email 마스킹은 `settings.USER_ADMIN_EMAIL_MASKING` 에 따라 결정.
    기본 True (마스킹 ON, 운영 안전). False 명시 시 raw email.
    """
    email = mask_email(user.email) if settings.USER_ADMIN_EMAIL_MASKING else user.email
    return UserAdminView(
        id=user.id,
        username=user.username,
        email=email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def build_summary(user: User) -> UserSummary:
    """도메인 User 를 요약 응답으로 변환 (PII 0건)."""
    return UserSummary(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


class Token(BaseModel):
    """인증 토큰."""

    access_token: str
    token_type: str = "bearer"

    model_config = {
        "json_schema_extra": {
            "example": {
                "access_token": (
                    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                    "eyJzdWIiOjEsImV4cCI6MTkwMDAwMDAwMH0."
                    "SAMPLE_SIGNATURE_NOT_A_REAL_TOKEN"
                ),
                "token_type": "bearer",
            }
        }
    }


class TokenPayload(BaseModel):
    """토큰 내용."""

    sub: int
    exp: datetime
