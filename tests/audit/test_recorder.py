"""audit recorder 인프라 회귀 가드.

본 테스트는 **인프라만** 검증 — 도메인 hook (auth/user/product) 통합 회귀는
별도 PR 의 PLAN 에서 추가.

회귀 가드 매트릭스 (PRD §4-4 의 인프라 부분):
1. record_audit() 가 audit_logs 에 row 1건 INSERT
2. request_id contextvar 자동 첨부
3. user_id contextvar 자동 첨부 (anonymous 시 NULL)
4. PII redact (event_metadata 의 email → [REDACTED])
5. AUDIT_ENABLED=false 시 no-op (row 0건)
"""

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLogModel
from app.audit.recorder import record_audit
from app.core.context import request_id_var, user_id_var


async def _count_audit(session: AsyncSession) -> int:
    result = await session.execute(select(AuditLogModel))
    return len(result.scalars().all())


async def _fetch_one(session: AsyncSession) -> AuditLogModel:
    result = await session.execute(select(AuditLogModel))
    rows = result.scalars().all()
    assert len(rows) == 1, f"expected exactly 1 row, got {len(rows)}"
    return rows[0]


@pytest.fixture
def reset_contextvars() -> Iterator[None]:
    """각 테스트 후 contextvar 회수 — task-scoped 자동 회수 보강.

    sync fixture (await 불필요) — pytest 가 generator fixture 로 정상 처리.
    """
    request_id_var.set("-")
    user_id_var.set(None)
    yield
    request_id_var.set("-")
    user_id_var.set(None)


@pytest.mark.asyncio
async def test_record_audit_inserts_single_row(
    db_session: AsyncSession, reset_contextvars: None
) -> None:
    """record_audit() 가 audit_logs 에 row 1건 INSERT."""
    assert await _count_audit(db_session) == 0
    await record_audit(
        db_session,
        action="test.action",
        outcome="success",
        target_type="test",
        target_id=42,
    )
    await db_session.commit()

    row = await _fetch_one(db_session)
    assert row.action == "test.action"
    assert row.outcome == "success"
    assert row.target_type == "test"
    assert row.target_id == 42


@pytest.mark.asyncio
async def test_record_audit_attaches_request_id_from_contextvar(
    db_session: AsyncSession, reset_contextvars: None
) -> None:
    """request_id contextvar 자동 첨부 — PR #32 패턴 재사용."""
    request_id_var.set("test-rid-abc123")
    await record_audit(db_session, action="test.rid", outcome="success")
    await db_session.commit()

    row = await _fetch_one(db_session)
    assert row.request_id == "test-rid-abc123"


@pytest.mark.asyncio
async def test_record_audit_request_id_dash_normalized_to_null(
    db_session: AsyncSession, reset_contextvars: None
) -> None:
    """request_id 가 default '-' 인 경우 NULL 저장 — anonymous 컨텍스트.

    PR #32 의 default '-' placeholder 가 audit row 에 그대로 저장되면 쿼리
    표면 노이즈 (`WHERE request_id != '-'` 패턴 강요). NULL 로 정규화.
    """
    request_id_var.set("-")
    await record_audit(db_session, action="test.no.rid", outcome="success")
    await db_session.commit()

    row = await _fetch_one(db_session)
    assert row.request_id is None


@pytest.mark.asyncio
async def test_record_audit_attaches_user_id_from_contextvar(
    db_session: AsyncSession, test_user: dict[str, Any], reset_contextvars: None
) -> None:
    """user_id contextvar 자동 첨부 → actor_id — PR #73 패턴 재사용."""
    user_id_var.set(test_user["id"])
    await record_audit(db_session, action="test.actor", outcome="success")
    await db_session.commit()

    row = await _fetch_one(db_session)
    assert row.actor_id == test_user["id"]


@pytest.mark.asyncio
async def test_record_audit_anonymous_actor_id_is_null(
    db_session: AsyncSession, reset_contextvars: None
) -> None:
    """anonymous (user_id contextvar 미설정) 시 actor_id NULL."""
    user_id_var.set(None)
    await record_audit(db_session, action="test.anon", outcome="success")
    await db_session.commit()

    row = await _fetch_one(db_session)
    assert row.actor_id is None


@pytest.mark.asyncio
async def test_record_audit_redacts_pii_in_metadata(
    db_session: AsyncSession, reset_contextvars: None
) -> None:
    """event_metadata 의 PII 키 (email/first_name/...) → [REDACTED].

    PR #71 의 `_redact_pii` 재사용 단일 진실원. `_PII_KEYS` frozenset 갱신
    시 audit 도 자동 회복.
    """
    await record_audit(
        db_session,
        action="user.update",
        outcome="success",
        event_metadata={
            "email": "user@example.com",
            "first_name": "Alice",
            "non_pii_field": "kept",
        },
    )
    await db_session.commit()

    row = await _fetch_one(db_session)
    assert row.event_metadata == {
        "email": "[REDACTED]",
        "first_name": "[REDACTED]",
        "non_pii_field": "kept",
    }


@pytest.mark.asyncio
async def test_record_audit_disabled_is_noop(
    db_session: AsyncSession,
    reset_contextvars: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUDIT_ENABLED=false → record_audit() 가 즉시 return (row 0건)."""
    from app.core import config

    monkeypatch.setattr(config.settings, "AUDIT_ENABLED", False)
    await record_audit(db_session, action="test.disabled", outcome="success")
    await db_session.commit()

    assert await _count_audit(db_session) == 0
