"""pagination 듀얼 모드 헬퍼 단위 회귀 가드.

PRD §5.6 #1, #9 — `resolve_pagination` / `build_meta` 단위.
"""

from app.core.pagination import build_meta, resolve_pagination


class TestResolvePagination:
    """`resolve_pagination` 분기 규칙 회귀 가드."""

    def test_page_provided_returns_page_mode(self) -> None:
        """PRD §5.6 #1: page 제공 시 page 모드 + (page-1)*per_page = skip."""
        skip, limit, mode = resolve_pagination(skip=0, limit=100, page=2, per_page=10)
        assert (skip, limit, mode) == (10, 10, "page")

    def test_page_only_falls_back_to_limit_as_per_page(self) -> None:
        """per_page 미제공 시 limit (default 100) 사용 — PRD §5.2 fallback."""
        skip, limit, mode = resolve_pagination(skip=0, limit=100, page=3, per_page=None)
        assert (skip, limit, mode) == (200, 100, "page")

    def test_no_page_returns_offset_mode(self) -> None:
        """page 미제공 → offset 모드 (skip/limit 그대로)."""
        skip, limit, mode = resolve_pagination(
            skip=40, limit=20, page=None, per_page=None
        )
        assert (skip, limit, mode) == (40, 20, "offset")

    def test_per_page_only_without_page_stays_offset(self) -> None:
        """page 미제공 → offset (per_page 단독 활성화 X) — PRD §5.2 단순화."""
        skip, limit, mode = resolve_pagination(
            skip=0, limit=100, page=None, per_page=10
        )
        assert mode == "offset"

    def test_both_provided_page_wins(self) -> None:
        """PRD §1.4 / §5.6 #7: page + skip/limit 동시 제공 → page 우선."""
        skip, limit, mode = resolve_pagination(skip=999, limit=999, page=2, per_page=10)
        assert (skip, limit, mode) == (10, 10, "page")

    def test_page_one_is_skip_zero(self) -> None:
        """PRD §5.6 #2 단위 부분: page=1 의 skip 이 0 (off-by-one 가드)."""
        skip, limit, mode = resolve_pagination(skip=0, limit=100, page=1, per_page=20)
        assert (skip, limit, mode) == (0, 20, "page")


class TestBuildMeta:
    """`build_meta` 응답 dict 회귀 가드."""

    def test_offset_mode_returns_skip_limit(self) -> None:
        """offset 모드 → `{total, skip, limit}` (PR #52 동일 형식)."""
        meta = build_meta(
            total=47, mode="offset", skip=0, limit=20, page=None, per_page=None
        )
        assert meta == {"total": 47, "skip": 0, "limit": 20}

    def test_page_mode_returns_page_per_page_total_pages(self) -> None:
        """page 모드 → `{total, page, per_page, total_pages}` (offset 필드 미포함)."""
        meta = build_meta(total=47, mode="page", skip=0, limit=100, page=1, per_page=20)
        assert meta == {
            "total": 47,
            "page": 1,
            "per_page": 20,
            "total_pages": 3,
        }

    def test_total_pages_ceiling_division(self) -> None:
        """PRD §5.6 #9: total_pages 가 ceiling division — 47/20 = 3."""
        meta = build_meta(total=47, mode="page", skip=0, limit=100, page=1, per_page=20)
        assert meta["total_pages"] == 3

    def test_total_pages_exact_division(self) -> None:
        """ceiling division 의 정확 분할 케이스 — 40/20 = 2."""
        meta = build_meta(total=40, mode="page", skip=0, limit=100, page=1, per_page=20)
        assert meta["total_pages"] == 2

    def test_total_zero_yields_total_pages_zero(self) -> None:
        """PRD §5.6 #10 단위: total=0 → total_pages=0 (divide-by-zero 가드)."""
        meta = build_meta(total=0, mode="page", skip=0, limit=100, page=1, per_page=10)
        assert meta["total_pages"] == 0
        assert meta["total"] == 0

    def test_page_mode_per_page_fallback_to_limit(self) -> None:
        """per_page 미지정 시 limit 사용 — total_pages 도 limit 기준 계산."""
        meta = build_meta(
            total=50, mode="page", skip=0, limit=25, page=2, per_page=None
        )
        assert meta == {
            "total": 50,
            "page": 2,
            "per_page": 25,
            "total_pages": 2,
        }
