"""
사용자 관련 API 엔드포인트.
HTTP 요청을 처리하고 적절한 서비스를 호출합니다.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies import get_current_user
from app.api.permissions import require_admin, require_self_or_admin
from app.core.exceptions import AuthenticationException
from app.core.openapi import PaginatedResponse
from app.core.openapi_examples import (
    ERROR_401_AUTHENTICATION,
    ERROR_403_AUTHORIZATION,
    ERROR_404_NOT_FOUND_USER,
    ERROR_422_VALIDATION,
)
from app.core.pagination import (
    Pagination,
    build_meta,
    enforce_per_page_max,
    resolve_pagination,
    user_pagination_dep,
)
from app.core.sort import parse_sort
from app.di.providers import get_user_service
from app.user.domain import User, UserRole
from app.user.schemas import (
    Token,
    UserAdminView,
    UserCreate,
    UserListFilters,
    UserResponse,
    UserSummary,
    UserUpdate,
    build_admin_view,
    build_summary,
)
from app.user.service import UserService

router = APIRouter()


# PR #66: sort 화이트리스트. 인덱스 보유 / 외부 노출 가능한 필드만.
# `password_hash`, `hashed_password`, `full_name` (비인덱스) 등 명시 제외.
# repository 의 `_USER_SORT_COLUMN_MAP` 키와 1:1 대응 (수동 동기화).
_USER_SORT_FIELDS: frozenset[str] = frozenset(
    {"id", "email", "created_at", "updated_at", "role"}
)


# PRD §5.2 옵션 C — envelope wrap 후 최종 형식 직접 적시 (Swagger UI prefill).
# 모든 example PII 는 PRD §5.6 정책 준수 (*@example.com / dummy / 가명).
_USER_RESPONSE_EXAMPLE: dict[str, Any] = {
    "id": 1,
    "email": "newbie@example.com",
    "username": "newbie",
    "first_name": "길동",
    "last_name": "홍",
    "role": "customer",
    "is_active": True,
    "created_at": "2026-05-26T09:00:00Z",
    "updated_at": "2026-05-26T09:00:00Z",
}

CREATE_USER_RESPONSE_201_EXAMPLE: dict[str, Any] = {
    "description": "회원가입 성공 (envelope 형식)",
    "content": {"application/json": {"example": {"data": _USER_RESPONSE_EXAMPLE}}},
}

LOGIN_RESPONSE_200_EXAMPLE: dict[str, Any] = {
    "description": "OAuth2 로그인 성공 (RFC 6749 — envelope 비적용 raw 형식)",
    "content": {
        "application/json": {
            "example": {
                "access_token": (
                    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                    "eyJzdWIiOjEsImV4cCI6MTkwMDAwMDAwMH0."
                    "SAMPLE_SIGNATURE_NOT_A_REAL_TOKEN"
                ),
                "token_type": "bearer",
            }
        }
    },
}

GET_USER_RESPONSE_200_EXAMPLE: dict[str, Any] = {
    "description": (
        "사용자 단건 조회 성공 (본인: UserResponse / 관리자가 타인: UserAdminView)"
    ),
    "content": {"application/json": {"example": {"data": _USER_RESPONSE_EXAMPLE}}},
}

LIST_USERS_RESPONSE_200_EXAMPLE: dict[str, Any] = {
    "description": "사용자 목록 조회 성공 (pagination envelope — PR #52)",
    "content": {
        "application/json": {
            "example": {
                "data": [
                    {
                        "id": 1,
                        "username": "newbie",
                        "role": "customer",
                        "is_active": True,
                        "created_at": "2026-05-26T09:00:00Z",
                    },
                    {
                        "id": 2,
                        "username": "veteran",
                        "role": "staff",
                        "is_active": True,
                        "created_at": "2026-05-26T09:00:00Z",
                    },
                ],
                "meta": {"total": 2, "skip": 0, "limit": 100},
            }
        }
    },
}


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="사용자 회원가입",
    description=(
        "신규 사용자를 생성합니다. 인증 불필요 (공개 endpoint). "
        "이메일은 unique — 중복 시 409 envelope. "
        "비밀번호는 해시 저장되며 응답에 포함되지 않습니다."
    ),
    tags=["users-auth"],
    responses={
        201: CREATE_USER_RESPONSE_201_EXAMPLE,
        422: ERROR_422_VALIDATION,
    },
)
async def create_user(
    user_in: UserCreate, user_service: UserService = Depends(get_user_service)
) -> Any:
    """새 사용자를 생성합니다."""
    return await user_service.create_user(user_in.model_dump())


@router.get(
    "/me",
    response_model=UserResponse,
    summary="본인 정보 조회",
    description=(
        "현재 access token 으로 인증된 본인의 전체 정보 (PII 포함) 를 "
        "조회합니다. 인증 필요 (없으면 401 envelope)."
    ),
    tags=["users-auth"],
)
async def get_current_user_info(current_user: Any = Depends(get_current_user)) -> Any:
    """현재 인증된 사용자 정보를 조회합니다."""
    return current_user


@router.put(
    "/me",
    response_model=UserResponse,
    summary="본인 정보 수정",
    description=(
        "현재 인증된 본인의 정보를 부분 업데이트합니다. 인증 필요. "
        "전송한 필드만 반영 (partial update, `exclude_unset=True`). "
        "이메일 변경 시 unique 충돌 가능 (409 envelope)."
    ),
    tags=["users-auth"],
)
async def update_current_user(
    user_in: UserUpdate,
    current_user: Any = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> Any:
    """현재 인증된 사용자 정보를 업데이트합니다."""
    return await user_service.update_user(
        current_user.id, user_in.model_dump(exclude_unset=True)
    )


@router.post(
    "/token",
    response_model=Token,
    summary="OAuth2 토큰 로그인",
    description=(
        "OAuth2 password grant 로 access token 을 발급합니다. "
        "`username` 필드에 이메일을 사용하세요. "
        "인증 실패 시 401 envelope. "
        "응답은 RFC 6749 표준 형식 (envelope wrap 제외)."
    ),
    tags=["users-auth"],
    responses={
        200: LOGIN_RESPONSE_200_EXAMPLE,
        401: ERROR_401_AUTHENTICATION,
    },
)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    user_service: UserService = Depends(get_user_service),
) -> Any:
    """
    OAuth2 호환 토큰 로그인, username 필드에 이메일 사용.
    """
    user = await user_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise AuthenticationException("Incorrect email or password")

    access_token = user_service.create_access_token_for_user(user)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get(
    "/{user_id}",
    response_model=UserResponse | UserAdminView,
    summary="사용자 단건 조회 (본인/관리자)",
    description=(
        "특정 사용자 정보를 조회합니다. **본인 또는 관리자** 만 "
        "접근 가능 (그 외 403 envelope). "
        "본인 조회 시 `UserResponse` (전체 PII), 관리자가 타인 조회 시 "
        "`UserAdminView` (이메일 마스킹 + 이름 제외) 로 응답 분기."
    ),
    tags=["users-admin"],
    responses={
        200: GET_USER_RESPONSE_200_EXAMPLE,
        401: ERROR_401_AUTHENTICATION,
        403: ERROR_403_AUTHORIZATION,
        404: ERROR_404_NOT_FOUND_USER,
    },
)
async def get_user_by_id(
    user_id: int,
    current_user: User = Depends(require_self_or_admin),
    user_service: UserService = Depends(get_user_service),
) -> Any:
    """특정 사용자 정보를 조회합니다. 본인 또는 관리자만 접근 가능.

    - 본인 조회: `UserResponse` (전체 PII)
    - 관리자가 타인 조회: `UserAdminView` (email 마스킹 + 이름 제외)
    """
    user = await user_service.get_user(user_id)

    if current_user.id == user.id:
        return user
    return build_admin_view(user)


@router.get(
    "/",
    response_model=PaginatedResponse[UserSummary],
    response_model_exclude_none=True,
    summary="사용자 목록 조회 (관리자 전용)",
    description=(
        "사용자 목록을 페이지 단위로 조회합니다. **관리자 전용** "
        "(그 외 403 envelope). 응답은 `UserSummary` (PII 0건) — "
        "목록 페이지에서 이메일/이름 무차별 노출 차단. "
        "`{data, meta: {total, skip, limit}}` 형식."
    ),
    tags=["users-admin"],
    responses={
        200: LIST_USERS_RESPONSE_200_EXAMPLE,
        401: ERROR_401_AUTHENTICATION,
        403: ERROR_403_AUTHORIZATION,
    },
)
async def list_users(
    paging: Pagination = Depends(user_pagination_dep),
    page: int | None = Query(
        None, ge=1, description="페이지 번호 (1-indexed, page 모드)"
    ),
    per_page: int | None = Query(
        None,
        ge=1,
        description=(
            "페이지당 항목 수 (page 모드, 1 이상). 상한은 LIST_MAX_LIMIT "
            "(request 시점 평가)."
        ),
    ),
    sort: str | None = Query(
        None,
        description=(
            "정렬 (Stripe 스타일, comma 구분, '-' prefix = DESC). "
            "허용 필드: id, email, created_at, updated_at, role. "
            "예: ?sort=-created_at,email"
        ),
    ),
    role: UserRole | None = Query(None, description="역할 필터 (admin/staff/customer)"),
    is_active: bool | None = Query(None, description="활성 상태 필터"),
    q: str | None = Query(
        None,
        min_length=1,
        max_length=100,
        description=(
            "email / username / first_name / last_name 부분일치 검색 "
            "(case-insensitive, LIKE 메타문자 자동 escape)"
        ),
    ),
    _: Any = Depends(require_admin),
    user_service: UserService = Depends(get_user_service),
) -> Any:
    """사용자 목록을 조회합니다. 관리자 전용.

    응답은 `UserSummary` (PII 0건) — 목록 페이지에서 이메일/이름 무차별 노출 차단.

    페이징 듀얼 모드 (PR #64):
    - offset 모드 (default, `?skip=&limit=`): meta = {total, skip, limit}
    - page 모드 (`?page=&per_page=`): meta = {total, page, per_page, total_pages}
    - 동시 제공 시 page 우선 (skip/limit silent 무시).

    limit / per_page default 와 max 는 환경 변수 (PR ##):
    - `USER_LIST_DEFAULT_LIMIT` (default 100)
    - `LIST_MAX_LIMIT` (default 1000, offset/page 모드 공통 상한)

    filter/sort 표준화 (PR #66):
    - `?sort=field,-field2` (Stripe 스타일, multi-sort 입력 순서 보존)
    - `?role=&is_active=&q=` 평이한 query (bracket / DSL 회피)
    - count 는 filter 반영 / sort 무관 (PR #52 연장)
    """
    enforce_per_page_max(per_page)
    sort_fields = parse_sort(sort, _USER_SORT_FIELDS)
    effective_skip, effective_limit, mode = resolve_pagination(
        skip=paging.skip, limit=paging.limit, page=page, per_page=per_page
    )
    users, total = await user_service.list_users(
        skip=effective_skip,
        limit=effective_limit,
        filters=UserListFilters(role=role, is_active=is_active, q=q),
        sort=sort_fields,
    )
    return {
        "data": [build_summary(u) for u in users],
        "meta": build_meta(
            total=total,
            mode=mode,
            skip=effective_skip,
            limit=effective_limit,
            page=page,
            per_page=per_page,
        ),
    }
