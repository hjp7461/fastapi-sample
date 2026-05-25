"""sort 파서 + LIKE escape 단위 회귀 가드 (PR #66).

router 통합은 `tests/user/test_router.py` / `tests/product/test_router.py` 에서.
본 모듈은 `app/core/sort.py` 의 단위 동작만 검증한다.
"""

import pytest
from fastapi import HTTPException

from app.core.sort import SortField, escape_like_pattern, parse_sort


def test_parse_sort_returns_empty_for_none() -> None:
    """PR #66: raw=None 이면 빈 리스트 반환 (sort 누락 = DB 기본 순서)."""
    assert parse_sort(None, frozenset({"email"})) == []


def test_parse_sort_returns_empty_for_empty_string() -> None:
    """PR #66: raw='' 도 빈 리스트 (None 동등)."""
    assert parse_sort("", frozenset({"email"})) == []


def test_parse_sort_parses_single_ascending() -> None:
    """PR #66: ?sort=email → descending=False (ASC)."""
    result = parse_sort("email", frozenset({"email"}))
    assert result == [SortField(field="email", descending=False)]


def test_parse_sort_parses_single_descending() -> None:
    """PR #66: ?sort=-created_at → descending=True (DESC, '-' prefix)."""
    result = parse_sort("-created_at", frozenset({"created_at"}))
    assert result == [SortField(field="created_at", descending=True)]


def test_parse_sort_preserves_multi_sort_order() -> None:
    """PR #66: multi-sort 는 입력 순서 보존 (안정 정렬용)."""
    result = parse_sort(
        "role,-created_at,email",
        frozenset({"role", "created_at", "email"}),
    )
    assert result == [
        SortField(field="role", descending=False),
        SortField(field="created_at", descending=True),
        SortField(field="email", descending=False),
    ]


def test_parse_sort_rejects_empty_token() -> None:
    """PR #66 §5.7 #5: ?sort=email,,created_at → 422 (빈 토큰)."""
    with pytest.raises(HTTPException) as exc:
        parse_sort("email,,created_at", frozenset({"email", "created_at"}))
    assert exc.value.status_code == 422
    assert "빈 정렬 토큰" in str(exc.value.detail)


def test_parse_sort_rejects_field_not_in_whitelist() -> None:
    """PR #66 §5.7 #4: ?sort=password_hash → 422 (화이트리스트 외)."""
    with pytest.raises(HTTPException) as exc:
        parse_sort("password_hash", frozenset({"email", "id"}))
    assert exc.value.status_code == 422
    detail_str = str(exc.value.detail)
    assert "허용되지 않는 정렬 필드" in detail_str
    assert "password_hash" in detail_str


def test_parse_sort_rejects_duplicate() -> None:
    """PR #66 §5.7 #6: ?sort=email,-email → 422 (중복 필드)."""
    with pytest.raises(HTTPException) as exc:
        parse_sort("email,-email", frozenset({"email"}))
    assert exc.value.status_code == 422
    assert "중복 정렬 필드" in str(exc.value.detail)


def test_parse_sort_strips_whitespace_around_tokens() -> None:
    """PR #66: ?sort= email , -created_at  → 공백 trim 후 파싱."""
    result = parse_sort(" email , -created_at ", frozenset({"email", "created_at"}))
    assert result == [
        SortField(field="email", descending=False),
        SortField(field="created_at", descending=True),
    ]


def test_escape_like_pattern_handles_wildcards() -> None:
    """PR #66 §5.7 #17 (선택): LIKE 메타문자 (%, _, \\) escape + lowercase."""
    assert escape_like_pattern("50%_admin") == "50\\%\\_admin"
    assert escape_like_pattern("FOO") == "foo"
    # 백슬래시는 두 번 escape (LIKE escape 문자 자체)
    assert escape_like_pattern("a\\b") == "a\\\\b"


def test_escape_like_pattern_combined_meta_and_case() -> None:
    """PR #66: 메타문자 + 대문자 혼합 — escape 와 lower 가 모두 적용."""
    assert escape_like_pattern("100%_OFF") == "100\\%\\_off"
