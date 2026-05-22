"""Alembic 마이그레이션 ↔ SQLModel 메타데이터 정합성 회귀.

테스트 환경의 기본 격리 (인메모리 + StaticPool) 와는 분리된 가드. 매번 새
tmp_path SQLite 파일을 생성해 `alembic upgrade head` / `alembic downgrade base`
를 직접 호출하여 생성/제거 동작이 깨지지 않는지 확인한다.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[2]


def _make_alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


def test_alembic_upgrade_creates_expected_tables(tmp_path: Path):
    """`alembic upgrade head` 후 users/products/alembic_version 테이블 생성."""
    db_path = tmp_path / "alembic_upgrade.db"
    async_url = f"sqlite+aiosqlite:///{db_path}"
    cfg = _make_alembic_config(async_url)

    command.upgrade(cfg, "head")

    sync_engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(sync_engine)
    tables = set(insp.get_table_names())
    sync_engine.dispose()

    assert "users" in tables
    assert "products" in tables
    assert "alembic_version" in tables


def test_alembic_downgrade_removes_tables(tmp_path: Path):
    """`alembic downgrade base` 후 users/products 테이블 제거.

    alembic_version 메타 테이블은 alembic 표준상 남을 수 있으므로 검증하지 않는다.
    """
    db_path = tmp_path / "alembic_downgrade.db"
    async_url = f"sqlite+aiosqlite:///{db_path}"
    cfg = _make_alembic_config(async_url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    sync_engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(sync_engine)
    tables = set(insp.get_table_names())
    sync_engine.dispose()

    assert "users" not in tables
    assert "products" not in tables
