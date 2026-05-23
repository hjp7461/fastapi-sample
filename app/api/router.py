"""
전체 API 라우터 통합.
"""

from fastapi import APIRouter

from app.product.router import router as product_router
from app.user.router import router as user_router

# 메인 API 라우터
api_router = APIRouter()

# 각 모듈의 라우터 포함
api_router.include_router(user_router, prefix="/users", tags=["users"])
api_router.include_router(product_router, prefix="/products", tags=["products"])
