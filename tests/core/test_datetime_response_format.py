"""API 응답 datetime 형식 통일 회귀 가드 (PR #72 / E1).

PR #66 (`_build_system_meta`) 의 `requested_at` 가 Python `isoformat()` →
`+00:00` 접미사로 출력되어, 라우터 응답 본문의 Pydantic-serialized datetime
(`...Z` 접미사) 과 형식이 불일치했다. 본 PR 로 `format_iso_z` 헬퍼 도입 →
middleware meta 와 응답 본문이 동일 형식 (`Z` 접미사) 으로 통일.

drift 가드: 신규 datetime 필드가 다른 형식으로 노출되면 즉시 catch.
"""

import re
from datetime import UTC, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.core.datetime import format_iso_z

# Pydantic 2.x mode="json" 의 datetime 직렬화와 동등한 형식.
# 분초 마이크로초 옵션, 끝에 'Z' 접미사 강제.
ISO_Z_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def test_format_iso_z_utc() -> None:
    """UTC datetime → 'Z' 접미사."""
    dt = datetime(2026, 5, 26, 1, 23, 45, 678000, tzinfo=UTC)
    out = format_iso_z(dt)
    assert out == "2026-05-26T01:23:45.678000Z"
    assert ISO_Z_PATTERN.match(out)


def test_format_iso_z_non_utc_normalizes_to_utc_z() -> None:
    """비-UTC tz datetime → UTC 변환 후 'Z' 접미사 (시각 정합성 보존)."""
    kst = timezone(timedelta(hours=9))
    dt = datetime(2026, 5, 26, 10, 23, 45, 678000, tzinfo=kst)
    out = format_iso_z(dt)
    # KST 10:23 = UTC 01:23
    assert out == "2026-05-26T01:23:45.678000Z"


def test_format_iso_z_rejects_naive() -> None:
    """tz-naive datetime → ValueError (PR #8 정책 보존)."""
    naive = datetime(2026, 5, 26, 1, 23, 45)
    with pytest.raises(ValueError, match="timezone-aware"):
        format_iso_z(naive)


@pytest.mark.asyncio
async def test_response_meta_requested_at_uses_z_suffix(
    client: AsyncClient,
) -> None:
    """anonymous endpoint 응답의 meta.requested_at 이 'Z' 접미사 형식."""
    response = await client.get("/")
    body = response.json()
    assert "meta" in body
    requested_at = body["meta"]["requested_at"]
    assert ISO_Z_PATTERN.match(requested_at), (
        f"'Z' 접미사 형식 기대, 실제: {requested_at!r}"
    )


def test_pydantic_json_mode_produces_z_suffix() -> None:
    """sanity — Pydantic 2.x mode="json" 가 UTC datetime 을 'Z' 접미사로 직렬화.

    `format_iso_z` 와 Pydantic 자동 직렬화가 같은 형식임을 보장 — 응답 본문
    (Pydantic) 과 middleware meta (`format_iso_z`) 형식 일치의 unit-level 근거.

    note: SQLite + aiosqlite 환경은 DB round-trip 시 tzinfo 가 유실되어 응답
    본문의 DB-sourced datetime 은 접미사 없음 (`test_datetime_handling.py`
    docstring 참고). 운영 환경 (PostgreSQL DateTime(timezone=True)) 에서는
    tz 보존되어 Pydantic 가 'Z' 접미사 자동 부여 — 두 layer (Pydantic + middleware)
    가 동일 형식이라는 contract 가 본 unit 테스트로 확립.
    """
    from pydantic import BaseModel

    class _M(BaseModel):
        t: datetime

    dt = datetime(2026, 5, 26, 1, 23, 45, 678000, tzinfo=UTC)
    pydantic_out = _M(t=dt).model_dump_json()
    helper_out = format_iso_z(dt)

    # Pydantic JSON 출력에서 datetime 부분만 추출 (양옆 따옴표 제거)
    pydantic_datetime_str = pydantic_out.split('"t":"')[1].rstrip('"}')

    assert pydantic_datetime_str == helper_out, (
        f"Pydantic mode=json ({pydantic_datetime_str!r}) 과 "
        f"format_iso_z ({helper_out!r}) 가 동일 형식이어야 함"
    )
    assert ISO_Z_PATTERN.match(pydantic_datetime_str)
    assert ISO_Z_PATTERN.match(helper_out)
