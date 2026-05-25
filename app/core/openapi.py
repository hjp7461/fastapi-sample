"""OpenAPI 스키마 envelope 적용 (PR #51).

SuccessEnvelopeMiddleware (PR #49) 가 런타임에 `{"data": <payload>}` 로 wrap 하지만
OpenAPI 스키마는 wrap 전 payload 만 노출하던 문제를 해결.

`customize_openapi(app)` 가 FastAPI 의 `app.openapi` override 로 등록되어 생성된
OpenAPI dict 를 후처리한다:
  1) components/schemas 에 envelope Pydantic 모델 등록
  2) 모든 2xx success 응답 → {"data": <원본 schema>} wrap
     (204 No Content + OAUTH2_EXCEPTION_PATHS RFC 6749 제외)
  3) endpoint x status 정확 매핑 (`app.core.openapi_status`) — 실제 응답 가능한
     error status 만 ErrorEnvelope 로 주입 (PR #51 의 over-spec 정확화)

OAUTH2_EXCEPTION_PATHS 는 `app.core.middleware` 의 frozenset 을 그대로 재사용 —
middleware ↔ OpenAPI 단일 진실원 (정책 변경 시 한 곳만 수정).
"""

from typing import Any, Generic, TypeVar

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.core.middleware import OAUTH2_EXCEPTION_PATHS
from app.core.openapi_status import resolve_status_codes

T = TypeVar("T")


# OpenAPI tags 메타데이터 (PR #63 — tags 2→4 세분화).
# 권한 경계 기준으로 Swagger UI 그룹화 + 외부 SDK 자동 생성 namespace 분리.
# 신규 tag 추가 시 `tests/core/test_openapi.py::ALLOWED_TAGS` 와
# `EXPECTED_ENDPOINT_TAGS` 매트릭스 동시 갱신 필수.
OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "users-auth",
        "description": (
            "공개/인증 사용자 API — 회원가입, 로그인 (OAuth2), 내 정보 조회/수정."
        ),
    },
    {
        "name": "users-admin",
        "description": (
            "관리자 전용 사용자 API — 사용자 단건 조회 (self_or_admin), "
            "사용자 목록 (admin)."
        ),
    },
    {
        "name": "products-public",
        "description": (
            "공개 상품 조회 API — 단건/목록 (viewer 권한 분기로 "
            "ProductResponse 또는 ProductPublicView 응답)."
        ),
    },
    {
        "name": "products-admin",
        "description": ("staff+ 상품 변경 API — 생성, 수정, 삭제, 재고 변경."),
    },
]


class SuccessEnvelope(BaseModel, Generic[T]):
    """SuccessEnvelopeMiddleware (PR #49) 가 wrap 한 success 응답 형식."""

    data: T


class ErrorDetail(BaseModel):
    """envelope 내 detail 객체 (PR #42)."""

    message: str
    code: str


class ErrorEnvelope(BaseModel):
    """도메인 예외 / HTTPException → envelope 응답 (PR #42)."""

    detail: ErrorDetail


class ValidationErrorItem(BaseModel):
    """field-level validation error (PR #48). raw `input` 은 PII 차단으로 제외."""

    loc: list[str]
    msg: str
    type: str


class ValidationErrorDetail(BaseModel):
    """422 RequestValidationError envelope 내 detail (PR #48)."""

    message: str
    code: str
    errors: list[ValidationErrorItem]


class ValidationErrorEnvelope(BaseModel):
    """422 RequestValidationError envelope 응답 (PR #48)."""

    detail: ValidationErrorDetail


class ResponseMeta(BaseModel):
    """success envelope 의 meta union dict.

    pagination 필드 (PR #52, 듀얼 모드) 와 시스템 필드 (본 PR — 응답 meta
    확장) 가 동일 dict 에 union. 모든 필드 Optional — 적용 가능한 필드만
    응답에 직렬화 (Option A: 단일 모델 + Optional 필드).

    pagination (offset 모드): `{total, skip, limit}` — PR #52 동일.
    pagination (page 모드): `{total, page, per_page, total_pages}`.
    시스템 (본 PR): `requested_at` (UTC ISO8601), `request_id` (PR #32
    contextvar). 단일 객체 응답에서는 pagination 필드 omit, 시스템 필드만
    노출. list 응답에서는 양쪽 union.

    `app/core/pagination.py::build_meta` 가 pagination mode 별 필요한 키만
    채우고, `SuccessEnvelopeMiddleware` 가 시스템 필드를 setdefault 로
    union (pagination 필드 보호).
    """

    # pagination (PR #52)
    total: int | None = None
    # offset 모드 필드
    skip: int | None = None
    limit: int | None = None
    # page 모드 필드
    page: int | None = None
    per_page: int | None = None
    total_pages: int | None = None
    # 시스템 필드 (본 PR — 응답 meta 확장)
    requested_at: str | None = None
    request_id: str | None = None


