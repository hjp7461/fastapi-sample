"""
사용자 관련 Pydantic 모델 (요청/응답 스키마).
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.user.domain import UserRole


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

    @field_validator('password_confirm')
    def passwords_match(cls, v, info):
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('비밀번호가 일치하지 않습니다')
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
    """사용자 정보 응답."""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    """인증 토큰."""
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """토큰 내용."""
    sub: int
    exp: datetime