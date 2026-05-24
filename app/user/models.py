"""
사용자 관련 SQLAlchemy/SQLModel 모델 정의.
데이터베이스 스키마를 표현합니다.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, String
from sqlmodel import Field, SQLModel

from app.core.datetime import utcnow_aware
from app.user.domain import UserRole


class UserModel(SQLModel, table=True):
    """
    사용자 테이블 모델.
    """

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(sa_column=Column(String, unique=True, index=True))
    username: str = Field(sa_column=Column(String, unique=True, index=True))
    hashed_password: str = Field(sa_column=Column(String))
    first_name: str | None = Field(default=None)
    last_name: str | None = Field(default=None)
    role: UserRole = Field(sa_column=Column(Enum(UserRole), default=UserRole.CUSTOMER))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, default=True))
    created_at: datetime = Field(
        default_factory=utcnow_aware,
        sa_column=Column(
            DateTime(timezone=True),
            default=utcnow_aware,
        ),
    )
    updated_at: datetime = Field(
        default_factory=utcnow_aware,
        sa_column=Column(
            DateTime(timezone=True),
            default=utcnow_aware,
            onupdate=utcnow_aware,
        ),
    )
