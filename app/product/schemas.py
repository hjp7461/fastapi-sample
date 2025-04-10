"""
상품 관련 Pydantic 모델 (요청/응답 스키마) 정의.
API 요청 및 응답의 데이터 구조를 표현합니다.
"""
from datetime import datetime
from typing import Optional
from decimal import Decimal

from pydantic import BaseModel, Field

from app.product.domain import ProductCategory


class ProductBase(BaseModel):
    """상품 기본 속성."""
    name: str
    description: Optional[str] = None
    price: Decimal = Field(..., ge=0)
    category: ProductCategory = ProductCategory.OTHER
    inventory: int = Field(0, ge=0)
    is_active: bool = True


class ProductCreate(ProductBase):
    """상품 생성 요청."""
    pass


class ProductUpdate(BaseModel):
    """상품 정보 업데이트 요청."""
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, ge=0)
    category: Optional[ProductCategory] = None
    inventory: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class ProductResponse(ProductBase):
    """상품 정보 응답."""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductInventoryUpdate(BaseModel):
    """상품 재고 업데이트 요청."""
    quantity_change: int = Field(..., description="양수: 재고 증가, 음수: 재고 감소")