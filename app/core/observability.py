"""Sentry 통합 — 운영 관측성 단일 표면.

`setup_sentry()` 가 환경 변수 기반 활성화 분기 (DSN 빈 값 = no-op) +
FastAPI/Starlette/Loguru Integration + PII redact `before_send` +
request_id 자동 첨부를 일괄 구성한다. main.py 의 `setup_logging()` 직후 호출.

다른 모듈에서 `sentry_sdk.init` 을 직접 호출하지 말 것 — 본 모듈이 단일 진입점.

LoggingIntegration 은 명시적으로 disable — InterceptHandler 가 stdlib → loguru
로 통과시키므로 LoggingIntegration + LoguruIntegration 동시 활성화 시 이중 capture
가 된다. LoguruIntegration 만 활성화하여 loguru 단일 표면을 유지한다.
"""

from collections.abc import Mapping
from typing import Any, cast

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.loguru import LoguruIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.types import Event, Hint

from app.core.config import settings
from app.core.context import get_request_id, get_user_id

# 도메인 PII 필드 — event 의 dict 트리 walk 시 redact 대상.
# User/Product 모델 확장 시 본 frozenset 만 갱신 (단일 진실원).
_PII_KEYS: frozenset[str] = frozenset(
    {"email", "first_name", "last_name", "password", "hashed_password"}
)

_REDACTED = "[REDACTED]"


def _redact_pii(node: Any) -> Any:
    """dict/list 재귀 walk — `_PII_KEYS` 매칭 시 값을 `[REDACTED]` 로 치환.

    Sentry event 의 `extra` / `contexts` / `breadcrumbs[].data` / `request.data`
    같은 임의 트리에 도메인 PII 가 노출되는 경우를 일괄 차단.
    """
    if isinstance(node, Mapping):
        return {
            k: (_REDACTED if k in _PII_KEYS else _redact_pii(v))
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_redact_pii(x) for x in node]
    return node


def _before_send(event: Event, _hint: Hint) -> Event | None:
    """전송 직전 hook — PII redact + request_id tag 첨부.

    sentry-sdk 가 `before_send` 의 return None 을 "drop" 으로 해석 — 본 hook 은
    None 을 반환하지 않는다 (모든 event 전송).

    `_redact_pii` 는 임의 dict/list 트리에 동작하므로 mypy 가 반환 타입을
    `dict[Any, Any]` 로 추론. 본 hook 은 Event 의 shape (TypedDict) 보존만 하므로
    runtime 안전 — cast 로 명시.
    """
    redacted = _redact_pii(event)
    if isinstance(redacted, dict):
        tags = redacted.setdefault("tags", {})
        if isinstance(tags, dict):
            tags["request_id"] = get_request_id()
            # A3 (PR #73) — 인증된 요청에만 user_id tag 첨부. anonymous 는 omit.
            # Sentry tag value 는 string 만 허용 — str() 변환 명시.
            user_id = get_user_id()
            if user_id is not None:
                tags["user_id"] = str(user_id)
        return cast(Event, redacted)
    return event


def setup_sentry() -> None:
    """환경 변수 기반 Sentry 초기화. main.py import 시점에 1회 호출.

    - `SENTRY_DSN` 빈 값 시 즉시 return (no-op) — 개발 / 테스트 / 비활성 운영 0 영향
    - FastAPI/Starlette Integration 자동 + transaction_style="endpoint"
    - LoguruIntegration 으로 loguru ERROR+ 자동 capture
    - LoggingIntegration 명시적 disable — InterceptHandler 와의 이중 capture 차단
    - `send_default_pii=False` 강제 + `before_send` 가 도메인 PII redact
    """
    if not settings.SENTRY_DSN:
        return

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        release=settings.SENTRY_RELEASE,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
        send_default_pii=False,
        before_send=_before_send,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            LoguruIntegration(),
        ],
        disabled_integrations=[LoggingIntegration()],
    )
