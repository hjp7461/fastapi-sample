# app/core/database.py

"""
데이터베이스 연결 및 세션 관리를 위한 모듈.

스키마 생성/변경은 alembic 으로 관리한다 (`uv run alembic upgrade head`).
"""

from typing import AsyncGenerator, cast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base

from app.di.containers import Container

# Base 모델 정의
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 의존성 주입을 위한 데이터베이스 세션 제공자.
    Container에서 관리하는 async_scoped_session을 사용합니다.
    `async_scoped_session` 은 AsyncSession 인터페이스 proxy 라 cast 안전.
    """
    session = cast(AsyncSession, Container.db())
    try:
        yield session
    finally:
        # Resource provider가 세션 제거를 관리하므로 여기서는 아무것도 하지 않음
        pass
