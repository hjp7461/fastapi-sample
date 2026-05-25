"""Endpoint x status code 정확 매핑 회귀 가드.

PR #51 의 over-spec (모든 endpoint 에 5종 일괄 주입) 을 정확화한 결과,
각 endpoint 의 OpenAPI `responses` keys 가 실제 응답 가능한 status 만 노출
해야 한다. 본 테스트는 12 endpoint x 5 error status (+ success) 매트릭스를
전수 검증한다 — extra (over-spec) / missing (under-spec) 모두 감지.

매트릭스 갱신 사유:
- 신규 endpoint 추가 / 권한 가드 변경 / 도메인 예외 추가 / path param 변경 시
  `EXPECTED_STATUS_MATRIX` 에 한 줄 갱신 + RUNBOOK §10 매트릭스 갱신.
- 분석기 (`app.core.openapi_status`) 의 검출 규칙 자체가 잘못 동작하면
  본 테스트 또는 매트릭스 중 한쪽이 어긋남 → 즉시 catch.
"""

import pytest
from httpx import AsyncClient

# 12 endpoint x 응답 가능 status set (성공 + error).
# - GET /users/me: input 0 → 422 미발생. get_current_user → 401.
# - POST /users/token: form_data → 422. inline raise AuthenticationException → 401.
# - GET /products/{id}: get_optional_current_user (auth optional) → 401 미발생.
# - PATCH /products/{id}/inventory: BusinessLogicException 분기 → 400.
EXPECTED_STATUS_MATRIX: dict[tuple[str, str], set[str]] = {
    ("POST", "/api/v1/users/"): {"201", "400", "422"},
    ("GET", "/api/v1/users/me"): {"200", "401"},
    ("PUT", "/api/v1/users/me"): {"200", "401", "422"},
    ("POST", "/api/v1/users/token"): {"200", "401", "422"},
    ("GET", "/api/v1/users/{user_id}"): {"200", "401", "403", "404", "422"},
    ("GET", "/api/v1/users/"): {"200", "401", "403", "422"},
    ("POST", "/api/v1/products/"): {"201", "401", "403", "422"},
    ("GET", "/api/v1/products/{product_id}"): {"200", "404", "422"},
    ("PUT", "/api/v1/products/{product_id}"): {"200", "401", "403", "404", "422"},
    ("DELETE", "/api/v1/products/{product_id}"): {"204", "401", "403", "404", "422"},
    ("GET", "/api/v1/products/"): {"200", "422"},
    ("PATCH", "/api/v1/products/{product_id}/inventory"): {
        "200",
        "400",
        "401",
        "403",
        "404",
        "422",
    },
}


@pytest.mark.asyncio
async def test_endpoint_status_matrix_exact(client: AsyncClient) -> None:
    """12 endpoint 의 OpenAPI responses keys 가 기대 set 와 정확히 일치."""
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    schema = response.json()["data"]
    paths = schema["paths"]

    for (method, path), expected in EXPECTED_STATUS_MATRIX.items():
        assert path in paths, f"path 미존재: {path}"
        op = paths[path].get(method.lower())
        assert op is not None, f"method 미존재: {method} {path}"
        actual = set(op.get("responses", {}).keys())
        assert actual == expected, (
            f"{method} {path}: 기대={sorted(expected)} 실제={sorted(actual)} "
            f"(차이: extra={sorted(actual - expected)}, "
            f"missing={sorted(expected - actual)})"
        )


@pytest.mark.asyncio
async def test_endpoint_matrix_covers_all_api_v1_routes(client: AsyncClient) -> None:
    """`/api/v1/` 하위 모든 endpoint 가 EXPECTED_STATUS_MATRIX 에 등록.

    신규 endpoint 가 추가됐는데 매트릭스에 빠지면 즉시 catch — RUNBOOK §10
    갱신 누락 회귀 방지.
    """
    response = await client.get("/api/v1/openapi.json")
    schema = response.json()["data"]
    api_prefix = "/api/v1/"

    actual_endpoints: set[tuple[str, str]] = set()
    for path, methods in schema["paths"].items():
        if not path.startswith(api_prefix):
            continue
        for method in methods:
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            actual_endpoints.add((method.upper(), path))

    expected_endpoints = set(EXPECTED_STATUS_MATRIX.keys())
    missing = actual_endpoints - expected_endpoints
    extra = expected_endpoints - actual_endpoints
    assert not missing, f"매트릭스 누락 (신규 endpoint): {sorted(missing)}"
    assert not extra, f"매트릭스 잔존 (삭제된 endpoint): {sorted(extra)}"
