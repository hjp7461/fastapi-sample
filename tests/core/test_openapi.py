"""OpenAPI envelope 스키마 회귀 가드 (PR #51).

`customize_openapi` (app/core/openapi.py) 가 SuccessEnvelopeMiddleware (PR #49)
의 wrap 동작과 일치하는 OpenAPI 스키마를 생성하는지 검증.

검증 대상:
- success 응답 (2xx) → {"data": <원본 schema>} wrap
- 예외: 204 No Content, OAUTH2_EXCEPTION_PATHS (`/api/v1/users/token`)
- error envelope 일괄 주입 (401/403/404/400/422)
- components/schemas 에 envelope 모델 등록
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_success_response_wrapped_with_data_envelope(
    client: AsyncClient,
) -> None:
    """PR #51: success 응답 스키마가 {"data": <원본>} 으로 wrap 되는지 회귀 가드.

    SuccessEnvelopeMiddleware (PR #49) 의 런타임 wrap 과 OpenAPI 스키마가 일치.
    """
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    schema = response.json()["data"]  # /openapi.json 자체도 envelope wrap 됨

    op = schema["paths"]["/api/v1/users/me"]["get"]
    success_schema = op["responses"]["200"]["content"]["application/json"]["schema"]

    assert success_schema["type"] == "object"
    assert success_schema["required"] == ["data"]
    assert "data" in success_schema["properties"]


@pytest.mark.asyncio
async def test_oauth2_token_response_not_wrapped(client: AsyncClient) -> None:
    """PR #51: OAuth2 token endpoint 의 200 응답은 RFC 6749 표준 (wrap 안 됨).

    OAUTH2_EXCEPTION_PATHS (app/core/middleware.py) 의 frozenset 을 customizer
    가 import 재사용 — middleware ↔ OpenAPI 단일 진실원.
    """
    response = await client.get("/api/v1/openapi.json")
    schema = response.json()["data"]

    op = schema["paths"]["/api/v1/users/token"]["post"]
    success_schema = op["responses"]["200"]["content"]["application/json"]["schema"]

    # Token 스키마 그대로 — data 필드로 wrap 안 됨
    properties = success_schema.get("properties", {})
    assert "data" not in properties
    # Token 은 $ref 또는 본인 properties (access_token, token_type)
    assert "$ref" in success_schema or "access_token" in properties


@pytest.mark.asyncio
async def test_204_response_not_wrapped(client: AsyncClient) -> None:
    """PR #51: 204 No Content 응답은 스키마 없음 (envelope 비적용).

    DELETE /products/{id} 가 204 반환 — body 없으므로 wrap 대상 아님.
    """
    response = await client.get("/api/v1/openapi.json")
    schema = response.json()["data"]

    op = schema["paths"]["/api/v1/products/{product_id}"]["delete"]
    response_204 = op["responses"].get("204", {})
    # 204 응답이 존재하면 content 가 없거나 빈 객체
    assert "content" not in response_204 or not response_204.get("content")


@pytest.mark.asyncio
async def test_error_envelope_refs_on_full_coverage_endpoint(
    client: AsyncClient,
) -> None:
    """PR #51 envelope `$ref` 형식 회귀 가드.

    5종 (400/401/403/404/422) 가 모두 도출되는 `PATCH /products/{id}/inventory`
    로 envelope 모델 참조 형식만 검증 (endpoint x status 정확 매핑은
    `tests/core/test_openapi_endpoint_status_mapping.py` 가 전수 검증).
    """
    response = await client.get("/api/v1/openapi.json")
    schema = response.json()["data"]

    op = schema["paths"]["/api/v1/products/{product_id}/inventory"]["patch"]
    responses = op["responses"]

    for status_code in ("400", "401", "403", "404", "422"):
        assert status_code in responses, f"missing status {status_code}"
        ref = responses[status_code]["content"]["application/json"]["schema"]["$ref"]
        assert ref.startswith("#/components/schemas/"), f"status {status_code}"

    for status_code in ("400", "401", "403", "404"):
        ref = responses[status_code]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("ErrorEnvelope"), f"status {status_code}"
    assert responses["422"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "ValidationErrorEnvelope"
    )


@pytest.mark.asyncio
async def test_422_uses_validation_error_envelope(client: AsyncClient) -> None:
    """PR #51: 422 응답이 ValidationErrorEnvelope (errors 배열 + message + code) 형식.

    PR #48 의 422 envelope (field-level errors + raw input 차단) 와 스키마 일치.
    """
    response = await client.get("/api/v1/openapi.json")
    schema = response.json()["data"]

    components = schema["components"]["schemas"]
    detail = components["ValidationErrorDetail"]

    assert "errors" in detail["properties"]
    assert "message" in detail["properties"]
    assert "code" in detail["properties"]


@pytest.mark.asyncio
async def test_envelope_components_registered(client: AsyncClient) -> None:
    """PR #51: components/schemas 에 envelope 모델 5종 모두 등록."""
    response = await client.get("/api/v1/openapi.json")
    schema = response.json()["data"]

    components = schema["components"]["schemas"]
    for name in (
        "ErrorEnvelope",
        "ErrorDetail",
        "ValidationErrorEnvelope",
        "ValidationErrorDetail",
        "ValidationErrorItem",
    ):
        assert name in components, f"missing component: {name}"


@pytest.mark.asyncio
async def test_all_api_endpoints_have_korean_summary(
    client: AsyncClient,
) -> None:
    """PR #55: 모든 /api/v1/ endpoint 에 한국어 summary 명시.

    영문 자동 생성 (`get_user_by_id` → `Get User By Id`) fallback 차단 —
    신규 endpoint 추가 시 summary 누락 즉시 catch.
    """
    response = await client.get("/api/v1/openapi.json")
    schema = response.json()["data"]
    api_prefix = "/api/v1/"
    for path, methods in schema["paths"].items():
        if not path.startswith(api_prefix):
            continue
        for method, op in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            summary = op.get("summary", "")
            assert summary, f"{method.upper()} {path}: summary 누락"
            assert any("가" <= c <= "힣" for c in summary), (
                f"{method.upper()} {path}: summary={summary!r} — "
                "영문 자동 생성 의심, 한국어로 명시 필요"
            )


@pytest.mark.asyncio
async def test_paginated_response_schema_not_double_wrapped(
    client: AsyncClient,
) -> None:
    """PR #52: list endpoint 의 PaginatedResponse[T] schema 가 envelope 이중 wrap 안 됨.

    customizer 의 idempotent 룰 (`$ref` follow → properties 의 `data` 키 검사) 회귀.
    이중 wrap 시 schema 가 `{type: object, properties: {data: <PaginatedResponse>}}`
    가 됨 → 즉시 실패.
    """
    response = await client.get("/api/v1/openapi.json")
    schema = response.json()["data"]

    op = schema["paths"]["/api/v1/users/"]["get"]
    success = op["responses"]["200"]["content"]["application/json"]["schema"]

    # PaginatedResponse 가 $ref 또는 inline — 둘 다 data + meta 필드만 있어야 함
    components = schema["components"]["schemas"]
    if "$ref" in success:
        ref_name = success["$ref"].rsplit("/", 1)[-1]
        target = components[ref_name]
        properties = target.get("properties", {})
    else:
        properties = success.get("properties", {})

    assert "data" in properties
    assert "meta" in properties
    # 이중 wrap 검증: data 는 array (list[UserSummary]), object 가 아님
    data_schema = properties["data"]
    assert data_schema.get("type") == "array", (
        f"data 가 array 가 아님 (이중 wrap 의심): {data_schema}"
    )
