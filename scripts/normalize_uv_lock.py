"""Remove deprecated [options] section from uv.lock (PR #58).

uv 0.11.15 가 lockfile 에 `[options]` 섹션을 자동 추가:
    [options]
    exclude-newer = "0001-01-01T00:00:00Z" # This has no effect ...
    exclude-newer-span = "P7D"

comment 가 명시하듯 deprecated backward-compat metadata — 실제 효과 없음.
pre-commit 시점에 자동 제거하여 lockfile drift 회피.

운영자가 `uv run` (without `--no-sync`) / `uv sync` 호출 시 자동 추가됨 —
본 script 가 commit 시점에 정규화.
"""

import re
import sys
from pathlib import Path

UV_LOCK = Path("uv.lock")
# `[options]` 부터 다음 `[` 직전까지 (보통 `[[package]]`) 제거.
# multiline 모드: `^\[options\]` 라인 매치 + 이후 `[` 으로 시작 안 하는 라인들.
OPTIONS_BLOCK_PATTERN = re.compile(
    r"^\[options\]\n(?:(?!^\[).*\n)*",
    re.MULTILINE,
)


def normalize(content: str) -> str:
    """Strip `[options]` section (and trailing blank lines within block)."""
    return OPTIONS_BLOCK_PATTERN.sub("", content)


def main() -> int:
    if not UV_LOCK.exists():
        return 0
    original = UV_LOCK.read_text()
    cleaned = normalize(original)
    if cleaned != original:
        UV_LOCK.write_text(cleaned)
        print("normalize_uv_lock: removed [options] section from uv.lock")
        # pre-commit 표준: 파일 변경 시 exit 1 → hook fail (사용자 재커밋).
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
