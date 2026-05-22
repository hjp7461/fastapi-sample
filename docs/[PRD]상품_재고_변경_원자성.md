# 상품 재고 변경 원자성 보장 PRD

| 항목       | 내용                                                                              |
| ---------- | --------------------------------------------------------------------------------- |
| 작성일     | 2026-05-22                                                                        |
| 작성자     | conner                                                                            |
| 상태       | 제안 (Draft)                                                                      |
| 도메인     | Product                                                                           |
| 대상 범위  | `app/product/service.py:73 update_inventory`, `app/product/repository.py:108 update_inventory` |
| 관련 발견  | `docs/diagram/상품_관리_관리자.md` 작성 중 race condition + silent failure 캐치  |

---

## 1. 배경

`PATCH /api/v1/products/{product_id}/inventory` 의 재고 변경은 다음 순서로 동작한다.

```
[Service.update_inventory]
  1. repository.get_by_id(id)            ← SELECT
  2. 재고 부족 검증 (quantity_change < 0 and abs > inventory)
  3. repository.update_inventory(id, qc) ← 호출

[Repository.update_inventory]
  4. SELECT * FROM products WHERE id = ?
  5. new_inventory = current + qc
  6. if new_inventory < 0: new_inventory = 0   ← 음수 클램프
  7. UPDATE products SET inventory = ?
  8. COMMIT
  9. SELECT (재조회)
```

### 결함 1: Race Condition

서비스 단계 (1~2) 와 repository 의 UPDATE (7) 사이에 **다른 요청의 트랜잭션이 inventory 를 바꿀 수 있다.** 예시 시나리오:

```
T1 (요청 A: -10):  SELECT inventory=10 → 검증 통과 (10 >= 10)
T2 (요청 B: -10):  SELECT inventory=10 → 검증 통과
T1:                UPDATE inventory=0
T2:                UPDATE inventory=-10   ← 음수!
```

### 결함 2: Silent Failure

위 시나리오에서 repository 의 음수 클램프 (`if new_inventory < 0: new_inventory = 0`) 가 트리거되어 **재고가 조용히 0 으로 설정** 된다. 사용자 입장에서는:

- 요청 B 는 **200 OK** 를 받지만
- 실제로는 10 개가 아닌 0 개의 재고만 차감됨
- 차감 받지 못한 차이가 **소리 없이 사라짐**

이는 비즈니스 룰 (`재고 부족 시 거절`) 을 명시적으로 위배하면서 호출자에게 알리지 않는 전형적인 silent failure 다.

---

## 2. 목적

- 동시성 환경에서도 재고 변경이 **원자적** 으로 수행되도록 보장한다.
- 재고 부족은 **반드시 명시적 실패 (400)** 로 응답한다.
- 음수 재고 발생 가능성을 0 으로 만든다.
- repository 의 음수 클램프 (silent failure) 를 제거한다.

### 비목적

- 상품 도메인의 다른 메서드 (CRUD, 카테고리 등) 재검토.
- 재고 이력 (audit log) 추가.
- 다중 노드/분산 락 도입 — SQLite 단일 노드 가정 유지.
- 트랜잭션 격리 수준 전역 변경.

---

## 3. 성공 기준

| 지표                                                            | 목표값                       |
| --------------------------------------------------------------- | ---------------------------- |
| 동시 호출 시나리오 (재고 10, 동시 요청 `-10` 2건)               | 1건 200 / 1건 400 + 음수 재고 0건 |
| `quantity_change` 가 정확히 재고와 같을 때 (10 → 0)             | 200 OK + inventory=0         |
| `abs(quantity_change)` 가 재고 + 1 (10 + `-11`)                 | 400 Bad Request              |
| 음수 클램프 코드 제거                                           | `app/product/repository.py` 에서 해당 라인 삭제 |
| 기존 회귀 테스트                                                | 18/18 PASS 유지              |
| 추가 동시성 테스트 (선택)                                       | 신규 1건 PASS                |

---

## 4. 설계 옵션

