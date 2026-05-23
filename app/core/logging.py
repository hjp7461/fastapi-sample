"""애플리케이션 로깅 설정 — loguru 단일 표면.

`setup_logging()` 은 main.py import 시점에 1회 호출된다. 다른 모듈에서
sink 를 직접 추가하지 말 것 (`logger.add` 호출 금지) — 본 모듈의 단일 진입점이
sink 구성을 독점한다.

stdlib `logging` 호출 (uvicorn / sqlalchemy / FastAPI) 도 `InterceptHandler` 로
loguru 에 통과시켜 로깅 표면을 단일화한다.
"""

import logging
import sys
from typing import Any

from loguru import logger

from app.core.config import settings
from app.core.context import get_request_id


class InterceptHandler(logging.Handler):
    """stdlib logging 호출을 loguru 로 통과시킨다.

    참고: https://loguru.readthedocs.io/en/stable/overview.html#entirely-compatible-with-standard-logging
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # caller frame 찾기 (loguru 가 호출 위치를 정확히 표시하도록)
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


_TEXT_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[request_id]}</cyan> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

_JSON_FORMAT = "{message}"


def _inject_request_id(record: Any) -> None:
    """모든 로그 record 의 extra 에 현재 request_id 첨부.

    `logger.configure(patcher=...)` 로 등록되어 sink 도달 전에 호출된다.
    record 는 loguru 의 내부 Record (dict-like) — 외부에 노출되지 않아 `Any` 로 둔다.
    요청 컨텍스트 밖에서는 default "-" 가 들어간다 (`context.py` 참고).
    """
    record["extra"]["request_id"] = get_request_id()


def setup_logging() -> None:
    """환경 변수 기반 로깅 구성. main.py import 시점에 1회 호출.

    - LOG_LEVEL / LOG_FORMAT / LOG_FILE / LOG_FILE_ROTATION / LOG_FILE_RETENTION 참조
    - default loguru handler 제거 후 stderr sink 재구성 (중복 출력 차단)
    - LOG_FILE 설정 시 file sink 추가
    - stdlib logging → loguru intercept (uvicorn / sqlalchemy 노이즈 통일)
    - request_id 자동 첨부 (`RequestIDMiddleware` + `_inject_request_id` patcher)
    """
    logger.remove()
    logger.configure(patcher=_inject_request_id)

    is_json = settings.LOG_FORMAT == "json"
    sink_format = _JSON_FORMAT if is_json else _TEXT_FORMAT

    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format=sink_format,
        serialize=is_json,
        colorize=not is_json,
    )

    if settings.LOG_FILE:
        logger.add(
            settings.LOG_FILE,
            level=settings.LOG_LEVEL,
            format=sink_format,
            serialize=is_json,
            rotation=settings.LOG_FILE_ROTATION,
            retention=settings.LOG_FILE_RETENTION,
        )

    # stdlib logging → loguru
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for noisy in ("uvicorn", "sqlalchemy.engine"):
        logging.getLogger(noisy).handlers = [InterceptHandler()]

    # uvicorn.access 는 AccessLogMiddleware 가 대체 — 중복 출력 차단.
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers = []
    uvicorn_access.propagate = False
