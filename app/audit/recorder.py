"""audit event 기록 entry point.

`record_audit()` 가 단일 호출처 — 도메인 service 가 본 함수만 호출.
호출자가 자신의 트랜잭션 세션을 넘기고, commit 은 호출자 책임 (PRD §5.3
동기 정합성 — 본 작업 commit 시 audit 도 함께 영속, 본 작업 롤백 시 audit
도 함께 롤백).

PR #71 의 `_redact_pii` 재사용 (단일 진실원) — `_PII_KEYS` frozenset 갱신
시 audit 도 자동 회복.

PR #32 / #73 의 contextvar (request_id / user_id) 자동 첨부 — 명시적 인자
없으면 contextvar 에서 읽음.
"""

from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLogModel
from app.core.config import settings
from app.core.context import get_request_id, get_user_id
from app.core.observability import _redact_pii

# PRD §5.4 outcome — Literal 타입으로 호출처 타입 검증 (DB 는 VARCHAR 자유).
AuditOutcome = Literal["success", "failure", "denied"]
ActorRole = Literal["admin", "staff", "customer"]


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    outcome: AuditOutcome,
    actor_id: int | None = None,
    actor_role: ActorRole | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    event_metadata: dict[str, Any] | None = None,
) -> None:
    """audit event 1건을 호출자 세션에 추가 (commit 안 함).

    - `actor_id` 명시 안 하면 `user_id_var` contextvar 에서 자동 첨부 (anonymous=NULL)
    - `request_id` 는 `request_id_var` contextvar 자동 첨부 ('-' → NULL 정규화)
    - `event_metadata` 의 PII 키 (email/first_name/...) → `[REDACTED]`
    - `AUDIT_ENABLED=false` 시 즉시 return (no-op)

    호출자가 본 함수 반환 후 `session.commit()` 시점에 영속. 본 작업 실패 시
    함께 롤백 (PRD §5.3 동기 정합성 — 정합성 우선, audit 신뢰도 보장).
    """
    if not settings.AUDIT_ENABLED:
        return

    effective_actor_id = actor_id if actor_id is not None else get_user_id()
    rid = get_request_id()
    effective_request_id = rid if rid != "-" else None

    redacted_metadata: dict[str, Any] | None = None
    if event_metadata is not None:
        walked = _redact_pii(event_metadata)
        # `_redact_pii` 는 임의 노드 walk — dict 입력 → dict 출력 보장.
        # mypy 가 Any 로 추론하므로 isinstance 좁히기.
        assert isinstance(walked, dict)
        redacted_metadata = walked

    row = AuditLogModel(
        actor_id=effective_actor_id,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        outcome=outcome,
        request_id=effective_request_id,
        event_metadata=redacted_metadata,
    )
    session.add(row)
    await session.flush()
