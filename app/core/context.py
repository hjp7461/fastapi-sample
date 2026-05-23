"""요청 단위 ContextVar — 로그/서비스 계층에서 trace 식별자 공유.

`RequestIDMiddleware` 가 매 요청에서 set/reset 한다. 다른 모듈은 `get_request_id()`
로 읽기만 (직접 set 금지) — 미들웨어 외에서 set 하면 reset 책임이 불명확해진다.

asyncio.current_task 별로 격리되므로 동시 요청 다수일 때도 ID 가 섞이지 않는다.
"""

from contextvars import ContextVar

# default "-" 는 요청 없는 컨텍스트 (앱 기동 시점, 백그라운드 작업 등) 의 placeholder.
# 로그 포맷에서 빈 값으로 보이지 않도록 명시적 값을 둔다.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """현재 요청의 ID 를 반환. 요청 컨텍스트 밖이면 '-'."""
    return request_id_var.get()
