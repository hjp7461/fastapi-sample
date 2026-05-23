# [PRD] repository 예외 → enum 결과 패턴 (update_inventory)

| 항목 | 내용 |
| --- | --- |
| 상태 | 제안 (Draft) |
| 작성일 | 2026-05-23 |
| 출처 | PR #3 §5 결정 사항 후속, [HANDOFF] §6 마스터 목록 |
| 분류 | 클린 아키텍처 (계층 책임 정리) |
| 추정 작업량 | 중 (1.5~2 시간, 결과 타입 도입 + service 분기 + 단위 테스트) |

---

## 1. 배경

### 1.1 현재 시그니처의 혼합

`app/product/repository.py::update_inventory` 는 **세 가지 결과** 를 **두 가지 방식 (return vs raise)** 으로 섞어서 반환한다.

```python
async def update_inventory(self, product_id: int, quantity_change: int) -> Optional[Product]:
    """
    반환:
        Product : 갱신 성공
        None    : 상품 없음
    예외:
        BusinessLogicException : 재고 부족 (변경 시 음수 발생)
    """
```

- 성공 → `Product` 반환
- 상품 없음 → `None` 반환
- 재고 부족 → 예외 던짐

이는 다음 문제를 만든다.

1. **타입 시그니처가 거짓말** — `Optional[Product]` 만 보면 두 가지 결과만 있는 줄 알지만 실제로는 세 가지.
2. **repository 가 도메인 예외에 의존** — `app/core/exceptions.BusinessLogicException` 을 import. 클린 아키텍처상 "repository 는 데이터 접근만, 비즈니스 의미는 service 가" 라는 책임 분리에 위배.
3. **호출자의 분기가 비대칭** — `None` 체크는 명시, 예외는 try/except. 두 메커니즘으로 한 메서드를 처리.
4. **PR #3 PRD §5** 에서 이미 enum 결과 패턴을 후속 옵션으로 명시. "향후 다른 도메인 메서드에서 동일 패턴이 반복되면 enum 으로 리팩토링 검토."

### 1.2 다른 repository 메서드와의 비교

- `user/repository.py::update`, `product/repository.py::update`, `delete`, `get_by_id`, `list` — 모두 `Optional[T]` 또는 `bool` 반환, 예외 던지지 않음. 호출자가 `if not result:` 패턴으로 일관 분기.
- 본 PR 의 대상은 **`update_inventory` 한 메서드** — 가장 혼합도가 높은 케이스만 명시 결과 패턴으로 정리.

---

## 2. 목적

1. `update_inventory` 의 세 결과를 **명시적 enum** 으로 표현 (`InventoryUpdateOutcome`).
2. repository 가 **도메인 예외에 의존하지 않도록** — `BusinessLogicException` import 제거.
3. service 계층에서 outcome 을 **`match` 문 또는 if 체인** 으로 누락 없이 분기 — 새 outcome 추가 시 호환성을 컴파일/리뷰 단계에서 강제.
4. 외부 API 동작 불변 — 동일한 HTTP 응답 (200/404/400/422) 보장.

---

## 3. 비목적

- 다른 repository 메서드들 (`get_by_id`, `update`, `delete`, `list`, `create`) 의 시그니처 변경 — 본 PR 은 **혼합 시그니처 한 곳만**.
- 비즈니스 예외 전체 정의 재설계 — `app/core/exceptions.py` 는 그대로.
- product 도메인 외 (user 도메인 등) repository 의 결과 패턴 적용 — 후속.
- `tuple[Outcome, Optional[Product]]` 대신 dataclass — **dataclass 채택** (호출처 명료성 우선).
- Python 3.10+ `match` 강제 — 권장하되 가독성 비교 후 if 체인도 허용.

---

## 4. 성공 기준

