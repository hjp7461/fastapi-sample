"""
상품 데이터 액세스 레이어.
데이터베이스와의 상호작용을 담당합니다.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement, Select

from app.core.result import CrudOutcome, CrudResult
from app.core.sort import SortField, escape_like_pattern
from app.product.domain import NewProduct, Product
from app.product.models import ProductModel
from app.product.schemas import ProductListFilters


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
    product: Product | None = None


# router 의 `_PRODUCT_SORT_FIELDS` 화이트리스트와 1:1 대응 (수동 동기화).
_PRODUCT_SORT_COLUMN_MAP: dict[str, ColumnElement[Any]] = {
    "id": ProductModel.id,
    "name": ProductModel.name,
    "price": ProductModel.price,
    "created_at": ProductModel.created_at,
    "inventory": ProductModel.inventory,
}


def _apply_product_filters(
    query: Select[Any], filters: ProductListFilters
) -> Select[Any]:
    """list / count 공통 필터 적용 (PR #66).

    q 검색 대상: name, description (DB 컬럼).
    """
    if filters.category is not None:
        query = query.where(ProductModel.category == filters.category)
    if filters.is_active is not None:
        query = query.where(ProductModel.is_active == filters.is_active)
    if filters.q is not None:
        pattern = f"%{escape_like_pattern(filters.q)}%"
        query = query.where(
            or_(
                func.lower(ProductModel.name).like(pattern, escape="\\"),
                func.lower(ProductModel.description).like(pattern, escape="\\"),
            )
        )
    return query


class ProductRepository:
    """
    상품 데이터 액세스 레이어.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, new_product: NewProduct) -> Product:
        """새 상품을 생성합니다. DB save 후 `Product` 로 변환하여 반환."""
        db_product = ProductModel(
            name=new_product.name,
            description=new_product.description,
            price=new_product.price,
            category=new_product.category,
            inventory=new_product.inventory,
            is_active=new_product.is_active,
        )
        self.session.add(db_product)
        await self.session.commit()
        await self.session.refresh(db_product)
        return self._to_domain(db_product)

    async def get_by_id(self, product_id: int) -> CrudResult[Product]:
        """ID로 상품을 조회합니다 (PR #56: CrudResult 패턴)."""
        result = await self.session.execute(
            select(ProductModel).where(ProductModel.id == product_id)
        )
        db_product = result.scalars().first()
        if db_product is None:
            return CrudResult(outcome=CrudOutcome.NOT_FOUND)
        return CrudResult(outcome=CrudOutcome.OK, value=self._to_domain(db_product))

    async def update(
        self, product_id: int, product_data: dict[str, Any]
    ) -> CrudResult[Product]:
        """상품 정보를 업데이트합니다 (PR #56)."""
        result = await self.session.execute(
            select(ProductModel).where(ProductModel.id == product_id)
        )
        db_product = result.scalars().first()
        if db_product is None:
            return CrudResult(outcome=CrudOutcome.NOT_FOUND)

        update_data = {k: v for k, v in product_data.items() if v is not None}

        if update_data:
            await self.session.execute(
                update(ProductModel)
                .where(ProductModel.id == product_id)
                .values(**update_data)
            )
            await self.session.commit()

            result = await self.session.execute(
                select(ProductModel).where(ProductModel.id == product_id)
            )
            db_product = result.scalars().first()

        return CrudResult(outcome=CrudOutcome.OK, value=self._to_domain(db_product))

    async def delete(self, product_id: int) -> CrudResult[None]:
        """상품을 삭제합니다 (PR #56: bool → outcome enum)."""
        result = await self.session.execute(
            delete(ProductModel).where(ProductModel.id == product_id)
        )
        await self.session.commit()
        outcome = CrudOutcome.OK if result.rowcount > 0 else CrudOutcome.NOT_FOUND
        return CrudResult(outcome=outcome)

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: ProductListFilters | None = None,
        sort: list[SortField] | None = None,
    ) -> list[Product]:
        """상품 목록을 조회합니다 (PR #66: filter/sort 표준화).

        filters/sort default 시 PR #52 동작과 동일 (호환성).
        """
        _filters = filters if filters is not None else ProductListFilters()
        _sort = sort if sort is not None else []

        query: Select[Any] = select(ProductModel)
        query = _apply_product_filters(query, _filters)
        for sf in _sort:
            col = _PRODUCT_SORT_COLUMN_MAP[sf.field]
            query = query.order_by(col.desc() if sf.descending else col.asc())
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return [self._to_domain(product) for product in result.scalars().all()]

    async def count(self, filters: ProductListFilters | None = None) -> int:
        """필터 적용 후 상품 수 — pagination meta 의 total (PR #52/#66)."""
        _filters = filters if filters is not None else ProductListFilters()
        query: Select[Any] = select(func.count()).select_from(ProductModel)
        query = _apply_product_filters(query, _filters)
        result = await self.session.execute(query)
        return result.scalar_one()

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
