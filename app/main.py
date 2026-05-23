# app/main.py

"""
애플리케이션 진입점.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.middleware import AccessLogMiddleware, RequestIDMiddleware
from app.di.containers import Container

# 로깅 단일 진입점 — sink/포맷/레벨 환경 변수 기반 구성
setup_logging()

# 의존성 주입 컨테이너 초기화
container = Container()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    애플리케이션 라이프사이클 이벤트 처리를 위한 lifespan 컨텍스트 매니저.

    스키마는 alembic 으로 관리한다 (`uv run alembic upgrade head`).
    """
    yield  # 애플리케이션 실행

    # 종료 시 실행 (shutdown)
    if container.db.initialized:
        scoped_session = container.db()
        await scoped_session.remove()


# 애플리케이션 생성
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,  # lifespan 컨텍스트 매니저 설정
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 미들웨어 wrap 순서 (outermost → inner): RequestID → AccessLog → CORS.
# Starlette `add_middleware` 는 add 역순 wrap (마지막에 add 한 것이 outermost) 이므로
# 등록 순서는 inner 먼저: CORS (이미 등록) → AccessLog → RequestID.
# AccessLog 가 RequestID 안쪽이어야 contextvar 가 살아있을 때 logger 호출되어
# request_id 가 access log 에도 첨부된다.
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestIDMiddleware)

# 컨테이너 설정
app.container = container

# API 라우터 포함
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    """
    루트 엔드포인트.
    """
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "version": settings.VERSION,
        "docs": f"{settings.API_V1_STR}/docs",
    }
