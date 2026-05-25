"""페이지네이션 듀얼 모드 헬퍼 + factory dependency.

offset 모드 (`skip/limit`) 와 page 모드 (`page/per_page`) 의 단일 진실원.

- `resolve_pagination(skip, limit, page, per_page) -> (skip, limit, mode)`:
  query param 으로부터 effective (skip, limit) 와 mode 를 결정.
- `build_meta(total, mode, skip, limit, page, per_page) -> dict`:
  mode 에 따라 응답 meta dict 를 구성. offset 모드는 `{total, skip, limit}`,
  page 모드는 `{total, page, per_page, total_pages}` (ceiling division).
- `make_pagination_dep(default_limit_attr)`: 자원별 list paging FastAPI
  dependency factory. Query 의 default/le 가 module-load 시점에 settings
  를 캡처하는 함정을 회피하기 위해 request 시점에 settings 의 최신 값을
  평가한다 (pytest monkeypatch.setattr 호환). PR ## 신규.

분기 트리거 = `page is not None` (page 모드). `page/per_page` 와
`skip/limit` 이 동시에 제공되면 page 우선 (skip/limit silent 무시).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, Query, status

from app.core.config import settings

PaginationMode = Literal["offset", "page"]


@dataclass
class Pagination:
    """list endpoint paging 결과 (offset 모드: skip + 실효 limit + mode).

    page 모드 처리는 라우터의 `resolve_pagination` / `build_meta` 호출이
    담당 (본 dependency 는 offset 모드 limit/per_page 의 default + max 만
    관리). 라우터는 dependency 가 반환한 default_limit 을 `limit` 으로,
    page/per_page Query 와 함께 `resolve_pagination` 에 전달한다.
    """

    skip: int
    limit: int


def make_pagination_dep(
    default_limit_attr: str,
) -> Callable[..., Pagination]:
    """자원별 offset 모드 paging dependency factory.

    Args:
        default_limit_attr: Settings 의 default limit 필드명
            (예: ``"USER_LIST_DEFAULT_LIMIT"``).

    Returns:
        FastAPI dependency 함수. ge 는 Query 에서, le 는 dependency 내부
        에서 검증 (le 를 Query 에 두면 module-load 시점에 settings 캡처
        되어 monkeypatch 무효 — PR ## 핵심 설계 포인트).
    """

    def _dep(
        skip: int = Query(
            0,
            ge=0,
            description="페이징 offset (offset 모드, 0 이상)",
        ),
        limit: int | None = Query(
            None,
            ge=1,
            description=(
                "페이지 크기 (offset 모드, 1 이상). 미지정 시 자원별 "
                "default. 상한은 LIST_MAX_LIMIT (request 시점 평가)."
            ),
        ),
    ) -> Pagination:
        # request 시점에 settings 평가 — module-load 캡처 회피
        max_limit: int = settings.LIST_MAX_LIMIT
        default_limit: int = getattr(settings, default_limit_attr)
        effective: int = default_limit if limit is None else limit
        if effective > max_limit:
            # FastAPI 의 422 envelope 과 동일 형식 (PR #38 / #48)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=[
                    {
                        "loc": ["query", "limit"],
                        "msg": f"limit must be <= {max_limit}",
                        "type": "value_error.number.not_le",
                    }
                ],
            )
        return Pagination(skip=skip, limit=effective)

    return _dep


user_pagination_dep = make_pagination_dep("USER_LIST_DEFAULT_LIMIT")
product_pagination_dep = make_pagination_dep("PRODUCT_LIST_DEFAULT_LIMIT")


def enforce_per_page_max(per_page: int | None) -> None:
    """page 모드의 per_page 도 LIST_MAX_LIMIT 적용 (PR #64 정합성).

    PR #64 의 router-level Query 는 `le=1000` 으로 hardcoded 되어 있어
    LIST_MAX_LIMIT 환경 변수와 무관하게 동작. 본 헬퍼는 request 시점에
    settings.LIST_MAX_LIMIT 을 평가하여 per_page 상한을 동적으로 적용.

    Args:
        per_page: page 모드 쿼리 파라미터 (None 시 검증 skip).

    Raises:
        HTTPException 422: per_page > LIST_MAX_LIMIT 시 envelope 형식 raise.
    """
    if per_page is None:
        return
    max_limit: int = settings.LIST_MAX_LIMIT
    if per_page > max_limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "loc": ["query", "per_page"],
                    "msg": f"per_page must be <= {max_limit}",
                    "type": "value_error.number.not_le",
                }
            ],
        )


def resolve_pagination(
    *,
    skip: int,
    limit: int,
    page: int | None,
    per_page: int | None,
) -> tuple[int, int, PaginationMode]:
    """query param 으로부터 (effective_skip, effective_limit, mode) 결정.

    분기 규칙:
    - `page is not None` → page 모드.
      per_page 미지정 시 `limit` (default 100) fallback.
      effective_skip = `(page - 1) * effective_per_page`.
    - 그 외 → offset 모드 (skip/limit 그대로).

    page/per_page 와 skip/limit 동시 제공 시 page 우선 (skip/limit 무시).
    """
    if page is not None:
        effective_per_page = per_page if per_page is not None else limit
        return (page - 1) * effective_per_page, effective_per_page, "page"
    return skip, limit, "offset"


def build_meta(
    *,
    total: int,
    mode: PaginationMode,
    skip: int,
    limit: int,
    page: int | None,
    per_page: int | None,
) -> dict[str, int]:
    """mode 에 따라 응답 meta dict 구성 (offset 모드에 page 필드 미포함).

    page 모드: `{total, page, per_page, total_pages}` —
    total_pages 는 ceiling division, total==0 시 0.
    offset 모드: `{total, skip, limit}` — PR #52 동일.
    """
    if mode == "page":
        effective_per_page = per_page if per_page is not None else limit
        assert page is not None  # mode == "page" invariant
        total_pages = (
            (total + effective_per_page - 1) // effective_per_page if total > 0 else 0
        )
        return {
            "total": total,
            "page": page,
            "per_page": effective_per_page,
            "total_pages": total_pages,
        }
    return {"total": total, "skip": skip, "limit": limit}
