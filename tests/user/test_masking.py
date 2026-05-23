"""`mask_email` 단위 테스트."""

from app.user.masking import mask_email


def test_mask_email_basic():
    """정상 이메일은 로컬 첫 글자 + 호스트 첫 글자 + TLD 유지."""
    assert mask_email("alice@example.com") == "a***@e***.com"
    assert mask_email("a@x.com") == "a***@x***.com"


def test_mask_email_malformed():
    """비정상 입력은 보수적으로 *** 반환 (예외 X)."""
    assert mask_email("") == "***"
    assert mask_email("no-at-sign") == "***"
    assert mask_email("no-tld@host") == "***"


def test_mask_email_empty_local():
    """로컬 파트가 비어있어도 예외 없이 보수적 마스킹."""
    result = mask_email("@example.com")
    assert result.startswith("***")
    assert "@e***.com" in result
