# app/core/database.py

"""
데이터베이스 연결 및 세션 관리를 위한 모듈.
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base

from app.di.containers import Container

# Base 모델 정의
Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 의존성 주입을 위한 데이터베이스 세션 제공자.
    Container에서 관리하는 async_scoped_session을 사용합니다.
    """
    session = Container.db()
    try:
        yield session
    finally:
        # Resource provider가 세션 제거를 관리하므로 여기서는 아무것도 하지 않음
        pass

async def create_db_and_tables() -> None:
    """
    데이터베이스와 테이블 생성 (개발/테스트 환경에서만 사용).
    """
    from sqlmodel import SQLModel  # SQLModel 임포트

    engine = Container.engine()
    async with engine.begin() as conn:
        # SQLModel과 SQLAlchemy 모델을 함께 처리
        await conn.run_sync(SQLModel.metadata.create_all)