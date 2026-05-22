"""테스트 공통 픽스처.

- StaticPool 기반 인메모리 SQLite로 격리
- dependency_injector Container의 engine/session_factory를 테스트용으로 override
- 비동기 경로(`async`)는 그대로 유지
"""
import pytest
import pytest_asyncio
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.di.containers import Container
from app.main import app as fastapi_app
from app.product.models import ProductModel
from app.user.models import UserModel

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
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
def session_factory(engine):
    """테스트 엔진에 바인딩된 AsyncSession 팩토리."""
    return sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture(autouse=True)
async def container_override(engine, session_factory):
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
async def db_session(session_factory):
    """시드 데이터 작성용 세션."""
    async with session_factory() as session:
        yield session


@pytest.fixture
def app():
    return fastapi_app


@pytest_asyncio.fixture
async def client(app):
    """ASGI 트랜스포트로 직접 라우팅되는 비동기 HTTP 클라이언트."""
    app.dependency_overrides = {}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(db_session):
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
async def admin_user(db_session):
    from app.core.security import get_password_hash

    user_data = {
        "username": "adminuser",
        "email": "admin@example.com",
        "password": "adminpassword",
        "role": "admin",
    }
    db_user = UserModel(
        username=user_data["username"],
        email=user_data["email"],
        hashed_password=get_password_hash(user_data["password"]),
        is_active=True,
        role=user_data["role"],
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
async def auth_headers(client, test_user):
    login_data = {"username": test_user["email"], "password": test_user["password"]}
    response = await client.post("/api/v1/users/token", data=login_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_auth_headers(client, admin_user):
    login_data = {"username": admin_user["email"], "password": admin_user["password"]}
    response = await client.post("/api/v1/users/token", data=login_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_product(db_session):
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
