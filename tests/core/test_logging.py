"""`app/core/logging.py::setup_logging` 회귀 가드.

- default (text) 출력 형식 검증
- LOG_FORMAT=json 적용 시 JSON 파싱 가능 검증
- InterceptHandler 가 stdlib logging 호출을 loguru sink 로 통과 검증
"""

import json
import logging

import pytest
from loguru import logger

from app.core.config import settings
from app.core.logging import setup_logging


@pytest.fixture(autouse=True)
def restore_logger():
    """각 테스트 후 logger sink 상태를 default 로 복원."""
    yield
    logger.remove()
    setup_logging()


def test_setup_logging_text_default(capfd):
    """default LOG_FORMAT=text → stderr 사람 친화 포맷 + request_id 컬럼."""
    setup_logging()
    logger.warning("probe-text")
    captured = capfd.readouterr()
    assert "WARNING" in captured.err
    assert "probe-text" in captured.err
    # 요청 컨텍스트 밖에서는 default "-" 가 request_id 컬럼에 들어간다.
    assert " - " in captured.err  # "-" placeholder 가 컬럼 사이에 보임


def test_setup_logging_json_format(monkeypatch, capfd):
    """LOG_FORMAT=json 시 stderr 출력이 JSON 파싱 가능 + extra.request_id 포함."""
    monkeypatch.setattr(settings, "LOG_FORMAT", "json")
    setup_logging()
    logger.warning("probe-json")
    captured = capfd.readouterr()

    last_line = captured.err.strip().splitlines()[-1]
    data = json.loads(last_line)
    assert data["record"]["message"] == "probe-json"
    assert data["record"]["level"]["name"] == "WARNING"
    # 요청 컨텍스트 밖에서는 default "-" 가 들어간다.
    assert data["record"]["extra"]["request_id"] == "-"


def test_intercept_handler_routes_stdlib_to_loguru(capfd):
    """stdlib `logging.getLogger().warning()` 호출이 loguru sink 로 통과."""
    setup_logging()
    logging.getLogger("test_intercept").warning("via-stdlib")
    captured = capfd.readouterr()
    assert "via-stdlib" in captured.err
