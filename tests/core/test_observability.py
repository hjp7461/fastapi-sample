"""`app/core/observability.py::setup_sentry` 회귀 가드 — mock transport 격리.

- DSN 빈 값 시 no-op (개발 / CI 0 영향)
- logger.exception 이 LoguruIntegration 으로 자동 capture
- before_send 가 현재 request_id 를 tags 에 첨부
- 도메인 PII (`email` / `first_name` 등) 가 event 전송 직전 `[REDACTED]` 로 redact
- _redact_pii 의 nested dict / list 재귀 walk (unit)
- Settings 의 SENTRY_TRACES_SAMPLE_RATE 가 0.0~1.0 외 값 시 fail-fast
"""

from collections.abc import Iterator
from typing import Any

import pytest
import sentry_sdk
from loguru import logger
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from app.core.context import request_id_var, user_id_var
from app.core.observability import _before_send, _redact_pii


class _MockTransport(Transport):
    """Sentry envelope 를 메모리에 누적 — HTTP 호출 0."""

    def __init__(self) -> None:
        super().__init__()
        self.envelopes: list[Envelope] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        self.envelopes.append(envelope)

    def events(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for env in self.envelopes:
            for item in env.items:
                if item.headers.get("type") == "event":
                    payload = item.payload.json
                    if isinstance(payload, dict):
                        out.append(payload)
        return out


@pytest.fixture
def sentry_isolated() -> Iterator[_MockTransport]:
    """sentry-sdk client 백업/복원 + mock transport 주입.

    `before_send` 는 본 PR 의 hook 명시 — production 과 동일 PII redact / request_id
    tag 첨부 경로 검증. integrations 는 LoguruIntegration 만 명시 (Logging 비활성).
    """
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.loguru import LoguruIntegration

    original_client = sentry_sdk.get_client()
    transport = _MockTransport()
    sentry_sdk.init(
        dsn="https://x@y.example/1",
        transport=transport,
        traces_sample_rate=0.0,  # transaction 노이즈 차단 (event 만 검증)
        send_default_pii=False,
        before_send=_before_send,
        integrations=[LoguruIntegration()],
        disabled_integrations=[LoggingIntegration()],
    )
    yield transport
    # client 복원 — 다음 테스트로 누수 차단.
    sentry_sdk.get_global_scope().set_client(original_client)


def test_setup_sentry_noop_when_dsn_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DSN 빈 값 → init 호출 안 함 → 활성 client 없음.

    `get_client()` 는 매 호출마다 NonRecordingClient 인스턴스를 새로 만들 수
    있어 identity 비교는 불안정. `is_active()` 가 진실원 — 활성 client 없을 때
    False 반환.
    """
    from app.core.config import settings
    from app.core.observability import setup_sentry

    monkeypatch.setattr(settings, "SENTRY_DSN", "")

    setup_sentry()
    assert not sentry_sdk.get_client().is_active()


def test_logger_exception_captured(sentry_isolated: _MockTransport) -> None:
    """logger.exception → LoguruIntegration 가 Sentry 로 capture."""
    try:
        raise ValueError("probe-exc")  # noqa: TRY301
    except ValueError:
        logger.exception("oops")

    sentry_sdk.flush(timeout=2)
    events = sentry_isolated.events()
    assert events, "logger.exception 호출이 event 1건을 만들어야 함"
    # exception 또는 logentry 에 메시지가 포함되었는지 검증
    serialized = str(events)
    assert "probe-exc" in serialized or "oops" in serialized


def test_request_id_tag_attached(sentry_isolated: _MockTransport) -> None:
    """before_send 가 현재 request_id 를 tags 에 첨부."""
    token = request_id_var.set("test-rid-abc123")
    try:
        sentry_sdk.capture_message("probe")
        sentry_sdk.flush(timeout=2)
    finally:
        request_id_var.reset(token)

    events = sentry_isolated.events()
    assert events, "capture_message 호출이 event 1건을 만들어야 함"
    assert events[-1]["tags"]["request_id"] == "test-rid-abc123"


def test_user_id_tag_attached_when_authenticated(
    sentry_isolated: _MockTransport,
) -> None:
    """A3 (PR #73): before_send 가 인증된 요청의 user_id 를 tags 에 stringify 첨부."""
    rid_token = request_id_var.set("rid-with-user")
    uid_token = user_id_var.set(42)
    try:
        sentry_sdk.capture_message("probe-with-user")
        sentry_sdk.flush(timeout=2)
    finally:
        request_id_var.reset(rid_token)
        user_id_var.reset(uid_token)

    events = sentry_isolated.events()
    assert events, "capture_message 호출이 event 1건을 만들어야 함"
    assert events[-1]["tags"]["user_id"] == "42"


def test_user_id_tag_omitted_when_anonymous(
    sentry_isolated: _MockTransport,
) -> None:
    """A3 (PR #73): user_id_var=None (anonymous) 시 user_id tag omit."""
    rid_token = request_id_var.set("rid-anonymous")
    # user_id_var 는 default None (set 안 함)
    try:
        sentry_sdk.capture_message("probe-anonymous")
        sentry_sdk.flush(timeout=2)
    finally:
        request_id_var.reset(rid_token)

    events = sentry_isolated.events()
    assert events, "capture_message 호출이 event 1건을 만들어야 함"
    assert "user_id" not in events[-1]["tags"]


def test_pii_redacted_in_event(sentry_isolated: _MockTransport) -> None:
    """scope.set_extra 의 도메인 PII 가 전송 직전 `[REDACTED]` 로 치환."""
    with sentry_sdk.new_scope() as scope:
        scope.set_extra(
            "user_data",
            {"email": "leak@example.com", "first_name": "Leaky", "id": 42},
        )
        sentry_sdk.capture_message("probe-pii")
    sentry_sdk.flush(timeout=2)

    events = sentry_isolated.events()
    assert events, "capture_message 호출이 event 1건을 만들어야 함"
    extra = events[-1].get("extra", {}).get("user_data", {})
    assert extra.get("email") == "[REDACTED]"
    assert extra.get("first_name") == "[REDACTED]"
    assert extra.get("id") == 42  # 비 PII 는 보존


def test_pii_redacted_nested_dict() -> None:
    """nested dict / list 재귀 walk 검증 (unit — transport 불필요)."""
    payload = {
        "user": {"email": "x@y.com", "profile": {"last_name": "Doe"}},
        "items": [{"password": "hunter2"}, {"safe": "ok"}],
        "id": 1,
    }
    out = _redact_pii(payload)
    assert out["user"]["email"] == "[REDACTED]"
    assert out["user"]["profile"]["last_name"] == "[REDACTED]"
    assert out["items"][0]["password"] == "[REDACTED]"
    assert out["items"][1]["safe"] == "ok"
    assert out["id"] == 1


def test_sample_rate_validation_fail_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SENTRY_TRACES_SAMPLE_RATE=1.5 → Settings 초기화 시 ValidationError."""
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "1.5")
    # Settings 인스턴스를 직접 생성 (전역 settings 는 그대로) — 검증 트리거 격리.
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="less_than_equal"):
        Settings()
