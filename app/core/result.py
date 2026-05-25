"""repository CRUD outcome 패턴 (PR #56).

도메인 예외 의존 없이 outcome enum 으로 결과를 표현 — service 가 변환 책임.
PR #16 의 `InventoryUpdateResult` 패턴을 다른 CRUD 메서드로 확장.

특수 케이스 `update_inventory` 는 3-state (OK/NOT_FOUND/INSUFFICIENT) 라
별도 `InventoryUpdateResult` 유지 (`app/product/repository.py`).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

T = TypeVar("T")


class CrudOutcome(Enum):
    """공통 CRUD outcome (get/update/delete) — 2-state."""

    OK = "ok"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class CrudResult(Generic[T]):
    """outcome + value (OK 일 때만 value 보장).

    delete 처럼 value 가 의미 없는 케이스는 `T=None`, value=None.
    """

    outcome: CrudOutcome
    value: T | None = None
