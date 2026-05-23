"""
상품 관련 API 엔드포인트.
HTTP 요청을 처리하고 적절한 서비스를 호출합니다.
"""
from typing import List, Optional, Any, Union

from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.exceptions import NotFoundException, ValidationException, BusinessLogicException
from app.di.providers import get_product_service
from app.api.dependencies import (
    get_current_active_admin,
    get_current_user,
    get_optional_current_user,
)
from app.product.schemas import (
    ProductCreate,
    ProductInventoryUpdate,
    ProductPublicView,
    ProductResponse,
    ProductUpdate,
    build_public_view,
)
from app.product.domain import ProductCategory
from app.product.service import ProductService
from app.user.domain import User


router = APIRouter()


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_in: ProductCreate,
    product_service: ProductService = Depends(get_product_service),
    current_user: Any = Depends(get_current_active_admin)
) -> Any:
    """새 상품을 생성합니다. (관리자 전용)"""
    try:
        product = await product_service.create_product(product_in.model_dump())
        return product
    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{product_id}", response_model=Union[ProductPublicView, ProductResponse])
async def get_product_by_id(
    product_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    product_service: ProductService = Depends(get_product_service),
) -> Any:
    """특정 상품 정보를 조회합니다.

    - viewer 가 staff/admin → `ProductResponse` (전체, inventory 포함)
    - 그 외 (anonymous / 일반 사용자) → `ProductPublicView` (inventory 제외)
    """
    try:
        product = await product_service.get_product(product_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    if current_user is not None and current_user.is_staff_or_above():
        return product
    return build_public_view(product)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    product_in: ProductUpdate,
    product_service: ProductService = Depends(get_product_service),
    current_user: Any = Depends(get_current_active_admin)
) -> Any:
    """상품 정보를 업데이트합니다. (관리자 전용)"""
    try:
        return await product_service.update_product(
            product_id,
            product_in.model_dump(exclude_unset=True)
        )
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    product_service: ProductService = Depends(get_product_service),
    current_user: Any = Depends(get_current_active_admin)
) -> None:
    """상품을 삭제합니다. (관리자 전용)"""
    try:
        await product_service.delete_product(product_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get(
    "/",
    response_model=Union[List[ProductResponse], List[ProductPublicView]],
)
async def list_products(
    skip: int = 0,
    limit: int = 100,
    category: Optional[ProductCategory] = None,
    is_active: Optional[bool] = Query(None, description="활성화 상태 필터링"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    product_service: ProductService = Depends(get_product_service),
) -> Any:
    """상품 목록을 조회합니다.

    - viewer 가 staff/admin → `List[ProductResponse]` (전체)
    - 그 외 (anonymous / 일반 사용자) → `List[ProductPublicView]` (inventory 제외)
    """
    products = await product_service.list_products(
        skip=skip,
        limit=limit,
        category=category,
        is_active=is_active,
    )
    if current_user is not None and current_user.is_staff_or_above():
        return products
    return [build_public_view(p) for p in products]


@router.patch("/{product_id}/inventory", response_model=ProductResponse)
async def update_product_inventory(
    product_id: int,
    inventory_update: ProductInventoryUpdate,
    product_service: ProductService = Depends(get_product_service),
    current_user: Any = Depends(get_current_active_admin)
) -> Any:
    """상품 재고를 업데이트합니다. (관리자 전용)"""
    try:
        return await product_service.update_inventory(
            product_id,
            inventory_update.quantity_change
        )
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except BusinessLogicException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )