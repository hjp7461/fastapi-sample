"""
보안 관련 유틸리티 함수.
암호화, 토큰 생성 및 검증 등을 포함합니다.
"""

# from datetime import datetime, timedelta
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """입력 비밀번호가 해시와 일치하는지 검증.

    해시 포맷이 잘못된 경우 (짧은 문자열, 알 수 없는 알고리즘 등) 에는
    bcrypt 가 ValueError 를 던지므로 안전하게 False 로 변환한다.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        return False


def get_password_hash(password: str) -> str:
    """비밀번호를 bcrypt 로 해시 (UTF-8 인코딩, settings.BCRYPT_ROUNDS 라운드).

    bcrypt 는 입력의 72 바이트를 초과하는 부분을 무시한다. Pydantic
    스키마에서 `max_length=64` 로 제한하므로 영문 비밀번호 기준 안전 범위.

    라운드는 settings.BCRYPT_ROUNDS 에서 가져온다 (기본 12, 환경 변수로 override).
    """
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def _extract_bcrypt_rounds(hashed_password: str) -> int | None:
    """bcrypt 해시 (`$2b$<rounds>$<salt+hash>`) 에서 라운드 수를 추출.

    파싱 실패 시 None — 호출자가 보수적 처리한다.
    """
    try:
        return int(hashed_password.split("$")[2])
    except (IndexError, ValueError):
        return None


def needs_rehash(hashed_password: str) -> bool:
    """저장된 해시의 라운드가 현재 settings.BCRYPT_ROUNDS 보다 낮은지 확인.

    "낮은 경우에만" True — 업그레이드 (예: 12 → 13) 만 재해시 대상이고
    다운그레이드 (예: 13 → 12) 는 보안 약화이므로 차단. 운영자가
    BCRYPT_ROUNDS 를 낮춰도 이미 저장된 강한 해시를 자동 약화시키지 않는다.

    파싱 실패 시 보수적으로 False (재해시 안 함) — 인증 흐름 깨지지 않도록.

    True 면 lazy rehash 대상 (authenticate_user 에서 자동 업그레이드).
    """
    stored = _extract_bcrypt_rounds(hashed_password)
    if stored is None:
        return False
    return stored < settings.BCRYPT_ROUNDS


def create_access_token(
    subject: str | Any, expires_delta: timedelta | None = None
) -> str:
    """
    JWT 액세스 토큰을 생성합니다.

    Args:
        subject: 토큰의 주체 (일반적으로 사용자 ID)
        expires_delta: 토큰의 만료 기간

    Returns:
        str: 인코딩된 JWT 토큰
    """
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """
    JWT 액세스 토큰을 디코딩합니다.

    Args:
        token: 디코딩할 JWT 토큰

    Returns:
        Dict: 디코딩된 토큰 페이로드

    Raises:
        jwt.PyJWTError: 토큰이 유효하지 않을 경우
    """
    payload: dict[str, Any] = jwt.decode(
        token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
    )
    return payload
