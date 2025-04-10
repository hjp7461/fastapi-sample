"""
사용자 도메인 엔티티 및 값 객체 정의.
핵심 비즈니스 로직과 규칙을 포함합니다.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, List


class UserRole(str, Enum):
    ADMIN = "admin"
    STAFF = "staff"
    CUSTOMER = "customer"


@dataclass
class User:
    """사용자 도메인 엔티티."""
    id: Optional[int] = None
    email: str = ""
    username: str = ""
    hashed_password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: UserRole = UserRole.CUSTOMER
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def full_name(self) -> str:
        """사용자의 전체 이름을 반환합니다."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username

    def can_manage_products(self) -> bool:
        """사용자가 상품을 관리할 수 있는지 확인합니다."""
        return self.role in (UserRole.ADMIN, UserRole.STAFF)