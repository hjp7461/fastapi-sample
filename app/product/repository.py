"""
상품 데이터 액세스 레이어.
데이터베이스와의 상호작용을 담당합니다.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.product.domain import Product, ProductCategory
from app.product.models import ProductModel


class InventoryUpdateOutcome(Enum):
    """`update_inventory` 의 세 결과를 명시.

    - OK: 갱신 성공
    - NOT_FOUND: 해당 product_id 가 존재하지 않음
    - INSUFFICIENT: 갱신 시 음수 재고 발생 (재고 부족)
    """

    OK = "ok"
    NOT_FOUND = "not_found"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class InventoryUpdateResult:
    """`update_inventory` 의 결과 객체.

    `outcome` 이 `OK` 일 때만 `product` 가 유효한 도메인 객체. 그 외는 `None`.
    """

    outcome: InventoryUpdateOutcome
    product: Optional[Product] = None


class ProductRepository:
    """
    상품 데이터 액세스 레이어.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, product: Product) -> Product:
        """새 상품을 생성합니다."""
        db_product = ProductModel(
            name=product.name,
            description=product.description,
            price=product.price,
            category=product.category,
            inventory=product.inventory,
            is_active=product.is_active,
        )
        self.session.add(db_product)
        await self.session.commit()
        await self.session.refresh(db_product)
        return self._to_domain(db_product)

    async def get_by_id(self, product_id: int) -> Optional[Product]:
        """ID로 상품을 조회합니다."""
        result = await self.session.execute(
            select(ProductModel).where(ProductModel.id == product_id)
        )
        db_product = result.scalars().first()
        if db_product:
            return self._to_domain(db_product)
        return None

    async def update(
        self, product_id: int, product_data: Dict[str, Any]
    ) -> Optional[Product]:
        """상품 정보를 업데이트합니다."""
        # 먼저 상품이 존재하는지 확인
        result = await self.session.execute(
            select(ProductModel).where(ProductModel.id == product_id)
        )
        db_product = result.scalars().first()
        if not db_product:
            return None

        # 업데이트할 필드 필터링
        update_data = {k: v for k, v in product_data.items() if v is not None}

        # 데이터가 있으면 업데이트 실행
        if update_data:
            await self.session.execute(
                update(ProductModel)
                .where(ProductModel.id == product_id)
                .values(**update_data)
            )
            await self.session.commit()

            # 업데이트된 상품 조회
            result = await self.session.execute(
                select(ProductModel).where(ProductModel.id == product_id)
            )
            db_product = result.scalars().first()

        return self._to_domain(db_product)

    async def delete(self, product_id: int) -> bool:
        """상품을 삭제합니다."""
        result = await self.session.execute(
            delete(ProductModel).where(ProductModel.id == product_id)
        )
        await self.session.commit()
        return result.rowcount > 0

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        category: Optional[ProductCategory] = None,
        is_active: Optional[bool] = None,
    ) -> List[Product]:
        """상품 목록을 조회합니다."""
        query = select(ProductModel)

        # 필터 적용
        if category:
            query = query.where(ProductModel.category == category)
        if is_active is not None:
            query = query.where(ProductModel.is_active == is_active)

        # 페이징 적용
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return [self._to_domain(product) for product in result.scalars().all()]

    async def update_inventory(
        self, product_id: int, quantity_change: int
    ) -> InventoryUpdateResult:
        """원자적 재고 변경.

        조건부 단일 UPDATE 로 race condition 을 차단한다.
        `inventory + quantity_change >= 0` 조건이 DB 레벨에서 평가되므로
        동시 차감 시에도 음수 재고가 발생할 수 없다.

        결과는 도메인 예외 없이 명시 outcome 으로 반환 — 호출자 (service) 가
        outcome 별로 적절한 도메인 예외로 변환한다.
        """
        result = await self.session.execute(
            update(ProductModel)
            .where(ProductModel.id == product_id)
            .where(ProductModel.inventory + quantity_change >= 0)
            .values(inventory=ProductModel.inventory + quantity_change)
        )
        await self.session.commit()

        if result.rowcount == 0:
            # 상품 없음 vs 재고 부족 구분
            select_result = await self.session.execute(
                select(ProductModel).where(ProductModel.id == product_id)
            )
            db_product = select_result.scalars().first()
            if db_product is None:
                return InventoryUpdateResult(outcome=InventoryUpdateOutcome.NOT_FOUND)
            return InventoryUpdateResult(outcome=InventoryUpdateOutcome.INSUFFICIENT)

        # 갱신된 결과 재조회
        select_result = await self.session.execute(
            select(ProductModel).where(ProductModel.id == product_id)
        )
        db_product = select_result.scalars().first()
        return InventoryUpdateResult(
            outcome=InventoryUpdateOutcome.OK,
            product=self._to_domain(db_product),
        )

    def _to_domain(self, db_product: ProductModel) -> Product:
        """데이터베이스 모델을 도메인 엔티티로 변환합니다."""
        return Product(
            id=db_product.id,
            name=db_product.name,
            description=db_product.description,
            price=db_product.price,
            category=db_product.category,
            inventory=db_product.inventory,
            is_active=db_product.is_active,
            created_at=db_product.created_at,
            updated_at=db_product.updated_at,
        )
