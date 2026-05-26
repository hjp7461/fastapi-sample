"""
애플리케이션 설정.
"""

import os

from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

# .env 파일 로드
load_dotenv()


class Settings(BaseSettings):
    """
    애플리케이션 설정 클래스.
    환경 변수에서 값을 로드합니다.
    """

    # 기본 설정
    PROJECT_NAME: str = "FastAPI Clean Architecture"
    PROJECT_DESCRIPTION: str = "FastAPI 클린 아키텍처 예제 애플리케이션"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # 보안 설정
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-for-jwt")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    BCRYPT_ROUNDS: int = int(os.getenv("BCRYPT_ROUNDS", "12"))

    # 데이터베이스 설정
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app.db")
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"

    # 응답 PII 정책 — UserAdminView (관리자→타인 조회) 의 email 마스킹.
    # 기본 True (운영 안전). 개발 환경에서 `false` 명시 시 raw 노출.
    USER_ADMIN_EMAIL_MASKING: bool = (
        os.getenv("USER_ADMIN_EMAIL_MASKING", "true").lower() == "true"
    )

    # 로깅 설정 — loguru sink/포맷 (app/core/logging.py::setup_logging 가 사용).
    # default 는 기존 동작 호환 (stderr / INFO / text / file 비활성).
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "text")
    LOG_FILE: str | None = os.getenv("LOG_FILE") or None
    LOG_FILE_ROTATION: str = os.getenv("LOG_FILE_ROTATION", "10 MB")
    LOG_FILE_RETENTION: str = os.getenv("LOG_FILE_RETENTION", "7 days")

    # 관측성 설정 — Sentry (app/core/observability.py::setup_sentry 가 참조).
    # default 는 비활성 (SENTRY_DSN 빈 값) → 개발/테스트 영향 0.
    # 운영 활성화는 .env 의 DSN 설정 + sample_rate 조정만 필요.
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    SENTRY_ENVIRONMENT: str = os.getenv("SENTRY_ENVIRONMENT", "development")
    SENTRY_TRACES_SAMPLE_RATE: float = Field(
        default=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        ge=0.0,
        le=1.0,
        description="Sentry Performance — 0.0 비활성, 운영 권장 0.1, staging 1.0",
    )
    SENTRY_PROFILES_SAMPLE_RATE: float = Field(
        default=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0")),
        ge=0.0,
        le=1.0,
        description=(
            "Sentry Profiling — 0.0 비활성. Performance 가 활성화된 경우만 수집"
        ),
    )
    SENTRY_RELEASE: str | None = os.getenv("SENTRY_RELEASE") or None
    SENTRY_SEND_PII: bool = os.getenv("SENTRY_SEND_PII", "false").lower() == "true"

    # audit log 설정 — app/audit/recorder.py::record_audit 가 참조.
    # default True (운영 안전). 테스트는 fixture override 로 별도 검증.
    # false 설정 시 record_audit() 가 즉시 return (no-op) — 본 작업 영향 0.
    AUDIT_ENABLED: bool = os.getenv("AUDIT_ENABLED", "true").lower() == "true"

    # CORS 설정
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",  # React 앱
        "http://localhost:8000",  # FastAPI 앱
    ]

    # list endpoint 페이징 정책 (PR #52 / PR #64 후속).
    # default 는 자원별, max 는 DoS 가드 단일 기준.
    # offset 모드 limit + page 모드 per_page 양쪽에 동일 max 적용.
    USER_LIST_DEFAULT_LIMIT: int = Field(
        default=100,
        gt=0,
        description="GET /users/ 의 limit default (운영자 정책 — 예: 50/100/200)",
    )
    PRODUCT_LIST_DEFAULT_LIMIT: int = Field(
        default=100,
        gt=0,
        description="GET /products/ 의 limit default — 카탈로그 크기 정책",
    )
    LIST_MAX_LIMIT: int = Field(
        default=1000,
        gt=0,
        description="모든 list endpoint 의 limit / per_page 상한 (DoS 가드)",
    )

    @field_validator("BCRYPT_ROUNDS")
    @classmethod
    def validate_bcrypt_rounds(cls, v: int) -> int:
        """bcrypt 표준 범위 검증 (4 ≤ rounds ≤ 31)."""
        if not (4 <= v <= 31):
            raise ValueError(f"BCRYPT_ROUNDS must be between 4 and 31, got {v}")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """loguru 가 인식하는 표준 레벨만 허용."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}, got {v!r}")
        return upper

    @field_validator("LOG_FORMAT")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """text (개발/사람) vs json (운영/수집 파이프라인)."""
        allowed = {"text", "json"}
        lower = v.lower()
        if lower not in allowed:
            raise ValueError(f"LOG_FORMAT must be one of {sorted(allowed)}, got {v!r}")
        return lower

    @model_validator(mode="after")
    def _validate_list_limits(self) -> "Settings":
        """자원별 default ≤ 공통 max — 잘못된 설정 fail-fast."""
        for name, value in (
            ("USER_LIST_DEFAULT_LIMIT", self.USER_LIST_DEFAULT_LIMIT),
            ("PRODUCT_LIST_DEFAULT_LIMIT", self.PRODUCT_LIST_DEFAULT_LIMIT),
        ):
            if value > self.LIST_MAX_LIMIT:
                raise ValueError(
                    f"{name}={value} must be <= LIST_MAX_LIMIT={self.LIST_MAX_LIMIT}"
                )
        return self

    model_config = {"env_file": ".env", "case_sensitive": True}


# 설정 인스턴스 생성
settings = Settings()
