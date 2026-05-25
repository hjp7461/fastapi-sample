"""
상품 관련 API 엔드포인트.
HTTP 요청을 처리하고 적절한 서비스를 호출합니다.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_optional_current_user
from app.api.permissions import require_staff_or_admin
from app.core.openapi import PaginatedResponse
from app.core.openapi_examples import (
    ERROR_401_AUTHENTICATION,
    ERROR_403_AUTHORIZATION,
    ERROR_404_NOT_FOUND_PRODUCT,
    ERROR_422_VALIDATION,
)
from app.core.pagination import build_meta, resolve_pagination
from app.di.providers import get_product_service
from app.product.domain import ProductCategory
from app.product.schemas import (
    ProductCreate,
    ProductInventoryUpdate,
    ProductPublicView,
    ProductResponse,
    ProductUpdate,
    build_public_view,
)
from app.product.service import ProductService
from app.user.domain import User

router = APIRouter()


# PRD §5.2 옵션 C — envelope wrap 후 최종 형식 직접 적시. PII 정책: PRD §5.6.
_PRODUCT_RESPONSE_EXAMPLE: dict[str, Any] = {
    "id": 42,
    "name": "샘플 머그컵",
    "description": "테스트용 머그컵 (회귀 가드 sample).",
    "price": "12000.00",
    "category": "other",
    "inventory": 50,
    "is_active": True,
    "created_at": "2026-05-26T09:00:00Z",
    "updated_at": "2026-05-26T09:00:00Z",
}

_PRODUCT_PUBLIC_VIEW_EXAMPLE: dict[str, Any] = {
    "id": 42,
    "name": "샘플 머그컵",
    "description": "테스트용 머그컵 (회귀 가드 sample).",
    "price": "12000.00",
    "category": "other",
    "is_active": True,
    "created_at": "2026-05-26T09:00:00Z",
    "updated_at": "2026-05-26T09:00:00Z",
}

CREATE_PRODUCT_RESPONSE_201_EXAMPLE: dict[str, Any] = {
    "description": "상품 생성 성공 (envelope 형식)",
    "content": {"application/json": {"example": {"data": _PRODUCT_RESPONSE_EXAMPLE}}},
}

UPDATE_PRODUCT_RESPONSE_200_EXAMPLE: dict[str, Any] = {
    "description": "상품 수정 성공 (envelope 형식)",
    "content": {
        "application/json": {
            "example": {
                "data": {
                    **_PRODUCT_RESPONSE_EXAMPLE,
                    "price": "13500.00",
                    "updated_at": "2026-05-26T10:30:00Z",
                }
            }
        }
    },
}

GET_PRODUCT_RESPONSE_200_EXAMPLE: dict[str, Any] = {
    "description": (
        "상품 단건 조회 성공 (anonymous/customer: ProductPublicView, "
        "staff/admin: ProductResponse)"
    ),
    "content": {
        "application/json": {"example": {"data": _PRODUCT_PUBLIC_VIEW_EXAMPLE}}
    },
}

UPDATE_INVENTORY_RESPONSE_200_EXAMPLE: dict[str, Any] = {
    "description": "재고 변경 성공 (envelope 형식)",
    "content": {
        "application/json": {
            "example": {
                "data": {
                    **_PRODUCT_RESPONSE_EXAMPLE,
                    "inventory": 47,
                    "updated_at": "2026-05-26T11:15:00Z",
                }
            }
        }
    },
}


@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="상품 생성 (staff/admin)",
    description=(
        "신규 상품을 생성합니다. **staff 또는 admin** 만 접근 가능 "
        "(그 외 403 envelope). SKU 는 unique — 중복 시 409 envelope."
    ),
    tags=["products-admin"],
    responses={
        201: CREATE_PRODUCT_RESPONSE_201_EXAMPLE,
        401: ERROR_401_AUTHENTICATION,
        403: ERROR_403_AUTHORIZATION,
        422: ERROR_422_VALIDATION,
    },
)
async def create_product(
    product_in: ProductCreate,
    product_service: ProductService = Depends(get_product_service),
    current_user: Any = Depends(require_staff_or_admin),
) -> Any:
    """새 상품을 생성합니다. (staff/admin 전용)"""
    return await product_service.create_product(product_in.model_dump())


@router.get(
    "/{product_id}",
    response_model=ProductPublicView | ProductResponse,
    summary="상품 단건 조회 (viewer 분기)",
    description=(
        "특정 상품 정보를 조회합니다. 인증 불필요 (공개). "
        "viewer 가 staff/admin 인 경우 `ProductResponse` (inventory 포함), "
        "그 외 (anonymous / 일반 사용자) 는 `ProductPublicView` "
        "(inventory 제외) 로 응답 분기."
    ),
    tags=["products-public"],
    responses={
        200: GET_PRODUCT_RESPONSE_200_EXAMPLE,
        404: ERROR_404_NOT_FOUND_PRODUCT,
    },
)
async def get_product_by_id(
    product_id: int,
    current_user: User | None = Depends(get_optional_current_user),
    product_service: ProductService = Depends(get_product_service),
) -> Any:
    """특정 상품 정보를 조회합니다.

    - viewer 가 staff/admin → `ProductResponse` (전체, inventory 포함)
    - 그 외 (anonymous / 일반 사용자) → `ProductPublicView` (inventory 제외)
    """
    product = await product_service.get_product(product_id)

    if current_user is not None and current_user.is_staff_or_above():
        return product
    return build_public_view(product)


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    summary="상품 정보 수정 (staff/admin)",
    description=(
        "상품 정보를 부분 업데이트합니다. **staff 또는 admin** 만 "
        "접근 가능 (그 외 403 envelope). 전송한 필드만 반영 (partial update). "
        "재고 (`inventory_count`) 변경은 본 endpoint 가 아닌 "
        "`/inventory` PATCH 사용 권장 (원자성)."
    ),
    tags=["products-admin"],
    responses={
        200: UPDATE_PRODUCT_RESPONSE_200_EXAMPLE,
        401: ERROR_401_AUTHENTICATION,
        403: ERROR_403_AUTHORIZATION,
        404: ERROR_404_NOT_FOUND_PRODUCT,
    },
)
async def update_product(
    product_id: int,
    product_in: ProductUpdate,
    product_service: ProductService = Depends(get_product_service),
    current_user: Any = Depends(require_staff_or_admin),
) -> Any:
    """상품 정보를 업데이트합니다. (staff/admin 전용)"""
    return await product_service.update_product(
        product_id, product_in.model_dump(exclude_unset=True)
    )


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="상품 삭제 (staff/admin)",
    description=(
        "상품을 삭제합니다 (hard delete). **staff 또는 admin** 만 "
        "접근 가능 (그 외 403 envelope). "
        "성공 시 204 No Content (응답 body 없음)."
    ),
    tags=["products-admin"],
)
async def delete_product(
    product_id: int,
    product_service: ProductService = Depends(get_product_service),
    current_user: Any = Depends(require_staff_or_admin),
) -> None:
    """상품을 삭제합니다. (staff/admin 전용)"""
    await product_service.delete_product(product_id)


@router.get(
    "/",
    # union 을 PaginatedResponse 외부가 아닌 inner item T 에 둠 —
    # Pydantic smart-mode 가 각 item 단위로 PublicView vs Response 매칭.
    # PublicView 가 먼저 (좁은 스키마: inventory 없음 우선 매치).
    response_model=PaginatedResponse[ProductPublicView | ProductResponse],
    response_model_exclude_none=True,
    summary="상품 목록 조회 (viewer 분기)",
    description=(
        "상품 목록을 페이지 단위로 조회합니다. 인증 불필요 (공개). "
        "viewer 가 staff/admin 이면 `PaginatedResponse[ProductResponse]` "
        "(inventory 포함), 그 외는 `PaginatedResponse[ProductPublicView]` "
        "(inventory 제외). `category`, `is_active` 쿼리 파라미터로 필터링 가능. "
        "`{data, meta: {total, skip, limit}}` 형식."
    ),
    tags=["products-public"],
)
async def list_products(
    skip: int = Query(0, ge=0, description="페이징 offset (offset 모드, 0 이상)"),
    limit: int = Query(
        100, ge=1, le=1000, description="페이지 크기 (offset 모드, 1~1000)"
    ),
    page: int | None = Query(
        None, ge=1, description="페이지 번호 (1-indexed, page 모드)"
    ),
    per_page: int | None = Query(
        None,
        ge=1,
        le=1000,
        description="페이지당 항목 수 (page 모드, 1~1000)",
    ),
    category: ProductCategory | None = None,
    is_active: bool | None = Query(None, description="활성화 상태 필터링"),
    current_user: User | None = Depends(get_optional_current_user),
    product_service: ProductService = Depends(get_product_service),
) -> Any:
    """상품 목록을 조회합니다.

    - viewer 가 staff/admin → `PaginatedResponse[ProductResponse]` (전체)
    - 그 외 (anonymous / 일반 사용자) → `PaginatedResponse[ProductPublicView]`
      (inventory 제외)

    페이징 듀얼 모드 (PR ##):
    - offset 모드 (default, `?skip=&limit=`): meta = {total, skip, limit}
    - page 모드 (`?page=&per_page=`): meta = {total, page, per_page, total_pages}
    - 동시 제공 시 page 우선 (skip/limit silent 무시).
    """
    effective_skip, effective_limit, mode = resolve_pagination(
        skip=skip, limit=limit, page=page, per_page=per_page
    )
    products, total = await product_service.list_products(
        skip=effective_skip,
        limit=effective_limit,
        category=category,
        is_active=is_active,
    )
    meta = build_meta(
        total=total,
        mode=mode,
        skip=effective_skip,
        limit=effective_limit,
        page=page,
        per_page=per_page,
    )
    if current_user is not None and current_user.is_staff_or_above():
        return {"data": products, "meta": meta}
    return {"data": [build_public_view(p) for p in products], "meta": meta}


@router.patch(
    "/{product_id}/inventory",
    response_model=ProductResponse,
    summary="상품 재고 변경 (staff/admin, 원자적)",
    description=(
        "상품 재고를 원자적으로 변경합니다 (delta 기반). "
        "**staff 또는 admin** 만 접근 가능 (그 외 403 envelope). "
        "`quantity_change` 가 양수면 증가, 음수면 감소. "
        "결과 재고가 음수가 되면 400 envelope. "
        "DB row lock 으로 동시성 안전."
    ),
    tags=["products-admin"],
    responses={
        200: UPDATE_INVENTORY_RESPONSE_200_EXAMPLE,
        401: ERROR_401_AUTHENTICATION,
        403: ERROR_403_AUTHORIZATION,
        404: ERROR_404_NOT_FOUND_PRODUCT,
        422: ERROR_422_VALIDATION,
    },
)
async def update_product_inventory(
    product_id: int,
    inventory_update: ProductInventoryUpdate,
    product_service: ProductService = Depends(get_product_service),
    current_user: Any = Depends(require_staff_or_admin),
) -> Any:
    """상품 재고를 업데이트합니다. (staff/admin 전용)"""
    return await product_service.update_inventory(
        product_id, inventory_update.quantity_change
    )
