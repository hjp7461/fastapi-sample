"""OpenAPI 스키마 envelope 적용 (PR #51).

SuccessEnvelopeMiddleware (PR #49) 가 런타임에 `{"data": <payload>}` 로 wrap 하지만
OpenAPI 스키마는 wrap 전 payload 만 노출하던 문제를 해결.

`customize_openapi(app)` 가 FastAPI 의 `app.openapi` override 로 등록되어 생성된
OpenAPI dict 를 후처리한다:
  1) components/schemas 에 envelope Pydantic 모델 등록
  2) 모든 2xx success 응답 → {"data": <원본 schema>} wrap
     (204 No Content + OAUTH2_EXCEPTION_PATHS RFC 6749 제외)
  3) 모든 endpoint 에 401/403/404/400/422 ErrorEnvelope 일괄 주입

OAUTH2_EXCEPTION_PATHS 는 `app.core.middleware` 의 frozenset 을 그대로 재사용 —
middleware ↔ OpenAPI 단일 진실원 (정책 변경 시 한 곳만 수정).
"""

from typing import Any, Generic, TypeVar

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

from app.core.middleware import OAUTH2_EXCEPTION_PATHS

T = TypeVar("T")


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


class PaginationMeta(BaseModel):
    """offset 기반 페이징 meta (PR #52)."""

    total: int
    skip: int
    limit: int


class PaginatedResponse(BaseModel, Generic[T]):
    """list endpoint 응답 envelope (PR #52).

    응답 형식: `{"data": [...T], "meta": {...PaginationMeta}}` — middleware /
    OpenAPI customizer 의 idempotent 룰 (응답 body / schema 가 이미 `data` 키
    보유 시 wrap skip) 로 이중 wrap 회피.
    """

    data: list[T]
    meta: PaginationMeta


_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

_STANDARD_ERROR_RESPONSES: dict[str, tuple[str, str]] = {
    "400": ("ErrorEnvelope", "Bad Request — domain validation or business logic error"),
    "401": (
        "ErrorEnvelope",
        "Unauthorized — invalid/expired token or inactive account",
    ),
    "403": ("ErrorEnvelope", "Forbidden — insufficient permissions"),
    "404": ("ErrorEnvelope", "Not Found — resource missing"),
    "422": (
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
    _inject_error_responses(schema)

    app.openapi_schema = schema
    return schema


def _register_envelope_components(schema: dict[str, Any]) -> None:
    """components/schemas 에 envelope 모델 추가 (Generic SuccessEnvelope /
    PaginatedResponse 제외 — 인스턴스화된 형태가 paths 안에 inline 또는
    `$ref` 로 들어가므로 별도 등록 불필요)."""
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for model in (
        ErrorDetail,
        ErrorEnvelope,
        ValidationErrorItem,
        ValidationErrorDetail,
        ValidationErrorEnvelope,
        PaginationMeta,
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
    """단일 response object 의 content/schema 를 {"data": <원본>} 으로 wrap.

    PR #52 idempotent: 이미 `data` property 를 가진 schema 는 그대로 통과
    (PaginatedResponse[T] 등 라우터가 직접 envelope 을 구성한 경우).
    """
    content = response.get("content", {})
    for media_obj in content.values():
        if "schema" not in media_obj:
            continue
        original = media_obj["schema"]
        if _schema_has_data_property(original, components):
            continue
        media_obj["schema"] = {
            "type": "object",
            "required": ["data"],
            "properties": {"data": original},
        }


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


def _inject_error_responses(schema: dict[str, Any]) -> None:
    """모든 endpoint 에 표준 error envelope responses 일괄 주입.

    - 401/403/404/400 → ErrorEnvelope
    - 422 → ValidationErrorEnvelope (errors 배열 포함)
    - 기존 응답 (FastAPI default 422 등) 은 envelope 으로 덮어쓰기 (단일 진실원).
    """
    for _path, methods in schema.get("paths", {}).items():
        for method, op in methods.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            responses = op.setdefault("responses", {})
            for status_code, (
                envelope_name,
                description,
            ) in _STANDARD_ERROR_RESPONSES.items():
                responses[status_code] = {
                    "description": description,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{envelope_name}"}
                        }
                    },
                }