| 옵션 | 방식                                            | 장점                                              | 단점                                                              |
| ---- | ----------------------------------------------- | ------------------------------------------------- | ----------------------------------------------------------------- |
| A    | **조건부 단일 UPDATE** (Recommended)            | DB 한 번. 원자적. SQLAlchemy core 로 DB 무관 동작 | 비즈니스 메시지 분기 (상품 없음 vs 재고 부족) 를 위해 후속 SELECT 필요 |
| B    | `SELECT ... FOR UPDATE` (행 잠금)               | 표준 패턴                                         | SQLite + aiosqlite 에서 지원 한계. 다른 DB 로 마이그레이션 시 적합 |
| C    | 트랜잭션 격리 격상 (`SERIALIZABLE`) + 재시도    | DB 중립                                           | 복잡도 증가. 재시도 정책 별도 설계 필요. 성능 영향                |

### 권장: 옵션 A

SQLite + 단일 노드 환경에서 가장 단순하고 안전한 해법.

```sql
-- 의사 SQL
UPDATE products
SET    inventory = inventory + :quantity_change
WHERE  id = :product_id
   AND inventory + :quantity_change >= 0;
```

- 행이 0건 갱신되면 → 상품 없음 또는 재고 부족
- 분기 위해 후속 `SELECT` 한 번 수행

---

## 5. 상세 설계 (옵션 A)

### 5.1 Repository

```python
# app/product/repository.py
from sqlalchemy import select, update

async def update_inventory(
    self, product_id: int, quantity_change: int
) -> Optional[Product]:
    """원자적 재고 변경.

    반환:
        Product   : 성공
        None      : 상품 없음
    예외:
        BusinessLogicException : 재고 부족
    """
    result = await self.session.execute(
        update(ProductModel)
        .where(ProductModel.id == product_id)
        .where(ProductModel.inventory + quantity_change >= 0)
        .values(inventory=ProductModel.inventory + quantity_change)
    )
    await self.session.commit()

    if result.rowcount == 0:
        # 갱신 실패 → 상품 없음 vs 재고 부족 구분 위해 후속 조회
        product = await self.get_by_id(product_id)
        if product is None:
            return None
        # 상품은 있는데 갱신 안 됨 → 재고 부족
        raise BusinessLogicException(
            f"Not enough inventory for product {product_id}"
        )

    # 갱신된 결과 재조회
    return await self.get_by_id(product_id)
```

### 5.2 Service

검증 책임이 DB 로 이동했으므로 서비스는 단순 위임.

```python
# app/product/service.py
async def update_inventory(
    self, product_id: int, quantity_change: int
) -> Product:
    product = await self.product_repository.update_inventory(
        product_id, quantity_change
    )
    if product is None:
        raise NotFoundException(f"Product with ID {product_id} not found")
    return product
```

### 5.3 클린 아키텍처 정합성 검토

`BusinessLogicException` 을 repository 에서 던지는 것이 어색하다는 지적이 있을 수 있다.

**대안: 결과 enum 패턴**

```python
class InventoryUpdateResult(Enum):
    OK = "ok"
    NOT_FOUND = "not_found"
    INSUFFICIENT = "insufficient"

async def update_inventory(...) -> tuple[InventoryUpdateResult, Optional[Product]]:
    ...
```

- 장점: repository 가 도메인 예외를 모름
- 단점: 호출자가 매번 분기 처리 필요, 시그니처 복잡

**결정**: 본 PRD 는 단순성을 우선해 **예외를 repository 에서 던지는 방식** 을 채택한다. 향후 다른 도메인 메서드에서 동일 패턴이 반복되면 enum 으로 리팩토링 검토.

---

## 6. 영향 받는 파일

| 파일                                       | 변경 종류        | 비고                                                                 |
| ------------------------------------------ | ---------------- | -------------------------------------------------------------------- |
| `app/product/repository.py`                | 재작성           | `update_inventory` 메서드. 음수 클램프 제거, 조건부 UPDATE 도입       |
| `app/product/service.py`                   | 단순화           | `update_inventory` 의 SELECT/검증 로직 제거 (검증은 repository 가 담당) |
| `tests/product/test_router.py`             | 케이스 추가      | 동시성 시뮬레이션 1건, 경계 케이스 (정확히 0 됨) 1건                  |
| `docs/diagram/상품_관리_관리자.md`         | 다이어그램 갱신  | `PATCH inventory` 시퀀스 단순화                                       |

