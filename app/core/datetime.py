"""시간 관련 공통 헬퍼.

`utcnow_aware()` 는 timezone-aware UTC 현재 시각을 반환한다.
SQLModel / SQLAlchemy 의 `default_factory` / `default` / `onupdate`
콜러블로 직접 전달하기 위해 인자를 받지 않는다.

`format_iso_z()` 는 timezone-aware datetime 을 Pydantic 2.x mode="json"
와 동등한 ISO 8601 + 'Z' 접미사 문자열로 직렬화한다. middleware meta
(`requested_at`) 등 비-Pydantic 직렬화 위치에서 사용해 응답 형식을 통일.
"""

from datetime import UTC, datetime


def utcnow_aware() -> datetime:
    return datetime.now(UTC)


def format_iso_z(dt: datetime) -> str:
    """timezone-aware datetime → ISO 8601 + 'Z' 접미사 문자열.

    Pydantic 2.x 의 mode="json" 직렬화와 동등한 출력 — middleware meta 의
    datetime 이 라우터 응답 본문의 Pydantic-serialized datetime 과 같은
    형식이 되도록 보장 (응답 형식 단일 진실원).

    tz-naive datetime 입력 시 ValueError — PR #8 의 timezone-aware 정책
    보존 + 운영 데이터 무결성 fail-fast.
    """
    if dt.tzinfo is None:
        raise ValueError("format_iso_z requires timezone-aware datetime")
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
