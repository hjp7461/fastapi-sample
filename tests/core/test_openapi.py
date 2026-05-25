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


# require_* 가드 ↔ summary 권한 조건 키워드 매핑 (PR #55 표기 정책 정착).
# 신규 가드 추가 시 본 dict 갱신 의무 (app/api/permissions.py 와 동기화).
GUARD_SUMMARY_KEYWORDS: dict[str, set[str]] = {
    "require_admin": {"관리자"},
    "require_self_or_admin": {"본인", "관리자"},
    "require_staff_or_admin": {"staff", "admin"},
}


@pytest.mark.asyncio
async def test_summary_includes_permission_keywords_for_guarded_endpoints(
    client: AsyncClient,
) -> None:
    """`require_*` 가드 의존 endpoint 의 summary 가 권한 조건 키워드 포함.

    PR #55 의 표기 정책 (관리자 / 본인 / staff·admin) 회귀 가드 — 신규 endpoint
    추가 시 가드는 두었으나 summary 권한 조건 누락 즉시 catch.
    """
    from fastapi.routing import APIRoute

    from app.core.openapi_status import _walk_dependants
    from app.main import app

    response = await client.get("/api/v1/openapi.json")
    schema = response.json()["data"]
    paths = schema["paths"]

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/v1/"):
            continue

        required_guards = {
            d.call.__name__
            for d in _walk_dependants(route.dependant)
            if d.call is not None
            and hasattr(d.call, "__name__")
            and d.call.__name__ in GUARD_SUMMARY_KEYWORDS
        }
        if not required_guards:
            continue

        for method in route.methods:
            op = paths.get(route.path, {}).get(method.lower())
            if op is None:
                continue
            summary = op.get("summary", "")
            for guard in required_guards:
                missing = {
                    kw for kw in GUARD_SUMMARY_KEYWORDS[guard] if kw not in summary
                }
                assert not missing, (
                    f"{method} {route.path}: 가드 `{guard}` 사용 중인데 "
                    f"summary={summary!r} 에 권한 키워드 누락: {sorted(missing)}"
                )


# PR #63: OpenAPI tags 세분화 (2 -> 4) -- endpoint x tag 매트릭스 + 화이트리스트.
# 신규 endpoint 추가 시 tag 누락 / 오타 / 미허용 tag 즉시 catch (drift 가드).
# 정책 변경 시 본 dict + ALLOWED_TAGS + app/core/openapi.py::OPENAPI_TAGS 동시 갱신.
EXPECTED_ENDPOINT_TAGS: dict[tuple[str, str], list[str]] = {
    # users-auth (회원가입 / 로그인 / 내 정보 조회 / 내 정보 수정)
    ("POST", "/api/v1/users/"): ["users-auth"],
    ("POST", "/api/v1/users/token"): ["users-auth"],
    ("GET", "/api/v1/users/me"): ["users-auth"],
    ("PUT", "/api/v1/users/me"): ["users-auth"],
    # users-admin (사용자 단건 self_or_admin / 사용자 목록 admin)
    ("GET", "/api/v1/users/{user_id}"): ["users-admin"],
    ("GET", "/api/v1/users/"): ["users-admin"],
    # products-public (단건 / 목록 viewer 분기)
    ("GET", "/api/v1/products/{product_id}"): ["products-public"],
    ("GET", "/api/v1/products/"): ["products-public"],
    # products-admin (생성 / 수정 / 삭제 / 재고 변경)
    ("POST", "/api/v1/products/"): ["products-admin"],
    ("PUT", "/api/v1/products/{product_id}"): ["products-admin"],
    ("DELETE", "/api/v1/products/{product_id}"): ["products-admin"],
    ("PATCH", "/api/v1/products/{product_id}/inventory"): ["products-admin"],
}

ALLOWED_TAGS: frozenset[str] = frozenset(
    {"users-auth", "users-admin", "products-public", "products-admin"}
)


