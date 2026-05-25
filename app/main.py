# app/main.py

"""
애플리케이션 진입점.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import (
    AccessLogMiddleware,
    RequestIDMiddleware,
    SuccessEnvelopeMiddleware,
)
from app.core.observability import setup_sentry
from app.core.openapi import OPENAPI_TAGS, customize_openapi
from app.di.containers import Container

# 로깅 단일 진입점 — sink/포맷/레벨 환경 변수 기반 구성
setup_logging()

# 관측성 단일 진입점 — SENTRY_DSN 빈 값 시 no-op (개발/테스트 0 영향).
# setup_logging() 직후 호출 — loguru sink 가 먼저 구성되어야
# LoguruIntegration 이 hook 가능.
setup_sentry()

# 의존성 주입 컨테이너 초기화
container = Container()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    애플리케이션 라이프사이클 이벤트 처리를 위한 lifespan 컨텍스트 매니저.

    스키마는 alembic 으로 관리한다 (`uv run alembic upgrade head`).
    """
    yield  # 애플리케이션 실행

    # 종료 시 실행 (shutdown)
    if container.db.initialized:
        scoped_session = container.db()
        await scoped_session.remove()

    # Sentry transport queue flush — DSN 빈 값 시 no-op (sentry_sdk default).
    # graceful shutdown 시점에 진행 중 event 손실 차단 (PRD §8 리스크).
    sentry_sdk.flush(timeout=2)


# 애플리케이션 생성
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    openapi_tags=OPENAPI_TAGS,  # PR #63 — Swagger UI 그룹화 (4 tags 권한 경계)
    lifespan=lifespan,  # lifespan 컨텍스트 매니저 설정
)

# 도메인 예외 → HTTP status 자동 변환 (단일 진실원: app/core/exceptions.py)
register_exception_handlers(app)

# OpenAPI 스키마 envelope 적용 (PR #51) — middleware ↔ OpenAPI 단일 진실원.
# success {"data": <T>} wrap + error envelope 일괄 주입 (라우터 변경 0).
# FastAPI 공식 custom_openapi 패턴 — bound method 재할당이라 mypy ignore.
app.openapi = lambda: customize_openapi(app)  # type: ignore[method-assign]

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 미들웨어 wrap 순서 (outermost → inner):
#   RequestID → AccessLog → SuccessEnvelope → CORS.
# Starlette `add_middleware` 는 add 역순 wrap (마지막에 add 한 것이 outermost)
# 이므로 등록 순서는 inner 먼저: CORS (이미 등록) → SuccessEnvelope → AccessLog
# → RequestID. AccessLog 가 RequestID 안쪽이어야 contextvar 가 살아있을 때
# logger 호출되어 request_id 가 access log 에도 첨부된다. SuccessEnvelope 는
# 라우터에 가장 가까운 안쪽 (CORS 다음) 에 위치 — 응답 body 변환만 담당하고
# 헤더/로깅/contextvar 는 outer 가 처리.
app.add_middleware(SuccessEnvelopeMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestIDMiddleware)

# 컨테이너 설정 — FastAPI 공식 패턴 (app.state).
app.state.container = container

# API 라우터 포함
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root() -> dict[str, str]:
    """
    루트 엔드포인트.
    """
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "version": settings.VERSION,
        "docs": f"{settings.API_V1_STR}/docs",
    }
