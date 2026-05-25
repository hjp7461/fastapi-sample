"""OpenAPI schema 를 파일로 export.

CI 의 SDK 생성 게이트 및 향후 SDK publish / 문서 사이트의 단일 진실원.

`app.openapi()` 호출 결과 (PR #51 customizer / PR #59 endpoint x status /
PR #60 summary 권한 / PR #63 tag 세분화 / PR #65 examples 등 누적 반영)
를 JSON 파일로 직렬화한다. DB 연결 / lifespan startup 부수효과 없이
schema dict 만 추출 (FastAPI 의 `app.openapi()` 는 lazy build).

Usage:
    uv run python scripts/export_openapi.py [--output openapi.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.main import app


def main() -> int:
    """OpenAPI schema 를 JSON 파일로 출력.

    Returns:
        프로세스 종료 코드 (0 = 성공).
    """
    parser = argparse.ArgumentParser(description="Export OpenAPI schema to JSON.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("openapi.json"),
        help="출력 파일 경로 (기본: ./openapi.json)",
    )
    args = parser.parse_args()

    schema = app.openapi()
    args.output.write_text(json.dumps(schema, ensure_ascii=False, indent=2))
    path_count = len(schema.get("paths", {}))
    print(f"Exported OpenAPI schema -> {args.output} ({path_count} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
