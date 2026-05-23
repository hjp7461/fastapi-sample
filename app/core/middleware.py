"""FastAPI 미들웨어.

- `RequestIDMiddleware`: 매 요청에 trace ID 부여 → contextvar 저장 → 응답 헤더.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.context import request_id_var

HEADER_NAME = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """요청별 ID 를 contextvar 에 저장 + 응답 헤더로 반환.

    - incoming `X-Request-ID` 헤더가 있으면 그대로 사용 (분산 trace 호환).
    - 없으면 `uuid4().hex` 로 새로 생성 (32자, 충돌 거의 0).
    - 응답에 동일 ID 를 `X-Request-ID` 헤더로 반환 (디버깅 편의).
    - try/finally 로 contextvar reset — task 간 ID leakage 방지.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(HEADER_NAME) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[HEADER_NAME] = request_id
        return response
