"""normalize_uv_lock script 단위 테스트 (PR #58)."""

from scripts.normalize_uv_lock import normalize


def test_normalize_removes_options_section() -> None:
    """[options] 섹션 제거 + 다음 [[package]] 까지 정상 연결."""
    original = """version = 1
revision = 3
requires-python = ">=3.12"

[options]
exclude-newer = "0001-01-01T00:00:00Z" # comment
exclude-newer-span = "P7D"

[[package]]
name = "aiosqlite"
"""
    expected = """version = 1
revision = 3
requires-python = ">=3.12"

[[package]]
name = "aiosqlite"
"""
    assert normalize(original) == expected


def test_normalize_idempotent_when_no_options() -> None:
    """이미 정규화된 파일은 변경 없음 (idempotent)."""
    content = """version = 1
revision = 3

[[package]]
name = "aiosqlite"
"""
    assert normalize(content) == content


def test_normalize_handles_options_at_end() -> None:
    """[options] 가 파일 끝에 있어도 안전 제거."""
    original = """[[package]]
name = "x"

[options]
exclude-newer = "0001-01-01T00:00:00Z"
"""
    expected = """[[package]]
name = "x"

"""
    assert normalize(original) == expected
