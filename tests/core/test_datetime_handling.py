"""모델의 datetime 필드가 timezone-aware UTC 로 동작하는지 검증.

note: SQLite + aiosqlite 환경에서는 INSERT/SELECT 사이클에서 timezone 정보가
유실된다. 따라서 DB 왕복을 거친 datetime 의 tzinfo 가 None 인 것은 SQLite 한계이며,
PostgreSQL 등 DateTime(timezone=True) 를 네이티브 지원하는 DB 로 이전 시 자동으로
aware 가 보존된다. 본 테스트는 Python 단 (default_factory 호출 결과) 에서의
timezone-aware 동작과, DB 왕복 후의 datetime 정합성 (값 자체) 을 검증한다.
"""

import asyncio
from datetime import UTC, datetime

import pytest

from app.user.models import UserModel


def test_default_factory_returns_timezone_aware():
    """모델 인스턴스화 시점에 default_factory 가 timezone-aware UTC 를 반환한다.

    DB 왕복 전 단계 검증 — Python 단에서 datetime.utcnow() deprecation 이
    완전히 해소되었음을 보장.
    """
    user = UserModel(
        email="aware@example.com",
        username="aware",
        hashed_password="h",
        is_active=True,
    )

    assert user.created_at.tzinfo is not None
    assert user.created_at.utcoffset() == datetime.now(UTC).utcoffset()
    assert user.updated_at.tzinfo is not None
    assert user.updated_at.utcoffset() == datetime.now(UTC).utcoffset()


@pytest.mark.asyncio
async def test_user_updated_at_changes_on_update(db_session):
    """UserModel.updated_at 이 UPDATE 시점에 자동 갱신된다.

    SQLite 환경에서는 DB 왕복 시 tzinfo 가 유실되므로 본 테스트는 값 자체의
    변화 (시간 증가) 만 검증한다. timezone-aware 보장은 위 테스트에서 별도 검증.
    """
    user = UserModel(
        email="upd@example.com",
        username="upduser",
        hashed_password="h",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    initial_updated = user.updated_at

    # SQLite 의 datetime precision 한계로 짧은 sleep
    await asyncio.sleep(0.01)

    user.username = "upduser_renamed"
    await db_session.commit()
    await db_session.refresh(user)

    assert user.updated_at > initial_updated
