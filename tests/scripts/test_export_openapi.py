"""scripts/export_openapi.py 회귀 가드 (PR #N: SDK CI 통합).

CI 의 SDK 생성 step (`Export OpenAPI schema`) 이 valid JSON 산출 +
핵심 endpoint 포함 — 두 invariant 를 단위 회귀로 가드한다.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_export_openapi_produces_valid_json(tmp_path: Path) -> None:
    """export 스크립트가 valid OpenAPI 3.x JSON 을 산출하는지 검증."""
    output = tmp_path / "openapi.json"
    result = subprocess.run(
        [sys.executable, "scripts/export_openapi.py", "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.exists()
    schema = json.loads(output.read_text())
    assert schema.get("openapi", "").startswith("3."), schema.get("openapi")
    assert "paths" in schema


def test_export_openapi_includes_core_paths(tmp_path: Path) -> None:
    """export 결과 schema 에 핵심 endpoint (users / products) 포함 검증."""
    from app.main import app

    schema = app.openapi()
    paths = schema.get("paths", {})
    assert "/api/v1/users/" in paths
    assert "/api/v1/products/" in paths
