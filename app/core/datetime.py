"""시간 관련 공통 헬퍼.

`utcnow_aware()` 는 timezone-aware UTC 현재 시각을 반환한다.
SQLModel / SQLAlchemy 의 `default_factory` / `default` / `onupdate`
콜러블로 직접 전달하기 위해 인자를 받지 않는다.
"""

from datetime import UTC, datetime


def utcnow_aware() -> datetime:
    return datetime.now(UTC)
