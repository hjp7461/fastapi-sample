"""`RequestIDMiddleware` + loguru patcher 회귀 가드.

- 헤더 없는 요청 → 응답 X-Request-ID 가 uuid hex (32자) 자동 생성
- incoming X-Request-ID → 응답 동일
- 요청 처리 중 get_request_id() 가 헤더 값과 일치 (contextvar 동작)
- text/json 로그에 request_id 자동 첨부 (loguru patcher)
"""

import json
import re

import pytest
import pytest_asyncio
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from loguru import logger

from app.core.config import settings
from app.core.context import get_request_id
from app.core.logging import setup_logging
from app.main import app

HEX_32 = re.compile(r"^[0-9a-f]{32}$")


# ---------------------------------------------------------------------------
# 테스트 한정 라우트 — fixture 가 등록/제거
# ---------------------------------------------------------------------------


def _read_request_id() -> dict[str, str]:
    """현재 contextvar 값을 반환하는 테스트 핸들러."""
    return {"request_id": get_request_id()}


def _log_probe() -> dict[str, bool]:
    """요청 처리 중 loguru 로그를 1줄 남기는 테스트 핸들러."""
    logger.info("probe-from-request")
    return {"ok": True}


@pytest.fixture(autouse=True, scope="module")
def _probe_routes():
    """테스트용 임시 라우트 2개를 등록 + 모듈 종료 시 제거.

    `app.router.routes` 에 직접 추가 — fastapi 의 `add_api_route` 는 OpenAPI 까지
    갱신하므로 테스트 한정 용도엔 과함. router 의 routes 리스트만 임시 조작.
    """
    test_router = APIRouter()
    test_router.add_api_route("/__test_request_id", _read_request_id, methods=["GET"])
    test_router.add_api_route("/__test_log_probe", _log_probe, methods=["GET"])
    app.include_router(test_router)

    yield

    # teardown: 본 router 의 routes 만 제거 (다른 라우트 영향 없도록)
    app.router.routes = [
        r
        for r in app.router.routes
        if getattr(r, "path", None) not in ("/__test_request_id", "/__test_log_probe")
    ]


@pytest_asyncio.fixture
async def client():
    """ASGI 트랜스포트 — 라이프스팬 우회 (단위 테스트 격리)."""
    app.dependency_overrides = {}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture(autouse=True)
def restore_logger():
    """각 테스트 후 logger sink 상태를 default 로 복원."""
    yield
    logger.remove()
    setup_logging()


# ---------------------------------------------------------------------------
# 미들웨어 동작
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_id_generated_when_header_missing(client: AsyncClient):
    """헤더 없이 요청 → 응답 X-Request-ID 가 uuid4 hex 형식 (32자)."""
    response = await client.get("/__test_request_id")

    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert HEX_32.match(request_id), f"uuid4 hex 32자 기대, 실제: {request_id!r}"


@pytest.mark.asyncio
async def test_request_id_propagates_from_incoming_header(client: AsyncClient):
    """incoming X-Request-ID 가 있으면 그대로 수용 → 응답 동일."""
    custom_id = "my-trace-12345"
    response = await client.get(
        "/__test_request_id", headers={"X-Request-ID": custom_id}
    )

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id


@pytest.mark.asyncio
async def test_request_id_accessible_via_contextvar(client: AsyncClient):
    """요청 처리 중 get_request_id() → 응답 헤더와 일치."""
    custom_id = "ctxvar-trace-678"
    response = await client.get(
        "/__test_request_id", headers={"X-Request-ID": custom_id}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == custom_id
    assert body["request_id"] == response.headers.get("X-Request-ID")


@pytest.mark.asyncio
async def test_request_id_resets_between_requests(client: AsyncClient):
    """연속 요청 2건의 ID 가 서로 다름 — contextvar leakage 방지."""
    r1 = await client.get("/__test_request_id")
    r2 = await client.get("/__test_request_id")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["request_id"] != r2.json()["request_id"]


# ---------------------------------------------------------------------------
# loguru 자동 첨부
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_id_in_text_log(client: AsyncClient, capfd):
    """요청 처리 중 logger.info() → text 로그에 request_id 포함."""
    setup_logging()
    custom_id = "log-text-trace-99"
    response = await client.get(
        "/__test_log_probe", headers={"X-Request-ID": custom_id}
    )

    assert response.status_code == 200
    captured = capfd.readouterr()
    assert "probe-from-request" in captured.err
    assert custom_id in captured.err, (
        f"text 로그에 request_id 미포함. 실제 stderr:\n{captured.err}"
    )


@pytest.mark.asyncio
async def test_request_id_in_json_log(client: AsyncClient, capfd, monkeypatch):
    """LOG_FORMAT=json 시 record.extra.request_id 가 JSON 출력에 포함."""
    monkeypatch.setattr(settings, "LOG_FORMAT", "json")
    setup_logging()
    custom_id = "log-json-trace-42"
    response = await client.get(
        "/__test_log_probe", headers={"X-Request-ID": custom_id}
    )

    assert response.status_code == 200
    captured = capfd.readouterr()

    # probe-from-request 라인만 추출 (uvicorn / intercept 노이즈 배제)
    probe_lines = [
        line
        for line in captured.err.strip().splitlines()
        if "probe-from-request" in line
    ]
    assert probe_lines, "probe-from-request JSON 라인을 찾지 못함"

    data = json.loads(probe_lines[-1])
    assert data["record"]["message"] == "probe-from-request"
    assert data["record"]["extra"]["request_id"] == custom_id
