"""
애플리케이션 설정.
"""
import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

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

    # 데이터베이스 설정
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app.db")
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"
    AUTO_CREATE_TABLES: bool = os.getenv("AUTO_CREATE_TABLES", "true").lower() == "true"

    # CORS 설정
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",  # React 앱
        "http://localhost:8000",  # FastAPI 앱
    ]

    model_config = {
        "env_file": ".env",
        "case_sensitive": True
    }


# 설정 인스턴스 생성
settings = Settings()