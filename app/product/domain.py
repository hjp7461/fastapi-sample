"""
상품 도메인 엔티티 및 값 객체 정의.
핵심 비즈니스 로직과 규칙을 포함합니다.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Union


class ProductCategory(str, Enum):
    ELECTRONICS = "electronics"
    CLOTHING = "clothing"
    BOOKS = "books"
    HOME = "home"
    BEAUTY = "beauty"
    OTHER = "other"


@dataclass
class NewProduct:
    """신규 상품 생성용 도메인 객체 — DB save 이전 상태.

    id/created_at/updated_at 가 없음. service 가 입력 데이터를 정리하여 만들고
    repository.create() 에 전달. 저장 후 `Product` 로 반환된다.
    """

    name: str
    price: Union[float, Decimal]
    category: ProductCategory = ProductCategory.OTHER
    description: Optional[str] = None
    inventory: int = 0
    is_active: bool = True


@dataclass
class Product:
    """상품 도메인 엔티티 — DB save 이후 상태.

    id/created_at/updated_at 가 항상 not None (저장된 상품 표현). 신규
    생성은 `NewProduct` 사용 후 `repository.create()` 호출.

    `description` 은 미입력 가능 → Optional 유지.
    `price` 의 `Union[float, Decimal]` 통일은 별도 후속.
    """

    id: int
    name: str
    price: Union[float, Decimal]
    category: ProductCategory
    inventory: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    description: Optional[str] = None

    def is_in_stock(self) -> bool:
        """상품 재고가 있는지 확인합니다."""
        return self.inventory > 0 and self.is_active

    def can_order(self, quantity: int) -> bool:
        """주문 가능한 수량인지 확인합니다."""
        return self.inventory >= quantity and self.is_active
