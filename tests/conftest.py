"""테스트 공통 픽스처.

- StaticPool 기반 인메모리 SQLite로 격리
- dependency_injector Container의 engine/session_factory를 테스트용으로 override
- 비동기 경로(`async`)는 그대로 유지
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from dependency_injector import providers
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.di.containers import Container
from app.main import app as fastapi_app
from app.product.models import ProductModel
from app.user.domain import UserRole
from app.user.models import UserModel

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """단일 커넥션 인메모리 SQLite. StaticPool로 다중 세션이 동일 DB를 공유."""
    test_engine = create_async_engine(
        TEST_DB_URL,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=False,
        future=True,
    )

    from sqlmodel import SQLModel

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(SQLModel.metadata.create_all)

    yield test_engine

    await test_engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """테스트 엔진에 바인딩된 AsyncSession 팩토리."""
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture(autouse=True)
async def container_override(
    engine: AsyncEngine, session_factory: async_sessionmaker[AsyncSession]
) -> AsyncIterator[None]:
    """Container.engine / session_factory를 테스트용으로 교체.

    teardown에서 scoped_session 정리 + override 원복.
    """
    Container.engine.override(providers.Singleton(lambda: engine))
    Container.session_factory.override(providers.Factory(lambda: session_factory))
    # Singleton 캐시 무효화 (사전 호출로 인한 잔존 인스턴스 제거)
    Container.engine.reset()

    yield

    if Container.db.initialized:
        scoped = Container.db()
        await scoped.remove()
        Container.db.shutdown()

    Container.engine.reset_override()
    Container.session_factory.reset_override()
    Container.engine.reset()


@pytest_asyncio.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """시드 데이터 작성용 세션."""
    async with session_factory() as session:
        yield session


@pytest.fixture
def app() -> FastAPI:
    return fastapi_app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """ASGI 트랜스포트로 직접 라우팅되는 비동기 HTTP 클라이언트."""
    app.dependency_overrides = {}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> dict[str, Any]:
    from app.core.security import get_password_hash

    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword",
    }
    db_user = UserModel(
        username=user_data["username"],
        email=user_data["email"],
        hashed_password=get_password_hash(user_data["password"]),
        is_active=True,
    )
    db_session.add(db_user)
    await db_session.commit()
    await db_session.refresh(db_user)

    return {
        "id": db_user.id,
        "username": user_data["username"],
        "email": user_data["email"],
        "password": user_data["password"],
    }


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> dict[str, Any]:
    from app.core.security import get_password_hash

    user_data = {
        "username": "adminuser",
        "email": "admin@example.com",
        "password": "adminpassword",
        "role": UserRole.ADMIN.value,
    }
    db_user = UserModel(
        username=user_data["username"],
        email=user_data["email"],
        hashed_password=get_password_hash(user_data["password"]),
        is_active=True,
        role=UserRole.ADMIN,
    )
    db_session.add(db_user)
    await db_session.commit()
    await db_session.refresh(db_user)

    return {
        "id": db_user.id,
        "username": user_data["username"],
        "email": user_data["email"],
        "password": user_data["password"],
    }


@pytest_asyncio.fixture
async def staff_user(db_session: AsyncSession) -> dict[str, Any]:
    from app.core.security import get_password_hash

    user_data = {
        "username": "staffuser",
        "email": "staff@example.com",
        "password": "staffpassword",
        "role": UserRole.STAFF.value,
    }
    db_user = UserModel(
        username=user_data["username"],
        email=user_data["email"],
        hashed_password=get_password_hash(user_data["password"]),
        is_active=True,
        role=UserRole.STAFF,
    )
    db_session.add(db_user)
    await db_session.commit()
    await db_session.refresh(db_user)

    return {
        "id": db_user.id,
        "username": user_data["username"],
        "email": user_data["email"],
        "password": user_data["password"],
    }


@pytest_asyncio.fixture
async def auth_headers(
    client: AsyncClient, test_user: dict[str, Any]
) -> dict[str, str]:
    login_data = {"username": test_user["email"], "password": test_user["password"]}
    response = await client.post("/api/v1/users/token", data=login_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_auth_headers(
    client: AsyncClient, admin_user: dict[str, Any]
) -> dict[str, str]:
    login_data = {"username": admin_user["email"], "password": admin_user["password"]}
    response = await client.post("/api/v1/users/token", data=login_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def staff_auth_headers(
    client: AsyncClient, staff_user: dict[str, Any]
) -> dict[str, str]:
    login_data = {"username": staff_user["email"], "password": staff_user["password"]}
    response = await client.post("/api/v1/users/token", data=login_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_product(db_session: AsyncSession) -> dict[str, Any]:
    from decimal import Decimal

    product_data = {
        "name": "Test Product",
        "description": "Test product description",
        "price": Decimal("99.99"),
        "inventory": 10,
        "is_active": True,
    }
    db_product = ProductModel(**product_data)
    db_session.add(db_product)
    await db_session.commit()
    await db_session.refresh(db_product)

    return {
        "id": db_product.id,
        "name": product_data["name"],
        "description": product_data["description"],
        "price": product_data["price"],
    }
