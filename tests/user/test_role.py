"""UserRole / User 도메인 권한 메서드 회귀 가드.

권한 계층 (CUSTOMER ⊂ STAFF ⊂ ADMIN) 의 의도가 코드에 정확히 표현되어 있는지 검증.
"""
from app.user.domain import User, UserRole


def test_user_is_admin():
    """is_admin 은 ADMIN 만 True."""
    assert User(role=UserRole.ADMIN).is_admin() is True
    assert User(role=UserRole.STAFF).is_admin() is False
    assert User(role=UserRole.CUSTOMER).is_admin() is False


def test_user_is_staff_or_above():
    """is_staff_or_above 는 ADMIN, STAFF 둘 다 True (계층 의도: STAFF ⊂ ADMIN)."""
    assert User(role=UserRole.ADMIN).is_staff_or_above() is True
    assert User(role=UserRole.STAFF).is_staff_or_above() is True
    assert User(role=UserRole.CUSTOMER).is_staff_or_above() is False


def test_can_manage_products_delegates_to_staff_or_above():
    """can_manage_products 는 is_staff_or_above 와 동일한 결과를 반환 (위임)."""
    for role in UserRole:
        user = User(role=role)
        assert user.can_manage_products() == user.is_staff_or_above()
