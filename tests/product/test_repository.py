"""ProductRepository.update_inventory 결과 패턴 단위 회귀.

PR #14 후속으로 도입한 enum 결과 패턴이 세 outcome (OK / NOT_FOUND / INSUFFICIENT)
을 정확히 표현하는지 검증한다. 라우터 통합 테스트와 별개의 layer 회귀 가드.
"""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.result import CrudOutcome
from app.product.domain import NewProduct, ProductCategory
from app.product.repository import (
    InventoryUpdateOutcome,
    InventoryUpdateResult,
    ProductRepository,
)


@pytest.mark.asyncio
async def test_update_inventory_returns_ok_on_success(db_session: AsyncSession) -> None:
    """정상 갱신: outcome.OK + product 반영."""
    repo = ProductRepository(db_session)
    product = await repo.create(
        NewProduct(
            name="P1",
            description=None,
            price=Decimal("10.00"),
            category=ProductCategory.OTHER,
            inventory=10,
            is_active=True,
        )
    )

    result = await repo.update_inventory(product.id, -3)

    assert isinstance(result, InventoryUpdateResult)
    assert result.outcome == InventoryUpdateOutcome.OK
    assert result.product is not None
    assert result.product.inventory == 7


@pytest.mark.asyncio
async def test_update_inventory_returns_not_found_for_missing_id(
    db_session: AsyncSession,
) -> None:
    """없는 id: outcome.NOT_FOUND + product None."""
    repo = ProductRepository(db_session)

    result = await repo.update_inventory(9999, -1)

    assert result.outcome == InventoryUpdateOutcome.NOT_FOUND
    assert result.product is None


@pytest.mark.asyncio
async def test_update_inventory_returns_insufficient_when_negative(
    db_session: AsyncSession,
) -> None:
    """음수 발생: outcome.INSUFFICIENT + 재고 보존."""
    repo = ProductRepository(db_session)
    product = await repo.create(
        NewProduct(
            name="P2",
            description=None,
            price=Decimal("5.00"),
            category=ProductCategory.OTHER,
            inventory=2,
            is_active=True,
        )
    )

    result = await repo.update_inventory(product.id, -10)

    assert result.outcome == InventoryUpdateOutcome.INSUFFICIENT
    assert result.product is None

    # 재고는 변화 없음 — 조건부 UPDATE 가 차단
    fresh = await repo.get_by_id(product.id)
    assert fresh.outcome == CrudOutcome.OK
    assert fresh.value is not None
    assert fresh.value.inventory == 2
