"""FastAPI 미들웨어.

- `RequestIDMiddleware`: 매 요청에 trace ID 부여 → contextvar 저장 → 응답 헤더.
- `AccessLogMiddleware`: 요청별 access log 한 줄 출력 (loguru, request_id 자동 첨부).
- `SuccessEnvelopeMiddleware`: 2xx JSON 응답을 `{"data": <payload>}` wrap (PR #49).
"""

import json
import re
import time
import uuid
from typing import Any, cast

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import ASGIApp

from app.core.context import request_id_var
from app.core.datetime import utcnow_aware

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

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
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


class AccessLogMiddleware(BaseHTTPMiddleware):
    """요청별 access log 한 줄 출력 (loguru 단일 표면).

    `RequestIDMiddleware` 안쪽에 등록한다 — contextvar 가 살아있을 때 호출되어
    `_inject_request_id` patcher 가 access log 에도 request_id 를 자동 첨부.
    uvicorn 의 기본 access log 는 `setup_logging()` 에서 비활성화되어 본
    미들웨어가 단일 진실원.

    예외 처리: `call_next` 가 raise 해도 try/finally 로 access log 한 줄은
    반드시 출력 (status=500 fallback). raise 는 catch 없이 자동 전파되어
    starlette `ServerErrorMiddleware` 가 traceback / 500 응답 책임.

    format 은 uvicorn 호환 (`{client} "{method} {path} HTTP/{version}" {status}`)
    + 디버깅용 elapsed_ms 추가.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        # call_next 가 raise 시 finally 에서 사용될 fallback. 사용자 exception
        # handler 가 다른 status 로 변환할 수도 있지만, "예외 발생" 시그널은 500.
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            client = request.client.host if request.client else "-"
            logger.info(
                '{client} "{method} {path} HTTP/{version}" {status} {elapsed_ms:.2f}ms',
                client=client,
                method=request.method,
                path=request.url.path,
                version=request.scope.get("http_version", "?"),
                status=status,
                elapsed_ms=elapsed_ms,
            )


# ---------------------------------------------------------------------------
# Success envelope (PR #49) — 2xx JSON 응답을 `{"data": <payload>}` wrap
# ---------------------------------------------------------------------------

OAUTH2_EXCEPTION_PATHS = frozenset({"/api/v1/users/token"})


def _build_system_meta() -> dict[str, str]:
    """시스템 meta (requested_at + request_id) 생성 (본 PR).

    - `requested_at`: 항상 노출 (UTC ISO8601, `+00:00` suffix).
    - `request_id`: `request_id_var` contextvar 값. 기본값 `"-"` (요청 외
      컨텍스트 placeholder) 또는 빈 문자열이면 omit — JSON 노이즈 회피.
      RequestIDMiddleware 가 설정한 정상 ID 만 응답 meta 에 노출.
    """
    meta: dict[str, str] = {"requested_at": utcnow_aware().isoformat()}
    request_id = request_id_var.get()
    if request_id and request_id != "-":
        meta["request_id"] = request_id
    return meta


def _inject_system_meta(body: dict[str, Any]) -> dict[str, Any]:
    """이미 envelope 인 응답의 meta 에 시스템 필드 주입 (본 PR).

    - meta dict 존재 시 `setdefault` → 기존 키 (pagination 등) 보호.
    - meta 가 없으면 신규 dict 추가.
    - body 는 in-place 갱신 후 그대로 반환.
    """
    system_meta = _build_system_meta()
    existing_meta = body.get("meta")
    if isinstance(existing_meta, dict):
        for key, value in system_meta.items():
            existing_meta.setdefault(key, value)
    else:
        body["meta"] = system_meta
    return body


class SuccessEnvelopeMiddleware(BaseHTTPMiddleware):
    """2xx JSON 응답을 `{"data": <payload>}` envelope 으로 wrap (PR #49)
    + 모든 envelope 응답의 meta 에 시스템 필드 (`requested_at`,
    `request_id`) 자동 주입 (본 PR — 응답 meta 확장).

    예외 (비적용 — 본 PR 도 동일 skip 로직 재사용, 신규 skip 0):
    - 4xx/5xx — handler 가 이미 envelope 처리 (PR #41/#42/#45/#46/#47/#48)
    - 204 No Content — body 없음
    - non-JSON content-type — HTML / stream / binary
    - OAUTH2_EXCEPTION_PATHS — RFC 6749 표준 응답 (`/users/token`)

    이미 envelope (`{data, ...}`) 인 응답은 PR #52 idempotent 룰 유지 (data
    이중 wrap X) + 본 PR meta 만 setdefault 로 union (pagination 필드 보호).
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        # 비적용 케이스 조기 반환
        if not (200 <= response.status_code < 300):
            return response
        if response.status_code == 204:
            return response
        if request.url.path in OAUTH2_EXCEPTION_PATHS:
            return response
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            return response

        # body 추출 — BaseHTTPMiddleware 는 항상 StreamingResponse 로 wrap.
        streaming = cast(StreamingResponse, response)
        body = b""
        async for chunk in streaming.body_iterator:
            if isinstance(chunk, str):
                body += chunk.encode("utf-8")
            elif isinstance(chunk, memoryview):
                body += bytes(chunk)
            else:
                body += chunk

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 원본 그대로 (안전망 — 실제로 도달 안 함)
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=content_type,
            )

        # PR #52 idempotent: 이미 envelope 형식 (dict + data 키) 이면 data
        # 이중 wrap 은 회피하고, 본 PR 시스템 meta 만 setdefault 로 union.
        # pagination meta envelope ({data, meta}) 의 기존 키 보호.
        if isinstance(payload, dict) and "data" in payload:
            payload = _inject_system_meta(payload)
        else:
            # 단일 객체 응답: envelope wrap + system meta 주입
            payload = {"data": payload, "meta": _build_system_meta()}

        wrapped = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        # content-length / content-type 은 starlette Response 가 재계산
        new_headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-length", "content-type")
        }
        return Response(
            content=wrapped,
            status_code=response.status_code,
            headers=new_headers,
            media_type="application/json",
        )