> 프로덕션 코드 2개 파일 + 테스트 + 문서. PR 하나에 담을 수 있는 규모.

---

## 7. 테스트 영향

### 7.1 기존 테스트

| 테스트                              | 영향                                                              |
| ----------------------------------- | ----------------------------------------------------------------- |
| `test_update_inventory_as_admin`    | 정상 케이스 — PASS 유지                                            |

### 7.2 추가 권장 케이스

```python
async def test_update_inventory_exact_zero(client, admin_auth_headers, test_product):
    """quantity_change 가 정확히 재고와 같을 때 0으로 만드는 케이스"""
    # test_product.inventory = 10
    response = await client.patch(
        f"/api/v1/products/{test_product['id']}/inventory",
        headers=admin_auth_headers,
        json={"quantity_change": -10},
    )
    assert response.status_code == 200
    assert response.json()["inventory"] == 0


async def test_update_inventory_insufficient(client, admin_auth_headers, test_product):
    """재고보다 많이 차감하려 할 때 400"""
    response = await client.patch(
        f"/api/v1/products/{test_product['id']}/inventory",
        headers=admin_auth_headers,
        json={"quantity_change": -11},
    )
    assert response.status_code == 400


async def test_update_inventory_concurrent(client, admin_auth_headers, test_product):
    """동시 차감 시 정확히 1건만 성공"""
    import asyncio
    # test_product.inventory = 10, 두 요청 모두 -10
    responses = await asyncio.gather(
        client.patch(
            f"/api/v1/products/{test_product['id']}/inventory",
            headers=admin_auth_headers,
            json={"quantity_change": -10},
        ),
        client.patch(
            f"/api/v1/products/{test_product['id']}/inventory",
            headers=admin_auth_headers,
            json={"quantity_change": -10},
        ),
        return_exceptions=False,
    )
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200, 400]
```

> **동시성 테스트 주의**: SQLite + StaticPool 단일 커넥션 환경에서는 실제 병렬 실행이 어려울 수 있다. 본격적 검증은 PostgreSQL 환경 또는 통합 테스트 단에서 수행하는 게 적합. 본 PRD 의 동시성 테스트는 "구조적 정합성" 수준의 회귀 가드로 위치 부여.

---

## 8. 리스크 및 미해결 이슈

| #   | 항목                                                                            | 대응                                                                          |
| --- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 1   | repository 가 `BusinessLogicException` 을 던지는 것의 아키텍처 적합성             | 단순성 우선으로 채택. 패턴 반복 시 enum 결과 패턴으로 리팩토링 검토             |
| 2   | SQLite + aiosqlite 환경에서 조건부 UPDATE 의 동시성 보장 수준                   | SQLite 는 기본적으로 DB 단위 잠금 → 단일 UPDATE 는 원자적. PostgreSQL 등에서는 행 단위 락으로 충분 |
| 3   | `inventory + quantity_change >= 0` 표현식이 SQLAlchemy 2.0 모든 dialect 에서 동일 동작 | SQLAlchemy core 로 작성하므로 안전. 다만 PR 검증 단계에서 echo 로 SQL 확인 권장 |
| 4   | 테스트의 동시성 시뮬레이션이 실제 race 를 재현하지 못할 수 있음                  | 본 PRD 의 동시성 테스트는 구조적 가드. 실 운영 검증은 부하 테스트로 별도 수행 |

---

## 9. 참고

- 관련 시퀀스 다이어그램: [`docs/diagram/상품_관리_관리자.md`](./diagram/상품_관리_관리자.md) (재고 변경 섹션)
- 예외 정의: `app/core/exceptions.py` (`NotFoundException`, `BusinessLogicException`)
- 코드 위치:
  - `app/product/service.py:73`
  - `app/product/repository.py:108`
- SQLAlchemy 2.0 UPDATE: https://docs.sqlalchemy.org/en/20/tutorial/data_update.html
