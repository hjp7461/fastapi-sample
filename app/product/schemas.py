"""
상품 관련 Pydantic 모델 (요청/응답 스키마) 정의.
API 요청 및 응답의 데이터 구조를 표현합니다.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, cast

from pydantic import BaseModel, Field

from app.product.domain import Product, ProductCategory


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
    """관리/staff 응답 — 전체 필드 (inventory 포함).

    `GET /products/{id}` 와 `GET /products/` 에서 viewer 가 staff 이상일 때 사용.
    POST/PUT/PATCH inventory 응답에도 사용 (모두 admin 권한).
    """

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductPublicView(BaseModel):
    """구매자/공개 응답 — inventory 제외.

    재고 수량은 영업 정보이므로 공개 조회에서 노출하지 않는다.
    """

    id: int
    name: str
    description: Optional[str] = None
    price: Decimal
    category: ProductCategory
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def build_public_view(product: Product) -> ProductPublicView:
    """도메인 Product 를 공개용으로 변환 (inventory 제외).

    DB 에서 가져온 product 는 id/created_at/updated_at not None — cast 로 narrow.
    price 는 도메인이 float|Decimal 합쳐 두지만 응답 스키마는 Decimal.
    """
    return ProductPublicView(
        id=cast(int, product.id),
        name=product.name,
        description=product.description,
        price=Decimal(str(product.price)),
        category=product.category,
        is_active=product.is_active,
        created_at=cast(datetime, product.created_at),
        updated_at=cast(datetime, product.updated_at),
    )


class ProductInventoryUpdate(BaseModel):
    """상품 재고 업데이트 요청."""

    quantity_change: int = Field(..., description="양수: 재고 증가, 음수: 재고 감소")
