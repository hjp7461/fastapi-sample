"""
사용자 데이터 액세스 레이어.
데이터베이스와의 상호작용을 담당합니다.
"""

from typing import List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.domain import NewUser, User
from app.user.models import UserModel


class UserRepository:
    """
    사용자 데이터 액세스 레이어.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, new_user: NewUser) -> User:
        """새 사용자를 생성합니다. DB save 후 `User` 로 변환하여 반환."""
        db_user = UserModel(
            email=new_user.email,
            username=new_user.username,
            hashed_password=new_user.hashed_password,
            first_name=new_user.first_name,
            last_name=new_user.last_name,
            role=new_user.role,
            is_active=new_user.is_active,
        )
        self.session.add(db_user)
        await self.session.commit()
        await self.session.refresh(db_user)
        return self._to_domain(db_user)

    async def get_by_id(self, user_id: int) -> Optional[User]:
        """ID로 사용자를 조회합니다."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        db_user = result.scalars().first()
        if db_user:
            return self._to_domain(db_user)
        return None

    async def get_by_email(self, email: str) -> Optional[User]:
        """이메일로 사용자를 조회합니다."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        db_user = result.scalars().first()
        if db_user:
            return self._to_domain(db_user)
        return None

    async def update(self, user_id: int, user_data: dict) -> Optional[User]:
        """사용자 정보를 업데이트합니다."""
        # 먼저 사용자가 존재하는지 확인
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        db_user = result.scalars().first()
        if not db_user:
            return None

        # 업데이트할 필드 필터링
        update_data = {k: v for k, v in user_data.items() if v is not None}

        # 데이터가 있으면 업데이트 실행
        if update_data:
            await self.session.execute(
                update(UserModel).where(UserModel.id == user_id).values(**update_data)
            )
            await self.session.commit()

            # 업데이트된 사용자 조회
            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            db_user = result.scalars().first()

        return self._to_domain(db_user)

    async def delete(self, user_id: int) -> bool:
        """사용자를 삭제합니다."""
        result = await self.session.execute(
            delete(UserModel).where(UserModel.id == user_id)
        )
        await self.session.commit()
        return result.rowcount > 0

    async def list(self, skip: int = 0, limit: int = 100) -> List[User]:
        """사용자 목록을 조회합니다."""
        result = await self.session.execute(select(UserModel).offset(skip).limit(limit))
        return [self._to_domain(user) for user in result.scalars().all()]

    def _to_domain(self, db_user: UserModel) -> User:
        """데이터베이스 모델을 도메인 엔티티로 변환합니다."""
        return User(
            id=db_user.id,
            email=db_user.email,
            username=db_user.username,
            hashed_password=db_user.hashed_password,
            first_name=db_user.first_name,
            last_name=db_user.last_name,
            role=db_user.role,
            is_active=db_user.is_active,
            created_at=db_user.created_at,
            updated_at=db_user.updated_at,
        )
