"""audit log SQLModel.

PRD §5.4 권장 스키마 (중간 폭, 9 컬럼). Python 속성명 `event_metadata` —
SQLAlchemy 의 declarative base 가 `metadata` 를 예약 속성으로 사용하므로
혼동 방지 위해 SQL 컬럼명도 동일하게 `event_metadata` 로 통일.

`outcome` 은 Literal 타입 (recorder 에서만 검증 — DB 는 VARCHAR(16) 자유 허용).
`actor_role` 도 동일 (Literal 검증은 recorder).

`actor_id` FK 는 ON DELETE SET NULL — 사용자 삭제 시 audit 의 action/target/
metadata 는 보존 (PRD §7.4).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String
from sqlmodel import Field, SQLModel

from app.core.datetime import utcnow_aware


class AuditLogModel(SQLModel, table=True):
    """audit_logs 테이블 — 사용자/재고/인증 사건의 영속 sink."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_actor_id_created_at", "actor_id", "created_at"),
        Index("idx_audit_action_created_at", "action", "created_at"),
        Index("idx_audit_target", "target_type", "target_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    actor_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    actor_role: str | None = Field(
        default=None, sa_column=Column(String(16), nullable=True)
    )
    action: str = Field(sa_column=Column(String(64), nullable=False))
    target_type: str | None = Field(
        default=None, sa_column=Column(String(32), nullable=True)
    )
    target_id: int | None = Field(default=None)
    outcome: str = Field(sa_column=Column(String(16), nullable=False))
    request_id: str | None = Field(
        default=None, sa_column=Column(String(128), nullable=True)
    )
    event_metadata: dict[str, Any] | None = Field(
        default=None, sa_column=Column("event_metadata", JSON, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=utcnow_aware,
        sa_column=Column(
            DateTime(timezone=True),
            default=utcnow_aware,
            nullable=False,
        ),
    )
