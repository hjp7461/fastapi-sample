"""
사용자 서비스 구현.
비즈니스 로직과 유즈케이스를 포함합니다.
"""

from datetime import timedelta
from typing import Any

from loguru import logger

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import (
    _extract_bcrypt_rounds,
    create_access_token,
    get_password_hash,
    verify_password,
)
from app.user.domain import NewUser, User, UserRole
from app.user.repository import UserRepository


class UserService:
    """
    사용자 관련 비즈니스 로직을 처리하는 서비스.
    """

    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    async def authenticate_user(self, email: str, password: str) -> User | None:
        """사용자 인증을 처리합니다.

        verify 성공 후 저장된 해시의 라운드를 검사해 다음 정책을 적용한다.
        - stored < configured (업그레이드): 백그라운드로 재해시. 실패해도 인증은 성공.
        - stored > configured (다운그레이드): 약화 차단. logger.warning 으로 가시화만.
        - stored == configured 또는 파싱 실패: 무처리.
        """
        user = await self.user_repository.get_by_email(email)
        # user.id 는 도메인이 not None 보장 (PR #38). hashed_password 는 OAuth /
        # 외부 로그인 시나리오에서 None 가능 → narrow 유지.
        if not user or not user.hashed_password:
            return None
        if not verify_password(password, user.hashed_password):
            return None

        stored_rounds = _extract_bcrypt_rounds(user.hashed_password)
        configured = settings.BCRYPT_ROUNDS

        if stored_rounds is not None and stored_rounds < configured:
            try:
                new_hash = get_password_hash(password)
                await self.user_repository.update(
                    user.id, {"hashed_password": new_hash}
                )
                user.hashed_password = new_hash
            except Exception:
                # 재해시 실패는 인증 자체를 막지 않는다.
                logger.exception(
                    "rehash failed (user_id={}, stored={}, configured={})",
                    user.id,
                    stored_rounds,
                    configured,
                )
        elif stored_rounds is not None and stored_rounds > configured:
            logger.warning(
                "rehash skipped: downgrade detected "
                "(user_id={}, stored={}, configured={})",
                user.id,
                stored_rounds,
                configured,
            )

        return user

    async def create_user(self, user_data: dict[str, Any]) -> User:
        """새 사용자를 생성합니다."""
        # 이메일 중복 확인
        existing_user = await self.user_repository.get_by_email(user_data["email"])
        if existing_user:
            raise ValidationException("이미 사용 중인 이메일입니다.")

        # 비밀번호 해싱
        hashed_password = get_password_hash(user_data.pop("password"))

        # 신규 사용자 객체 생성 (DB save 이전 상태)
        new_user = NewUser(
            email=user_data["email"],
            username=user_data["username"],
            hashed_password=hashed_password,
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            role=user_data.get("role", UserRole.CUSTOMER),
            is_active=user_data.get("is_active", True),
        )

        # 저장 및 반환 (User 로 변환됨)
        return await self.user_repository.create(new_user)

    async def get_user(self, user_id: int) -> User:
        """ID로 사용자를 조회합니다."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"User with ID {user_id} not found")
        return user

    async def update_user(self, user_id: int, user_data: dict[str, Any]) -> User:
        """사용자 정보를 업데이트합니다."""
        # 비밀번호가 있으면 해싱
        if user_data.get("password"):
            user_data["hashed_password"] = get_password_hash(user_data.pop("password"))

        # 업데이트 실행
        user = await self.user_repository.update(user_id, user_data)
        if not user:
            raise NotFoundException(f"User with ID {user_id} not found")

        return user

    async def delete_user(self, user_id: int) -> bool:
        """사용자를 삭제합니다."""
        # 삭제 전 존재 확인
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"User with ID {user_id} not found")

        return await self.user_repository.delete(user_id)

    async def list_users(
        self, skip: int = 0, limit: int = 100
    ) -> tuple[list[User], int]:
        """사용자 목록 + 전체 카운트 (pagination meta 용, PR #52)."""
        items = await self.user_repository.list(skip, limit)
        total = await self.user_repository.count()
        return items, total

    def create_access_token_for_user(
        self, user: User | int, expires_delta: timedelta | None = None
    ) -> str:
        """사용자를 위한 액세스 토큰을 생성합니다."""
        user_id = user.id if isinstance(user, User) else user

        if not expires_delta:
            expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        return create_access_token(subject=user_id, expires_delta=expires_delta)
