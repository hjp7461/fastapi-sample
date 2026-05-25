"""
전체 API 라우터 통합.
"""

from fastapi import APIRouter

from app.product.router import router as product_router
from app.user.router import router as user_router

# 메인 API 라우터
api_router = APIRouter()

# 각 모듈의 라우터 포함 (PR #63 — default tag 제거, endpoint 별 명시 override).
# 권한 경계 (users-auth / users-admin / products-public / products-admin) 단위로
# Swagger UI 그룹화 + 외부 SDK namespace 분리.
api_router.include_router(user_router, prefix="/users")
api_router.include_router(product_router, prefix="/products")
