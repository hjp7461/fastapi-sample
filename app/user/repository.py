"""
사용자 데이터 액세스 레이어.
데이터베이스와의 상호작용을 담당합니다.
"""

from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement, Select

from app.core.result import CrudOutcome, CrudResult
from app.core.sort import SortField, escape_like_pattern
from app.user.domain import NewUser, User
from app.user.models import UserModel
from app.user.schemas import UserListFilters

# router 의 `_USER_SORT_FIELDS` 화이트리스트와 1:1 대응 (수동 동기화).
# 부정합 시 parse_sort 가 422 로 차단하므로 KeyError 는 발생하지 않음.
_USER_SORT_COLUMN_MAP: dict[str, ColumnElement[Any]] = {
    "id": UserModel.id,
    "email": UserModel.email,
    "created_at": UserModel.created_at,
    "updated_at": UserModel.updated_at,
    "role": UserModel.role,
}


def _apply_user_filters(query: Select[Any], filters: UserListFilters) -> Select[Any]:
    """list / count 공통 필터 적용 (PR #66).

    q 검색 대상: email, username, first_name, last_name (DB 컬럼만).
    `full_name` 은 도메인 property 라 DB LIKE 대상이 아님 — 구성 컬럼으로 분해.
    """
    if filters.role is not None:
        query = query.where(UserModel.role == filters.role)
    if filters.is_active is not None:
        query = query.where(UserModel.is_active == filters.is_active)
    if filters.q is not None:
        pattern = f"%{escape_like_pattern(filters.q)}%"
        query = query.where(
            or_(
                func.lower(UserModel.email).like(pattern, escape="\\"),
                func.lower(UserModel.username).like(pattern, escape="\\"),
                func.lower(UserModel.first_name).like(pattern, escape="\\"),
                func.lower(UserModel.last_name).like(pattern, escape="\\"),
            )
        )
    return query


class UserRepository:
    """
    사용자 데이터 액세스 레이어.
    """

    def __init__(self, session: AsyncSession) -> None:
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

    async def get_by_id(self, user_id: int) -> CrudResult[User]:
        """ID로 사용자를 조회합니다 (PR #56: CrudResult 패턴)."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        db_user = result.scalars().first()
        if db_user is None:
            return CrudResult(outcome=CrudOutcome.NOT_FOUND)
        return CrudResult(outcome=CrudOutcome.OK, value=self._to_domain(db_user))

    async def get_by_email(self, email: str) -> CrudResult[User]:
        """이메일로 사용자를 조회합니다 (PR #56)."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        db_user = result.scalars().first()
        if db_user is None:
            return CrudResult(outcome=CrudOutcome.NOT_FOUND)
        return CrudResult(outcome=CrudOutcome.OK, value=self._to_domain(db_user))

    async def update(self, user_id: int, user_data: dict) -> CrudResult[User]:
        """사용자 정보를 업데이트합니다 (PR #56)."""
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        db_user = result.scalars().first()
        if db_user is None:
            return CrudResult(outcome=CrudOutcome.NOT_FOUND)

        update_data = {k: v for k, v in user_data.items() if v is not None}

        if update_data:
            await self.session.execute(
                update(UserModel).where(UserModel.id == user_id).values(**update_data)
            )
            await self.session.commit()

            result = await self.session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            db_user = result.scalars().first()

        return CrudResult(outcome=CrudOutcome.OK, value=self._to_domain(db_user))

    async def delete(self, user_id: int) -> CrudResult[None]:
        """사용자를 삭제합니다 (PR #56: bool → outcome enum)."""
        result = await self.session.execute(
            delete(UserModel).where(UserModel.id == user_id)
        )
        await self.session.commit()
        outcome = CrudOutcome.OK if result.rowcount > 0 else CrudOutcome.NOT_FOUND
        return CrudResult(outcome=outcome)

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: UserListFilters | None = None,
        sort: list[SortField] | None = None,
    ) -> list[User]:
        """사용자 목록을 조회합니다 (PR #66: filter/sort 표준화).

        filters/sort 모두 None / default 시 PR #52 동작과 동일 (호환성).
        """
        _filters = filters if filters is not None else UserListFilters()
        _sort = sort if sort is not None else []

        query: Select[Any] = select(UserModel)
        query = _apply_user_filters(query, _filters)
        for sf in _sort:
            col = _USER_SORT_COLUMN_MAP[sf.field]
            query = query.order_by(col.desc() if sf.descending else col.asc())
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return [self._to_domain(user) for user in result.scalars().all()]

    async def count(self, filters: UserListFilters | None = None) -> int:
        """필터 적용 후 사용자 수 (PR #66: filter 표준화 + PR #52 연장)."""
        _filters = filters if filters is not None else UserListFilters()
        query: Select[Any] = select(func.count()).select_from(UserModel)
        query = _apply_user_filters(query, _filters)
        result = await self.session.execute(query)
        return result.scalar_one()

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
