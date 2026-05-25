"""페이지네이션 듀얼 모드 헬퍼.

offset 모드 (`skip/limit`) 와 page 모드 (`page/per_page`) 의 단일 진실원.

- `resolve_pagination(skip, limit, page, per_page) -> (skip, limit, mode)`:
  query param 으로부터 effective (skip, limit) 와 mode 를 결정.
- `build_meta(total, mode, skip, limit, page, per_page) -> dict`:
  mode 에 따라 응답 meta dict 를 구성. offset 모드는 `{total, skip, limit}`,
  page 모드는 `{total, page, per_page, total_pages}` (ceiling division).

분기 트리거 = `page is not None` (page 모드). `page/per_page` 와
`skip/limit` 이 동시에 제공되면 page 우선 (skip/limit silent 무시).
"""

from typing import Literal

PaginationMode = Literal["offset", "page"]


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
