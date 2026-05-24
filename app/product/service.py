"""
상품 서비스 구현.
비즈니스 로직과 유즈케이스를 포함합니다.
"""

from typing import Any

from app.core.exceptions import (
    BusinessLogicException,
    NotFoundException,
)
from app.product.domain import NewProduct, Product, ProductCategory
from app.product.repository import (
    InventoryUpdateOutcome,
    ProductRepository,
)


class ProductService:
    """
    상품 관련 비즈니스 로직을 처리하는 서비스.
    """

    def __init__(self, product_repository: ProductRepository):
        self.product_repository = product_repository

    async def create_product(self, product_data: dict[str, Any]) -> Product:
        """새 상품을 생성합니다."""
        new_product = NewProduct(
            name=product_data["name"],
            description=product_data.get("description"),
            price=product_data["price"],
            category=product_data.get("category", ProductCategory.OTHER),
            inventory=product_data.get("inventory", 0),
            is_active=product_data.get("is_active", True),
        )

        return await self.product_repository.create(new_product)

    async def get_product(self, product_id: int) -> Product:
        """ID로 상품을 조회합니다."""
        product = await self.product_repository.get_by_id(product_id)
        if not product:
            raise NotFoundException(f"Product with ID {product_id} not found")
        return product

    async def update_product(
        self, product_id: int, product_data: dict[str, Any]
    ) -> Product:
        """상품 정보를 업데이트합니다."""
        product = await self.product_repository.update(product_id, product_data)
        if not product:
            raise NotFoundException(f"Product with ID {product_id} not found")

        return product

    async def delete_product(self, product_id: int) -> bool:
        """상품을 삭제합니다."""
        # 삭제 전 존재 확인
        product = await self.product_repository.get_by_id(product_id)
        if not product:
            raise NotFoundException(f"Product with ID {product_id} not found")

        return await self.product_repository.delete(product_id)

    async def list_products(
        self,
        skip: int = 0,
        limit: int = 100,
        category: ProductCategory | None = None,
        is_active: bool | None = None,
    ) -> list[Product]:
        """상품 목록을 조회합니다."""
        return await self.product_repository.list(
            skip=skip, limit=limit, category=category, is_active=is_active
        )

    async def update_inventory(self, product_id: int, quantity_change: int) -> Product:
        """상품 재고를 업데이트합니다.

        repository 가 반환하는 `InventoryUpdateResult` 의 outcome 을 명시 분기해
        도메인 예외로 변환한다. 존재 확인과 재고 부족 검증은 repository 의
        조건부 UPDATE 가 원자적으로 담당.
        """
        result = await self.product_repository.update_inventory(
            product_id, quantity_change
        )

        match result.outcome:
            case InventoryUpdateOutcome.OK:
                assert result.product is not None
                return result.product
            case InventoryUpdateOutcome.NOT_FOUND:
                raise NotFoundException(f"Product with ID {product_id} not found")
            case InventoryUpdateOutcome.INSUFFICIENT:
                raise BusinessLogicException(
                    f"Not enough inventory for product {product_id}"
                )
