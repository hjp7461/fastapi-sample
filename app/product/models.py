"""
상품 관련 SQLAlchemy/SQLModel 모델 정의.
데이터베이스 스키마를 표현합니다.
"""
from datetime import datetime
from typing import Optional
from decimal import Decimal

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Enum, Numeric
from sqlmodel import Field, SQLModel

from app.product.domain import ProductCategory


class ProductModel(SQLModel, table=True):
    """
    상품 테이블 모델.
    """
    __tablename__ = "products"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String, index=True))
    description: Optional[str] = Field(default=None)
    price: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    category: ProductCategory = Field(
        sa_column=Column(Enum(ProductCategory), default=ProductCategory.OTHER)
    )
    inventory: int = Field(default=0, sa_column=Column(Integer, default=0))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, default=True))
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, default=datetime.utcnow)
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(
            DateTime,
            default=datetime.utcnow,
            onupdate=datetime.utcnow
        )
    )