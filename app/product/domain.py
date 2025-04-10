"""
상품 도메인 엔티티 및 값 객체 정의.
핵심 비즈니스 로직과 규칙을 포함합니다.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Union


class ProductCategory(str, Enum):
    ELECTRONICS = "electronics"
    CLOTHING = "clothing"
    BOOKS = "books"
    HOME = "home"
    BEAUTY = "beauty"
    OTHER = "other"


@dataclass
class Product:
    """상품 도메인 엔티티."""
    id: Optional[int] = None
    name: str = ""
    description: Optional[str] = None
    price: Union[float, Decimal] = 0.0
    category: ProductCategory = ProductCategory.OTHER
    inventory: int = 0
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def is_in_stock(self) -> bool:
        """상품 재고가 있는지 확인합니다."""
        return self.inventory > 0 and self.is_active

    def can_order(self, quantity: int) -> bool:
        """주문 가능한 수량인지 확인합니다."""
        return self.inventory >= quantity and self.is_active