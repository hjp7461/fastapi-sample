"""Alembic env.py — async-friendly + settings 기반 URL.

target_metadata 는 SQLModel.metadata 를 사용한다. 모델 import 가 SQLModel 의
metadata 에 테이블을 등록하는 사이드 이펙트를 가지므로, 명시적으로 두 모델
모듈을 import 한다 (linter F401 무시).
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from alembic import context
from app.core.config import settings
from app.product import models as _product_models  # noqa: F401 — 메타데이터 등록
from app.user import models as _user_models  # noqa: F401 — 메타데이터 등록

config = context.config

# 단일 진실원: app.core.config.settings.DATABASE_URL
# alembic.ini 의 sqlalchemy.url 이 비어있으면 settings 로 채우고,
# 외부 (테스트 등) 에서 cfg.set_main_option 으로 명시 설정했으면 그것이 우선된다.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """offline 모드: URL 만으로 SQL 스크립트 생성."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """async 엔진으로 마이그레이션 실행."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
