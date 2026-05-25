"""요청 단위 ContextVar — 로그/서비스 계층에서 trace 식별자 공유.

`request_id_var`: `RequestIDMiddleware` 가 매 요청에서 set/reset.
`user_id_var`: `get_current_user` / `get_optional_current_user` 가 인증 성공 시
    set. anonymous 요청은 default None 유지. reset 은 task-scoped ContextVar 의
    자동 회수에 의존 (FastAPI request 별 asyncio task 격리).

다른 모듈은 `get_request_id()` / `get_user_id()` 로 읽기만 (직접 set 금지).
asyncio.current_task 별로 격리되므로 동시 요청 다수일 때도 값이 섞이지 않는다.
"""

from contextvars import ContextVar

# default "-" 는 요청 없는 컨텍스트 (앱 기동 시점, 백그라운드 작업 등) 의 placeholder.
# 로그 포맷에서 빈 값으로 보이지 않도록 명시적 값을 둔다.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# 인증된 사용자 ID — anonymous 요청은 default None.
# `get_current_user` / `get_optional_current_user` 가 인증 성공 시 set.
# loguru patcher / Sentry before_send / middleware meta 에서 자동 첨부 대상.
user_id_var: ContextVar[int | None] = ContextVar("user_id", default=None)


def get_request_id() -> str:
    """현재 요청의 ID 를 반환. 요청 컨텍스트 밖이면 '-'."""
    return request_id_var.get()


def get_user_id() -> int | None:
    """현재 인증된 사용자 ID. anonymous 요청이면 None."""
    return user_id_var.get()
