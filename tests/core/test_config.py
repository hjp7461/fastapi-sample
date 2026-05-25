"""Settings 검증 회귀 가드 (PR ## — list limit 환경 변수화).

- `gt=0` 가드 (Field 수준 단일 변수)
- `model_validator` cross-field 가드 (default ≤ max)

Settings 인스턴스 캐시 (`from app.core.config import settings`) 가 아니라
`Settings()` 직접 재구성으로 env 변경 시점 평가를 검증한다. 이전 import
된 settings 인스턴스에는 영향이 없도록 fixture 내에서만 격리.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_settings_list_max_limit_field_gt_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR ##: LIST_MAX_LIMIT=0 → Settings() ValidationError (gt=0 가드)."""
    from app.core.config import Settings

    monkeypatch.setenv("LIST_MAX_LIMIT", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_settings_cross_field_default_exceeds_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR ##: USER_LIST_DEFAULT_LIMIT > LIST_MAX_LIMIT → Settings() 부팅 실패.

    `model_validator(mode="after")` 의 cross-field 검증 — 잘못된 운영
    설정 fail-fast (사일런트 오작동 차단).
    """
    from app.core.config import Settings

    monkeypatch.setenv("LIST_MAX_LIMIT", "10")
    monkeypatch.setenv("USER_LIST_DEFAULT_LIMIT", "100")
    with pytest.raises(ValidationError, match="must be <= LIST_MAX_LIMIT"):
        Settings()