@pytest.mark.asyncio
async def test_endpoint_tags_match_whitelist(client: AsyncClient) -> None:
    """전체 /api/v1/ endpoint 의 tag 가 화이트리스트 + 매트릭스와 정확 일치.

    drift 가드 (PR #63):
    - 신규 endpoint 추가 시 tag 누락 -> 본 테스트 실패
    - 잘못된 tag 부여 (오타 'user-auth' / 기존 'users' 복귀) -> 화이트리스트 실패
    - tag 매핑 변경 (예: self_or_admin endpoint 이동) -> 매트릭스 정확 일치 실패
    - APIRouter default tag 복귀로 silent 부여 -> 매트릭스 실패

    `/api/v1/openapi.json` 자체는 docs auto-route 라 매트릭스에서 제외.
    """
    response = await client.get("/api/v1/openapi.json")
    schema = response.json()["data"]

    actual: dict[tuple[str, str], list[str]] = {}
    api_prefix = "/api/v1/"
    for path, methods in schema["paths"].items():
        if not path.startswith(api_prefix):
            continue
        # FastAPI 가 자동 생성한 openapi.json 자체는 제외
        if path == "/api/v1/openapi.json":
            continue
        for method, op in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            tags = op.get("tags", [])
            actual[(method.upper(), path)] = tags
            for tag in tags:
                assert tag in ALLOWED_TAGS, (
                    f"{method.upper()} {path}: tag '{tag}' 는 허용되지 않음. "
                    f"허용: {sorted(ALLOWED_TAGS)}"
                )

    assert actual == EXPECTED_ENDPOINT_TAGS, (
        f"endpoint x tag 매트릭스 drift 감지.\n"
        f"기대: {EXPECTED_ENDPOINT_TAGS}\n"
        f"실제: {actual}"
    )


@pytest.mark.asyncio
async def test_all_api_endpoints_have_korean_description(
    client: AsyncClient,
) -> None:
    """모든 /api/v1/ endpoint 에 한국어 description 명시.

    docstring fallback (영문 함수명 자동 생성 / 빈 docstring) 차단 —
    신규 endpoint 추가 시 description 누락 즉시 catch. PR #55 의 summary
    한국어 가드 패턴 복제 (서로 다른 표면, 동일 정책).
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
            description = op.get("description", "")
            assert description, f"{method.upper()} {path}: description 누락"
            assert any("가" <= c <= "힣" for c in description), (
                f"{method.upper()} {path}: description={description!r} — "
                "docstring fallback 의심, 한국어로 명시 필요"
            )


@pytest.mark.asyncio
async def test_description_includes_permission_keywords_for_guarded_endpoints(
    client: AsyncClient,
) -> None:
    """`require_*` 가드 의존 endpoint 의 description 이 권한 조건 키워드 포함.

    PR #60 의 summary 권한 키워드 가드를 description 에도 적용 — description
    상에서도 권한 조건이 명시되어야 외부 API 문서 (Swagger UI / Redoc) 에서
    소비자가 권한 요구사항을 즉시 인지 가능. `GUARD_SUMMARY_KEYWORDS` dict
    재사용 (별도 dict 신설 0, summary + description 단일 진실원).
    """
    from fastapi.routing import APIRoute

    from app.core.openapi_status import _walk_dependants
    from app.main import app

    response = await client.get("/api/v1/openapi.json")
    schema = response.json()["data"]
    paths = schema["paths"]

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/v1/"):
            continue

        required_guards = {
            d.call.__name__
            for d in _walk_dependants(route.dependant)
            if d.call is not None
            and hasattr(d.call, "__name__")
            and d.call.__name__ in GUARD_SUMMARY_KEYWORDS
        }
        if not required_guards:
            continue

        for method in route.methods:
            op = paths.get(route.path, {}).get(method.lower())
            if op is None:
                continue
            description = op.get("description", "")
            for guard in required_guards:
                missing = {
                    kw for kw in GUARD_SUMMARY_KEYWORDS[guard] if kw not in description
                }
                assert not missing, (
                    f"{method} {route.path}: 가드 `{guard}` 사용 중인데 "
                    f"description={description!r} 에 권한 키워드 누락: "
                    f"{sorted(missing)}"
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


@pytest.mark.asyncio
async def test_pagination_meta_optional_fields_in_schema(
    client: AsyncClient,
) -> None:
    """PR ##: PaginationMeta 의 offset + page 모드 필드가 모두 Optional 로 노출.

    Option A (단일 모델 + Optional 필드) — `total` 만 required, 나머지 5개
    (skip/limit/page/per_page/total_pages) 는 Optional 로 OpenAPI 양 모드 표현.
    """
    response = await client.get("/api/v1/openapi.json")
    schema = response.json()["data"]
    meta_schema = schema["components"]["schemas"]["PaginationMeta"]
    props = meta_schema["properties"]
    for field in ("total", "skip", "limit", "page", "per_page", "total_pages"):
        assert field in props, f"PaginationMeta 에 {field} 필드 누락"
    required = set(meta_schema.get("required", []))
    assert required == {"total"}, (
        f"required 가 {required} — total 만 필수여야 함 (Option A)"
    )
