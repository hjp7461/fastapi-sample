# tests/conftest.py (새 버전)
import asyncio
from typing import Dict, Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# 테스트 HTTP 클라이언트
import pytest_asyncio
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import Base
from app.main import app as fastapi_app
from app.user.models import UserModel
from app.product.models import ProductModel

# 테스트 DB URL
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


# 엔진 생성
@pytest_asyncio.fixture(scope="session")
async def engine():
    # 테스트 엔진 생성
    test_engine = create_async_engine(
        TEST_DB_URL,
        echo=True,  # SQL 출력을 보려면 True로 설정
        future=True
    )

    # 테이블 생성
    from app.user.models import UserModel
    from app.product.models import ProductModel
    from app.core.database import Base
    from sqlmodel import SQLModel

    async with test_engine.begin() as conn:
        # SQLAlchemy 및 SQLModel 테이블 생성
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(SQLModel.metadata.create_all)

    yield test_engine

    # 테스트 후 정리
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# DB 설정 및 생성
@pytest_asyncio.fixture(scope="session")
async def setup_db(engine):
    # 모든 관련 모델을 임포트
    from app.user.models import UserModel
    from app.product.models import ProductModel
    from app.core.database import Base
    from sqlmodel import SQLModel

    # 기존 테이블 삭제 (필요한 경우)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    # 모든 테이블 생성
    async with engine.begin() as conn:
        # SQLAlchemy 모델
        await conn.run_sync(Base.metadata.create_all)
        # SQLModel 모델 (사용하는 경우)
        await conn.run_sync(SQLModel.metadata.create_all)

    yield

    # 테스트 후 테이블 정리 (선택사항)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# 세션 팩토리
@pytest.fixture(scope="session")
def session_factory(engine):
    return sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False
    )


# 테스트 DB 세션
@pytest.fixture
async def db_session(setup_db, session_factory):
    async with session_factory() as session:
        yield session


# 테스트 FastAPI 앱
@pytest.fixture
def app():
    return fastapi_app


@pytest_asyncio.fixture
async def client(app):
    # 먼저 동기식 TestClient 생성
    test_client = TestClient(app)

    # 그런 다음 AsyncClient 생성 (app 매개변수 없이)
    async with AsyncClient(base_url="http://127.0.0.1:8000 ") as ac:
        # 요청을 FastAPI 애플리케이션으로 라우팅
        app.dependency_overrides = {}  # 의존성 초기화
        yield ac


# 테스트 사용자
@pytest.fixture
async def test_user(db_session):
    from app.core.security import get_password_hash

    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword"
    }

    db_user = UserModel(
        username=user_data["username"],
        email=user_data["email"],
        hashed_password=get_password_hash(user_data["password"]),
        is_active=True
    )

    db_session.add(db_user)
    await db_session.commit()
    await db_session.refresh(db_user)

    # 딕셔너리 직접 반환
    return {
        "id": db_user.id,
        "username": user_data["username"],
        "email": user_data["email"],
        "password": user_data["password"]
    }


# 테스트 관리자
@pytest.fixture
async def admin_user(db_session):
    from app.core.security import get_password_hash

    user_data = {
        "username": "adminuser",
        "email": "admin@example.com",
        "password": "adminpassword",
        "role": "admin"
    }

    db_user = UserModel(
        username=user_data["username"],
        email=user_data["email"],
        hashed_password=get_password_hash(user_data["password"]),
        is_active=True,
        role=user_data["role"]
    )

    db_session.add(db_user)
    await db_session.commit()
    await db_session.refresh(db_user)

    return {
        "id": db_user.id,
        "username": user_data["username"],
        "email": user_data["email"],
        "password": user_data["password"]
    }


# 테스트 인증 헤더
@pytest.fixture
async def auth_headers(client, test_user):
    login_data = {
        "username": test_user["email"],
        "password": test_user["password"]
    }

    response = await client.post("/api/v1/users/token", data=login_data)
    token = response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


# 관리자 인증 헤더
@pytest.fixture
async def admin_auth_headers(client, admin_user):
    login_data = {
        "username": admin_user["email"],
        "password": admin_user["password"]
    }

    response = await client.post("/api/v1/users/token", data=login_data)
    token = response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


# 테스트 상품
@pytest.fixture
async def test_product(db_session):
    from decimal import Decimal

    product_data = {
        "name": "Test Product",
        "description": "Test product description",
        "price": Decimal("99.99"),
        "inventory": 10,
        "is_active": True
    }

    db_product = ProductModel(**product_data)

    db_session.add(db_product)
    await db_session.commit()
    await db_session.refresh(db_product)

    return {
        "id": db_product.id,
        "name": product_data["name"],
        "description": product_data["description"],
        "price": product_data["price"]
    }