# app/di/containers.py

import asyncio

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_scoped_session,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.product.repository import ProductRepository
from app.product.service import ProductService
from app.user.repository import UserRepository
from app.user.service import UserService


class Container(containers.DeclarativeContainer):
    """
    의존성 주입 컨테이너.
    Resource Provider를 사용하여 async_scoped_session을 관리합니다.
    """

    # 설정
    wiring_config = containers.WiringConfiguration(
        packages=["app.api", "app.user", "app.product"]
    )

    # 데이터베이스 엔진 설정
    engine = providers.Singleton(
        create_async_engine,
        settings.DATABASE_URL,
        echo=settings.DB_ECHO,
        future=True,
        pool_pre_ping=True,
    )

    # 세션 팩토리 설정
    session_factory = providers.Factory(
        sessionmaker,
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    # async_scoped_session을 Resource로 등록
    db = providers.Resource(
        async_scoped_session, session_factory, scopefunc=asyncio.current_task
    )

    # 레포지토리
    user_repository = providers.Factory(UserRepository, session=db)

    product_repository = providers.Factory(ProductRepository, session=db)

    # 서비스
    user_service = providers.Factory(UserService, user_repository=user_repository)

    product_service = providers.Factory(
        ProductService, product_repository=product_repository
    )
