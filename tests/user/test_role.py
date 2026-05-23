"""UserRole / User 도메인 권한 메서드 회귀 가드.

권한 계층 (CUSTOMER ⊂ STAFF ⊂ ADMIN) 의 의도가 코드에 정확히 표현되어 있는지 검증.
"""

from datetime import datetime

from app.user.domain import User, UserRole


def _user_with(role: UserRole) -> User:
    """role 만 다르게 한 User 인스턴스 — DB save 후 상태 (id/timestamps 필수)."""
    return User(
        id=1,
        email="t@example.com",
        username="t",
        role=role,
        is_active=True,
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1),
    )


def test_user_is_admin():
    """is_admin 은 ADMIN 만 True."""
    assert _user_with(UserRole.ADMIN).is_admin() is True
    assert _user_with(UserRole.STAFF).is_admin() is False
    assert _user_with(UserRole.CUSTOMER).is_admin() is False


def test_user_is_staff_or_above():
    """is_staff_or_above 는 ADMIN, STAFF 둘 다 True (계층 의도: STAFF ⊂ ADMIN)."""
    assert _user_with(UserRole.ADMIN).is_staff_or_above() is True
    assert _user_with(UserRole.STAFF).is_staff_or_above() is True
    assert _user_with(UserRole.CUSTOMER).is_staff_or_above() is False


def test_can_manage_products_delegates_to_staff_or_above():
    """can_manage_products 는 is_staff_or_above 와 동일한 결과를 반환 (위임)."""
    for role in UserRole:
        user = _user_with(role)
        assert user.can_manage_products() == user.is_staff_or_above()