# 하위 호환 alias — 기존 import 경로 (`from app.core.openapi import
# PaginationMeta`) 보존. 새 코드는 `ResponseMeta` 사용 권장.
PaginationMeta = ResponseMeta


class PaginatedResponse(BaseModel, Generic[T]):
    """list endpoint 응답 envelope (PR #52, 듀얼 모드 확장 + 본 PR meta 통합).

    응답 형식: `{"data": [...T], "meta": {...ResponseMeta}}` — middleware /
    OpenAPI customizer 의 idempotent 룰 (응답 body / schema 가 이미 `data` 키
    보유 시 wrap skip) 로 이중 wrap 회피. meta 는 pagination + 시스템 필드
    union (모두 Optional).
    """

    data: list[T]
    meta: ResponseMeta


class EnvelopedResponse(BaseModel, Generic[T]):
    """단일 객체 응답 envelope — middleware 자동 주입 대상 (본 PR).

    응답 형식: `{"data": T, "meta": {requested_at, request_id}}` —
    pagination 필드는 단일 응답에서 omit. response_model 강제는 옵션 —
    라우터는 기존처럼 payload 만 반환하고 middleware 가 envelope + meta
    자동 주입 (라우터 변경 0).
    """

    data: T
    meta: ResponseMeta | None = None


_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

_ERROR_RESPONSE_META: dict[int, tuple[str, str]] = {
    400: ("ErrorEnvelope", "Bad Request — domain validation or business logic error"),
    401: (
        "ErrorEnvelope",
        "Unauthorized — invalid/expired token or inactive account",
    ),
    403: ("ErrorEnvelope", "Forbidden — insufficient permissions"),
    404: ("ErrorEnvelope", "Not Found — resource missing"),
    422: (
        "ValidationErrorEnvelope",
        "Unprocessable Entity — Pydantic input validation",
    ),
}


def customize_openapi(app: FastAPI) -> dict[str, Any]:
    """생성된 OpenAPI 스키마를 envelope 형식에 맞게 후처리.

    첫 호출 시 1회 생성 후 `app.openapi_schema` 캐시 — 이후 호출은 캐시 반환
    (FastAPI 공식 custom_openapi 패턴).
    """
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    _register_envelope_components(schema)
    _wrap_success_responses(schema)
    _inject_error_responses(schema, app)

    app.openapi_schema = schema
    return schema


def _register_envelope_components(schema: dict[str, Any]) -> None:
    """components/schemas 에 envelope 모델 추가 (Generic SuccessEnvelope /
    PaginatedResponse 제외 — 인스턴스화된 형태가 paths 안에 inline 또는
    `$ref` 로 들어가므로 별도 등록 불필요).

    본 PR: `ResponseMeta` 등록 (PaginationMeta alias 도 동일 이름 유지로 backward
    compat). `_ensure_meta_in_schema` 가 단일 객체 응답 schema 에 `meta` 추가
    시 본 컴포넌트를 `$ref` 로 참조.
    """
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for model in (
        ErrorDetail,
        ErrorEnvelope,
        ValidationErrorItem,
        ValidationErrorDetail,
        ValidationErrorEnvelope,
        ResponseMeta,
    ):
        components[model.__name__] = model.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )


def _wrap_success_responses(schema: dict[str, Any]) -> None:
    """모든 2xx 응답을 {"data": <원본 schema>} 로 wrap.

    예외 (조기 skip):
    - 204 No Content (스키마 없음)
    - OAUTH2_EXCEPTION_PATHS (RFC 6749, `/api/v1/users/token`)
    - PR #52: 이미 envelope 형식 (`data` property 보유) 인 schema (PaginatedResponse 등)
    """
    components = schema.get("components", {}).get("schemas", {})
    for path, methods in schema.get("paths", {}).items():
        if path in OAUTH2_EXCEPTION_PATHS:
            continue
        for method, op in methods.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            responses = op.get("responses", {})
            for status_code, response in responses.items():
                if not status_code.startswith("2"):
                    continue
                if status_code == "204":
                    continue
                _wrap_response_content(response, components)


def _wrap_response_content(
    response: dict[str, Any], components: dict[str, Any]
) -> None:
    """단일 response object 의 content/schema 를 {"data": <원본>, "meta":
    ResponseMeta} 로 wrap.

    PR #52 idempotent: 이미 `data` property 를 가진 schema 는 wrap skip,
    `meta` 만 누락 시 보강 (PaginatedResponse[T] 등 라우터가 직접 envelope
    을 구성한 경우 데이터는 그대로 두고 meta 만 일관 보장).

    PR #62 (OpenAPI examples): schema wrap 시 inner example 도 `{"data": ...}` 로
    함께 wrap (idempotent — 이미 envelope 형식이면 skip). 라우터가 `responses=`
    에 envelope 형식 example 을 직접 적시한 경우 이중 wrap 방지.

    본 PR: 신규 wrap 시 `meta: ResponseMeta` 필드 동시 주입 + 이미 envelope
    인 경우 `_ensure_meta_in_schema` 로 누락된 meta 보강.
    """
    content = response.get("content", {})
    for media_obj in content.values():
        if "schema" not in media_obj:
            continue
        original = media_obj["schema"]
        if _schema_has_data_property(original, components):
            _ensure_meta_in_schema(original, components)
            continue
        media_obj["schema"] = {
            "type": "object",
            "required": ["data"],
            "properties": {
                "data": original,
                "meta": {"$ref": "#/components/schemas/ResponseMeta"},
            },
        }
        # PR #62: inner example 을 envelope 으로 wrap (idempotent)
        if "example" in media_obj and not _example_is_wrapped(media_obj["example"]):
            media_obj["example"] = {"data": media_obj["example"]}


