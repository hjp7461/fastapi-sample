"""
사용자 도메인 엔티티 및 값 객체 정의.
핵심 비즈니스 로직과 규칙을 포함합니다.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    STAFF = "staff"
    CUSTOMER = "customer"


@dataclass
class NewUser:
    """신규 사용자 생성용 도메인 객체 — DB save 이전 상태.

    id/created_at/updated_at 가 없음. service 가 입력 데이터를 정리하여 만들고
    repository.create() 에 전달. 저장 후 `User` 로 반환된다.
    """

    email: str
    username: str
    hashed_password: str
    first_name: str | None = None
    last_name: str | None = None
    role: UserRole = UserRole.CUSTOMER
    is_active: bool = True


@dataclass
class User:
    """사용자 도메인 엔티티 — DB save 이후 상태.

    id/created_at/updated_at 가 항상 not None (저장된 사용자 표현). 신규
    생성은 `NewUser` 사용 후 `repository.create()` 호출 — 본 dataclass 의
    default 값으로 객체를 만들지 말 것.

    `hashed_password` 는 OAuth/외부 로그인 시나리오에서 None 가능 → Optional 유지.
    `first_name`/`last_name` 은 실제 미입력 가능 → Optional 유지.
    """

    id: int
    email: str
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
    hashed_password: str | None = None
    first_name: str | None = None
    last_name: str | None = None

    @property
    def full_name(self) -> str:
        """사용자의 전체 이름을 반환합니다."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username

    def is_admin(self) -> bool:
        """ADMIN 전용 권한 보유 여부."""
        return self.role == UserRole.ADMIN

    def is_staff_or_above(self) -> bool:
        """STAFF 이상 권한 보유 여부 (권한 계층: STAFF ⊂ ADMIN)."""
        return self.role in (UserRole.STAFF, UserRole.ADMIN)

    def can_manage_products(self) -> bool:
        """상품 관리 권한. STAFF 이상이면 가능."""
        return self.is_staff_or_above()
