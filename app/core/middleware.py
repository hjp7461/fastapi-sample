"""FastAPI 미들웨어.

- `RequestIDMiddleware`: 매 요청에 trace ID 부여 → contextvar 저장 → 응답 헤더.
"""

import re
import uuid

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.context import request_id_var

HEADER_NAME = "X-Request-ID"
MAX_LENGTH = 128
VALID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_incoming_id(raw: str | None) -> str | None:
    """incoming 헤더 검증 — 통과 시 그대로 반환, 실패 시 None.

    None 반환 시 caller 가 새 uuid 를 생성하도록 위임 (silent fallback).
    빈 문자열도 None 으로 처리 — 명시 거부 사유는 아니며 caller 가 새 ID 생성.
    """
    if not raw:
        return None
    if len(raw) > MAX_LENGTH:
        return None
    if not VALID_PATTERN.match(raw):
        return None
    return raw


class RequestIDMiddleware(BaseHTTPMiddleware):
    """요청별 ID 를 contextvar 에 저장 + 응답 헤더로 반환.

    incoming `X-Request-ID` 헤더 처리:
    - 검증 통과 (max 128자, `[A-Za-z0-9_-]+`) → 그대로 수용 (분산 trace 호환).
    - 검증 실패 (길이/charset) → 새 `uuid4().hex` 생성 + warn 로그 (silent fallback).
    - 헤더 없음/빈 값 → 새 `uuid4().hex` 생성 (warn 없음).
    - try/finally 로 contextvar reset — task 간 ID leakage 방지.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        raw = request.headers.get(HEADER_NAME)
        validated = _validate_incoming_id(raw)
        request_id = validated or uuid.uuid4().hex

        if raw and validated is None:
            logger.warning(
                "X-Request-ID rejected: invalid format "
                "(length={}, sample={!r}), new_id={}",
                len(raw),
                raw[:50],
                request_id,
            )

        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[HEADER_NAME] = request_id
        return response