def _ensure_meta_in_schema(schema: dict[str, Any], components: dict[str, Any]) -> None:
    """envelope 이지만 meta 가 누락된 schema 에 `meta: ResponseMeta` 추가 (본 PR).

    `$ref` 는 components 의 target schema 를 직접 수정 — middleware 가 모든
    success 응답에 meta 를 일관 주입하므로 OpenAPI 도 동일하게 표현. union
    (`oneOf`/`anyOf`) 멤버는 재귀로 처리.
    """
    if "$ref" in schema:
        ref_name = schema["$ref"].rsplit("/", 1)[-1]
        target = components.get(ref_name)
        if target is None:
            return
        properties = target.setdefault("properties", {})
        properties.setdefault("meta", {"$ref": "#/components/schemas/ResponseMeta"})
        return
    for member in schema.get("oneOf", []) + schema.get("anyOf", []):
        _ensure_meta_in_schema(member, components)
    if "properties" in schema:
        schema["properties"].setdefault(
            "meta", {"$ref": "#/components/schemas/ResponseMeta"}
        )


def _example_is_wrapped(example: Any) -> bool:
    """example 이 이미 envelope 형식 (`{"data": ...}`) 인지 검사 (PR #62).

    PR #52 의 `_schema_has_data_property` 와 동일한 idempotent 패턴 — dict 이고
    `data` 키를 가지면 envelope 으로 간주 (이중 wrap 회피).
    """
    return isinstance(example, dict) and "data" in example


def _schema_has_data_property(
    schema: dict[str, Any], components: dict[str, Any]
) -> bool:
    """schema 가 이미 `data` property 를 보유하면 envelope 형식으로 간주 (PR #52).

    `$ref` 인 경우 components 에서 target 모델을 찾아 properties 검사.
    union (`oneOf`/`anyOf`) 의 경우 임의 멤버라도 envelope 형식이면 True
    (Union[PaginatedResponse[A], PaginatedResponse[B]] 등 patterns).
    """
    if "$ref" in schema:
        ref_name = schema["$ref"].rsplit("/", 1)[-1]
        target = components.get(ref_name, {})
        return "data" in target.get("properties", {})
    for member in schema.get("oneOf", []) + schema.get("anyOf", []):
        if _schema_has_data_property(member, components):
            return True
    return "data" in schema.get("properties", {})


def _inject_error_responses(schema: dict[str, Any], app: FastAPI) -> None:
    """endpoint x status 정확 매핑으로 ErrorEnvelope responses 주입.

    `resolve_status_codes(route)` (app/core/openapi_status.py) 가 endpoint 별
    실제 응답 가능한 status set 을 도출하고, 본 함수는 해당 status 만 스키마에
    주입한다. PR #51 의 일괄 주입에서 over-spec 제거.

    - 401/403/404/400 → ErrorEnvelope
    - 422 → ValidationErrorEnvelope (errors 배열 포함)
    - 매핑되지 않은 endpoint (예: `/`) 는 error response 미주입.
    """
    route_status_map: dict[tuple[str, str], set[int]] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        codes = resolve_status_codes(route)
        for method in route.methods:
            route_status_map[(route.path, method.lower())] = codes

    for path, methods in schema.get("paths", {}).items():
        for method, op in methods.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            codes = route_status_map.get((path, method.lower()), set())
            responses = op.setdefault("responses", {})
            for status_code, meta in _ERROR_RESPONSE_META.items():
                if status_code not in codes:
                    continue
                envelope_name, description = meta
                # PR #62: 라우터가 `responses=` 로 명시한 example/headers/description
                # 보존 (merge). schema 만 envelope `$ref` 로 (재)덮어쓰기.
                existing = responses.get(str(status_code), {})
                merged_content = {
                    media_type: {
                        **media_obj,
                        "schema": {"$ref": f"#/components/schemas/{envelope_name}"},
                    }
                    for media_type, media_obj in existing.get("content", {}).items()
                }
                merged_content.setdefault(
                    "application/json",
                    {"schema": {"$ref": f"#/components/schemas/{envelope_name}"}},
                )
                merged: dict[str, Any] = {
                    "description": existing.get("description", description),
                    "content": merged_content,
                }
                if "headers" in existing:
                    merged["headers"] = existing["headers"]
                responses[str(status_code)] = merged
