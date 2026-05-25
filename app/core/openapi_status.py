"""Endpoint x status code 정적 분석 (PR #51 의 over-spec 정확화).

PR #51 은 모든 endpoint 에 400/401/403/404/422 를 일괄 주입했다.
공개 회원가입 (`POST /users/`) 에 401/403, body 없는 `GET /users/me` 에 422 등
실제로 발생하지 않는 status 가 OpenAPI 에 노출되어 클라이언트 SDK 가
false-positive error handling 을 생성하는 문제가 있었다.

본 모듈은 endpoint 별로 실제 응답 가능한 status set 만 도출한다.

검출 규칙:
- 401: dependency tree 에 `get_current_user` / `oauth2_scheme` 포함
       OR 호출 chain 에서 `AuthenticationException` raise
- 403: dependency tree 에 `require_*` 가드 포함
       OR 호출 chain 에서 `AuthorizationException` raise
- 404: `route.dependant.path_params` 존재 AND 호출 chain 에서 `NotFoundException` raise
       (path param 없는 endpoint 는 NotFound 가 의미상 불가)
- 400: 호출 chain 에서 `ValidationException` / `BusinessLogicException` raise
- 422: dependant 또는 sub-dependant 에 path/query/body/form/cookie/header 입력 존재

호출 chain 분석은 라우터 모듈 + 서비스 모듈을 AST 로 파싱해 함수별
`raise <Exception>(...)` 와 attribute call (`<obj>.<method>(...)`) 을 수집한다.
서비스 메서드 이름은 본 프로젝트 내 충돌 없도록 의도 명명 (예: `get_user`
vs `get_product`) — flat name → exceptions map 으로 단순화.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.api.dependencies import get_current_user, oauth2_scheme
from app.api.permissions import (
    require_admin,
    require_self_or_admin,
    require_staff_or_admin,
)
from app.core.exceptions import (
    AuthenticationException,
    AuthorizationException,
    BusinessLogicException,
    NotFoundException,
    ValidationException,
)

_AUTH_DEPENDENCIES: frozenset[Any] = frozenset({get_current_user, oauth2_scheme})
_PERMISSION_DEPENDENCIES: frozenset[Any] = frozenset(
    {require_admin, require_self_or_admin, require_staff_or_admin}
)

_EXCEPTION_TO_STATUS: dict[str, int] = {
    AuthenticationException.__name__: 401,
    AuthorizationException.__name__: 403,
    NotFoundException.__name__: 404,
    ValidationException.__name__: 400,
    BusinessLogicException.__name__: 400,
}

_SERVICE_MODULES: tuple[str, ...] = ("app.user.service", "app.product.service")
_ROUTER_MODULES: tuple[str, ...] = ("app.user.router", "app.product.router")


def _walk_dependants(dep: Dependant) -> Iterator[Dependant]:
    yield dep
    for sub in dep.dependencies:
        yield from _walk_dependants(sub)


def _depends_on(dep: Dependant, targets: frozenset[Any]) -> bool:
    return any(d.call in targets for d in _walk_dependants(dep))


def _has_input(dep: Dependant) -> bool:
    return any(
        d.path_params
        or d.query_params
        or d.body_params
        or d.cookie_params
        or d.header_params
        for d in _walk_dependants(dep)
    )


def _collect_raises(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Raise) or child.exc is None:
            continue
        exc = child.exc
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            names.add(exc.func.id)
        elif isinstance(exc, ast.Name):
            names.add(exc.id)
    return names


def _collect_attribute_calls(node: ast.AST) -> set[str]:
    """함수 본문의 모든 `<obj>.<method>(...)` 호출의 `method` 이름 set."""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            names.add(child.func.attr)
    return names


def _parse_module(module_name: str) -> ast.Module:
    module = importlib.import_module(module_name)
    source_path = inspect.getsourcefile(module)
    assert source_path is not None, f"source not available: {module_name}"
    return ast.parse(Path(source_path).read_text())


def _iter_functions(
    node: ast.AST,
) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            yield child
        elif isinstance(child, ast.ClassDef):
            yield from _iter_functions(child)


@cache
def _service_method_exceptions() -> dict[str, set[str]]:
    """서비스 메서드 이름 → 직접 raise 하는 예외 클래스 이름 set."""
    result: dict[str, set[str]] = {}
    for module_name in _SERVICE_MODULES:
        for fn in _iter_functions(_parse_module(module_name)):
            result[fn.name] = _collect_raises(fn)
    return result


@cache
def _router_function_metadata() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """라우터 함수 이름 → (직접 raise 예외 set, attribute call 메서드 이름 set)."""
    raises: dict[str, set[str]] = {}
    calls: dict[str, set[str]] = {}
    for module_name in _ROUTER_MODULES:
        for fn in _iter_functions(_parse_module(module_name)):
            raises[fn.name] = _collect_raises(fn)
            calls[fn.name] = _collect_attribute_calls(fn)
    return raises, calls


def _endpoint_raised_exceptions(endpoint_name: str) -> set[str]:
    """라우터 함수 inline raise + 호출하는 service 메서드의 raise union."""
    router_raises, router_calls = _router_function_metadata()
    service_exceptions = _service_method_exceptions()

    excs = set(router_raises.get(endpoint_name, set()))
    for method_name in router_calls.get(endpoint_name, set()):
        excs.update(service_exceptions.get(method_name, set()))
    return excs


def resolve_status_codes(route: APIRoute) -> set[int]:
    """단일 endpoint 가 실제 응답할 수 있는 error status set 도출.

    `_inject_error_responses` (app/core/openapi.py) 가 본 결과에 해당하는
    status 만 OpenAPI 스키마에 주입 — over-spec 제거.
    """
    codes: set[int] = set()
    dep = route.dependant

    if _depends_on(dep, _AUTH_DEPENDENCIES):
        codes.add(401)
    if _depends_on(dep, _PERMISSION_DEPENDENCIES):
        codes.add(403)
    if _has_input(dep):
        codes.add(422)

    endpoint = route.endpoint
    if not hasattr(endpoint, "__name__"):
        return codes

    for exc_name in _endpoint_raised_exceptions(endpoint.__name__):
        status = _EXCEPTION_TO_STATUS.get(exc_name)
        if status is None:
            continue
        # NotFoundException 은 path_params 가 있을 때만 의미 — /me 등에선 제외
        if status == 404 and not dep.path_params:
            continue
        codes.add(status)

    return codes
