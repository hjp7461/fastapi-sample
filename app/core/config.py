"""
애플리케이션 설정.
"""

import os
from typing import List

from dotenv import load_dotenv
from pydantic import field_validator
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

    # CORS 설정
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",  # React 앱
        "http://localhost:8000",  # FastAPI 앱
    ]

    @field_validator("BCRYPT_ROUNDS")
    @classmethod
    def validate_bcrypt_rounds(cls, v: int) -> int:
        """bcrypt 표준 범위 검증 (4 ≤ rounds ≤ 31)."""
        if not (4 <= v <= 31):
            raise ValueError(f"BCRYPT_ROUNDS must be between 4 and 31, got {v}")
        return v

    model_config = {"env_file": ".env", "case_sensitive": True}


# 설정 인스턴스 생성
settings = Settings()
