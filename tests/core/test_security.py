"""암호화 유틸리티 회귀 가드.

특히 passlib 시절에 생성된 해시의 호환성을 보장한다.
"""
from app.core.security import get_password_hash, verify_password


# passlib 1.7.4 + bcrypt 가 생성한 실제 해시 (마이그레이션 PR 시점에 박제).
# 이 해시들은 새 구현 (bcrypt 직접 사용) 으로도 동일하게 verify 되어야 한다.
LEGACY_HASH_TEST = "$2b$12$MJgQCEdQ2DFJ9WuWxNgvzeJlnhERQgfRZP8iWBSy/EYJmveWdxJWa"
# 평문: "TestPassword123"

LEGACY_HASH_ADMIN = "$2b$12$K2aYU8NmZR1xwybLA9UGXeeWIHaYjt/NTDeiPkuOQTq/yVhUhk8X2"
# 평문: "admin12345"


def test_hash_then_verify_roundtrip():
    """새 구현의 hash → verify 라운드트립."""
    plain = "MySecurePassword123!"
    hashed = get_password_hash(plain)

    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_verify_legacy_passlib_hash():
    """passlib 시절 생성된 해시도 새 구현으로 verify 가능해야 한다.

    호환성 보장: 기존 DB 의 사용자 비밀번호 (passlib 시절 생성) 가
    마이그레이션 없이 그대로 검증되어야 한다.
    """
    assert verify_password("TestPassword123", LEGACY_HASH_TEST) is True
    assert verify_password("wrong_password", LEGACY_HASH_TEST) is False

    assert verify_password("admin12345", LEGACY_HASH_ADMIN) is True
    assert verify_password("admin54321", LEGACY_HASH_ADMIN) is False


def test_verify_handles_malformed_hash():
    """잘못된 형식의 해시는 False 를 반환 (예외 X)."""
    assert verify_password("password", "not-a-bcrypt-hash") is False
    assert verify_password("password", "") is False
    assert verify_password("password", "$2b$short") is False
