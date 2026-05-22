"""암호화 유틸리티 회귀 가드.

특히 passlib 시절에 생성된 해시의 호환성을 보장한다.
"""
import bcrypt

from app.core.config import settings
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


def test_get_password_hash_uses_configured_rounds():
    """get_password_hash 가 settings.BCRYPT_ROUNDS 를 사용한다."""
    hashed = get_password_hash("test_password")
    # bcrypt 해시 형식: $2b$<rounds>$<salt+hash>
    parts = hashed.split("$")
    actual_rounds = int(parts[2])
    assert actual_rounds == settings.BCRYPT_ROUNDS


def test_verify_works_across_different_rounds():
    """라운드가 다른 두 해시를 동일 verify 함수로 검증 가능 (호환성).

    라운드 업그레이드 시 기존 해시 (낮은 라운드) 가 새 settings 와 무관하게
    검증되어야 한다.
    """
    plain = "samePassword"

    # 명시적으로 다른 라운드로 해시
    low_round_hash = bcrypt.hashpw(
        plain.encode("utf-8"), bcrypt.gensalt(rounds=10)
    ).decode("utf-8")
    default_round_hash = get_password_hash(plain)

    assert verify_password(plain, low_round_hash) is True
    assert verify_password(plain, default_round_hash) is True
    assert verify_password("wrong", low_round_hash) is False
    assert verify_password("wrong", default_round_hash) is False
