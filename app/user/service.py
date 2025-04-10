"""
사용자 서비스 구현.
비즈니스 로직과 유즈케이스를 포함합니다.
"""
from typing import List, Optional, Dict, Any, Union
from datetime import timedelta

from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.user.domain import User, UserRole
from app.user.repository import UserRepository


class UserService:
    """
    사용자 관련 비즈니스 로직을 처리하는 서비스.
    """

    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """사용자 인증을 처리합니다."""
        user = await self.user_repository.get_by_email(email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def create_user(self, user_data: Dict[str, Any]) -> User:
        """새 사용자를 생성합니다."""
        # 이메일 중복 확인
        existing_user = await self.user_repository.get_by_email(user_data["email"])
        if existing_user:
            raise ValidationException("이미 사용 중인 이메일입니다.")

        # 비밀번호 해싱
        hashed_password = get_password_hash(user_data.pop("password"))

        # 사용자 객체 생성
        user = User(
            email=user_data["email"],
            username=user_data["username"],
            hashed_password=hashed_password,
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            role=user_data.get("role", UserRole.CUSTOMER),
            is_active=user_data.get("is_active", True)
        )

        # 저장 및 반환
        return await self.user_repository.create(user)

    async def get_user(self, user_id: int) -> User:
        """ID로 사용자를 조회합니다."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"User with ID {user_id} not found")
        return user

    async def update_user(self, user_id: int, user_data: Dict[str, Any]) -> User:
        """사용자 정보를 업데이트합니다."""
        # 비밀번호가 있으면 해싱
        if "password" in user_data and user_data["password"]:
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

    async def list_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        """사용자 목록을 조회합니다."""
        return await self.user_repository.list(skip, limit)

    def create_access_token_for_user(
            self, user: Union[User, int], expires_delta: Optional[timedelta] = None
    ) -> str:
        """사용자를 위한 액세스 토큰을 생성합니다."""
        user_id = user.id if isinstance(user, User) else user

        if not expires_delta:
            expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        return create_access_token(
            subject=user_id,
            expires_delta=expires_delta
        )