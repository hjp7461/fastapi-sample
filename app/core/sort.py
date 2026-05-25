"""sort/filter 표준화 — Stripe 스타일 `?sort=field,-field2` 파서 + LIKE escape.

list endpoint 의 정렬/검색 쿼리 단일 진실원:

- :class:`SortField` — 파싱된 단일 정렬 키 (field + descending flag).
- :func:`parse_sort` — `?sort=email,-created_at` 형식 파서. 화이트리스트 검증 +
  빈 토큰 / 중복 필드 거부. 실패 시 422 envelope (PR #49 middleware 가 wrap).
- :func:`escape_like_pattern` — `q` 검색 시 LIKE 메타문자 (`\\`, `%`, `_`)
  escape + lowercase 통일. SQLite/Postgres 양쪽에서 case-insensitive LIKE 호환.

PRD/PLAN: `docs/[PRD]filter_sort_표준화.md`, `docs/[PLAN]filter_sort_표준화.md`.
"""

from dataclasses import dataclass

from fastapi import HTTPException, status


@dataclass(frozen=True)
class SortField:
    """파싱된 단일 정렬 키.

    Attributes:
        field: 정렬 대상 컬럼명 (endpoint 화이트리스트에 포함된 값).
        descending: True 면 DESC, False 면 ASC.
    """

    field: str
    descending: bool


def parse_sort(raw: str | None, allowed: frozenset[str]) -> list[SortField]:
    """`?sort=email,-created_at` 형식을 파싱하고 화이트리스트 검증.

    Args:
        raw: Query 원본 (None 또는 "" 이면 [] 반환).
        allowed: 정렬 허용 필드 집합 (endpoint 별 화이트리스트).

    Returns:
        파싱된 SortField 리스트 (입력 순서 보존 — multi-sort).

    Raises:
        HTTPException(422): 빈 토큰 / 허용되지 않는 필드 / 중복 필드.
            422 응답은 PR #49 의 SuccessEnvelopeMiddleware 가 wrap.
    """
    if not raw:
        return []
    fields: list[SortField] = []
    seen: set[str] = set()
    for raw_token in raw.split(","):
        token = raw_token.strip()
        if not token:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=[
                    {
                        "loc": ["query", "sort"],
                        "msg": "빈 정렬 토큰",
                        "type": "value_error",
                    }
                ],
            )
        descending = token.startswith("-")
        field = token[1:] if descending else token
        if field not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=[
                    {
                        "loc": ["query", "sort"],
                        "msg": f"허용되지 않는 정렬 필드: {field}",
                        "type": "value_error",
                        "ctx": {"allowed": sorted(allowed)},
                    }
                ],
            )
        if field in seen:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=[
                    {
                        "loc": ["query", "sort"],
                        "msg": f"중복 정렬 필드: {field}",
                        "type": "value_error",
                    }
                ],
            )
        seen.add(field)
        fields.append(SortField(field=field, descending=descending))
    return fields


def escape_like_pattern(raw: str) -> str:
    """LIKE 메타문자 (``\\``, ``%``, ``_``) 를 escape 처리하고 소문자 변환.

    SQLAlchemy 의 ``column.like(pattern, escape="\\")`` 와 함께 사용하면
    사용자가 ``%`` / ``_`` 를 포함해도 와일드카드로 해석되지 않는다.

    Args:
        raw: 사용자가 입력한 검색 문자열 (`?q=...`).

    Returns:
        escape + lowercase 처리된 문자열 (앞뒤 ``%`` wrap 은 호출자 책임).
    """
    return raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").lower()
