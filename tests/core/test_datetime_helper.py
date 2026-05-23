"""`utcnow_aware()` 헬퍼 단위 테스트."""

from datetime import UTC, datetime

from app.core.datetime import utcnow_aware


def test_utcnow_aware_is_timezone_aware():
    """헬퍼는 timezone-aware UTC datetime 을 반환한다."""
    now = utcnow_aware()

    assert now.tzinfo is not None
    assert now.utcoffset() == datetime.now(UTC).utcoffset()


def test_utcnow_aware_is_callable_default_factory():
    """SQLModel `default_factory` 와 호환되는 인자 0 콜러블이다."""
    factory = utcnow_aware

    result = factory()

    assert isinstance(result, datetime)
    assert result.tzinfo is not None