- [ ] `app/product/repository.py` 에 `InventoryUpdateOutcome` enum + `InventoryUpdateResult` dataclass 신규.
- [ ] `update_inventory` 의 반환 타입이 `InventoryUpdateResult` (dataclass), 예외를 던지지 않음.
- [ ] `app/product/repository.py` 에서 `BusinessLogicException` import 제거.
- [ ] `app/product/service.py::update_inventory` 가 outcome 을 명시 분기하여 도메인 예외를 적절히 던짐 (`NotFoundException`, `BusinessLogicException`).
- [ ] 기존 52 PASS 유지 (외부 API 동작 불변).
- [ ] 신규 회귀 가드:
  - `update_inventory` OK 케이스 → `outcome == OK` + `product is not None`
  - `update_inventory` NOT_FOUND 케이스 → `outcome == NOT_FOUND` + `product is None`
  - `update_inventory` INSUFFICIENT 케이스 → `outcome == INSUFFICIENT` + `product is None`
- [ ] product 라우터 통합 테스트 13건은 그대로 통과 (응답/상태코드 변화 없음).

---

## 5. 설계

### 5.1 결과 타입 (`app/product/repository.py`)

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional


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
```

### 5.2 `update_inventory` 재작성

```python
async def update_inventory(
    self, product_id: int, quantity_change: int
) -> InventoryUpdateResult:
    """원자적 재고 변경.

    조건부 단일 UPDATE 로 race condition 차단. 결과는 명시적 outcome 으로
    표현하므로 repository 는 도메인 예외를 모른다.
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
```

`BusinessLogicException` import 제거.

### 5.3 service 분기 재구성 (`app/product/service.py`)

```python
from app.product.repository import (
    InventoryUpdateOutcome,
    InventoryUpdateResult,
    ProductRepository,
)


async def update_inventory(self, product_id: int, quantity_change: int) -> Product:
    """상품 재고를 업데이트합니다.

    repository 가 반환하는 InventoryUpdateResult 를 명시 분기해 도메인 예외로 변환.
    """
    result = await self.product_repository.update_inventory(
        product_id, quantity_change
    )

    match result.outcome:
        case InventoryUpdateOutcome.OK:
            assert result.product is not None
            return result.product
        case InventoryUpdateOutcome.NOT_FOUND:
            raise NotFoundException(
                f"Product with ID {product_id} not found"
            )
        case InventoryUpdateOutcome.INSUFFICIENT:
            raise BusinessLogicException(
                f"Not enough inventory for product {product_id}"
            )
```

`match` 문은 새 outcome 추가 시 모든 case 를 검토하도록 강제 (정적 분석/리뷰 단계). Python 3.12 환경.

### 5.4 라우터 (`app/product/router.py`)

**변화 없음**. 기존 `BusinessLogicException` / `NotFoundException` 처리 코드 그대로. service 가 같은 예외를 던지므로 라우터의 catch 블록 영향 0.

### 5.5 단위 테스트 매트릭스

`tests/product/test_repository.py` 신규 (현재 product 테스트가 router 통합만 있고 repository 단위 테스트는 부재).

```python
# tests/product/test_repository.py
"""ProductRepository.update_inventory 결과 패턴 단위 회귀."""
import pytest
from decimal import Decimal

from app.product.domain import Product, ProductCategory
from app.product.repository import (
    InventoryUpdateOutcome,
    InventoryUpdateResult,
    ProductRepository,
)


@pytest.mark.asyncio
async def test_update_inventory_returns_ok_on_success(db_session):
    repo = ProductRepository(db_session)
    product = await repo.create(Product(
        name="P1", description=None, price=Decimal("10.00"),
        category=ProductCategory.OTHER, inventory=10, is_active=True,
    ))

    result = await repo.update_inventory(product.id, -3)

    assert isinstance(result, InventoryUpdateResult)
    assert result.outcome == InventoryUpdateOutcome.OK
    assert result.product is not None
    assert result.product.inventory == 7


@pytest.mark.asyncio
async def test_update_inventory_returns_not_found_for_missing_id(db_session):
    repo = ProductRepository(db_session)

    result = await repo.update_inventory(9999, -1)

    assert result.outcome == InventoryUpdateOutcome.NOT_FOUND
    assert result.product is None


@pytest.mark.asyncio
async def test_update_inventory_returns_insufficient_when_negative(db_session):
    repo = ProductRepository(db_session)
    product = await repo.create(Product(
        name="P2", description=None, price=Decimal("5.00"),
        category=ProductCategory.OTHER, inventory=2, is_active=True,
    ))

    result = await repo.update_inventory(product.id, -10)

    assert result.outcome == InventoryUpdateOutcome.INSUFFICIENT
    assert result.product is None
    # 재고는 변화 없음
    fresh = await repo.get_by_id(product.id)
    assert fresh.inventory == 2
```

### 5.6 기존 라우터 테스트 검증

`tests/product/test_router.py` 의 13건은 외부 API 호환성을 검증한다. 본 PR 은 외부 API 응답 동일하므로 변경 없이 모두 통과 기대.

리스크: PR #3 의 동시성 시뮬레이션 테스트 (`test_update_inventory_concurrent_charge_blocks_below_zero` 같은 케이스) 가 repository 의 raise 패턴에 의존한다면 service 단을 거치므로 영향 없을 것으로 예측. 실제 실행으로 확인.

---

## 6. 영향

| 영역 | 영향 |
| --- | --- |
| `app/product/repository.py` | `InventoryUpdateOutcome`/`InventoryUpdateResult` 신규, `update_inventory` 반환 타입 변경, `BusinessLogicException` import 제거 |
| `app/product/service.py` | `update_inventory` 가 outcome 분기 (`match`) |
| `app/product/router.py` | **변화 없음** |
| `tests/product/test_repository.py` | **신규** — 결과 패턴 단위 회귀 3건 |
| `tests/product/test_router.py` | **변화 없음** — 외부 API 호환성 그대로 |
| 외부 API / DB 스키마 | **변화 없음** |
| 응답 매트릭스 | 동일 (200/404/400/422) |

---

## 7. 리스크

| 리스크 | 가능성 | 대응 |
| --- | --- | --- |
| `match` 문이 outcome 누락 시 silently fall through | 낮음 | `match` 의 모든 case 가 명시. 누락된 case 는 `case _:` 없으면 자연스러운 미처리 — 테스트가 잡음 |
| dataclass `frozen=True` 가 product 직렬화에 영향 | 매우 낮음 | dataclass 는 repository → service 경계의 내부 객체. router 응답에 닿지 않음 |
| 다른 service 메서드가 repository.update_inventory 의 예외에 의존 | 매우 낮음 | grep 으로 호출처 확인. 현재 product/service.py 하나만 호출 |
| 단위 테스트가 db_session fixture 에 의존 → 격리 부담 | 낮음 | 기존 conftest 가 인메모리 + StaticPool 제공. 새 테스트도 동일 fixture 활용 |

---

## 8. 결정 사항 (확정)

- [x] **dataclass 채택** — tuple unpacking 보다 `result.outcome` / `result.product` 명료성 우선.
- [x] enum 이름: `InventoryUpdateOutcome` (값/result/등 동사·명사 혼합 회피).
- [x] dataclass 이름: `InventoryUpdateResult`. `frozen=True`.
- [x] service 분기는 `match` 채택 (Python 3.12, 누락 가시화).
- [x] `BusinessLogicException` import 는 repository 에서 제거, service 에서 유지.
- [x] 본 PR 범위: **`update_inventory` 한 메서드만**. 다른 메서드는 후속 검토 대상.
- [x] 단위 테스트는 신규 파일 `tests/product/test_repository.py` 에 분리 (라우터 통합 vs repository 단위).

---

## 9. 참고

- `docs/[PRD]상품_재고_변경_원자성.md` §5 결정 사항
- `app/product/repository.py`, `app/product/service.py`
- `app/core/exceptions.py`
- Python `match` (PEP 634): https://peps.python.org/pep-0634/
