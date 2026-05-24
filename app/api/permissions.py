"""권한 가드 의존성.

라우터에서 사용하는 권한 가드를 한 곳에 모은다. 인증 (요청자 신원 확인) 은
`app/api/dependencies.py` 의 `get_current_user` / `get_optional_current_user`
가 담당하고, 본 모듈은 그 위에 **누가 무엇을 할 수 있는가** 정책을 표현.

## 권한 가드 매트릭스

| 가드 | 통과 조건 | 실패 | 주요 사용처 |
| --- | --- | --- | --- |
| `require_admin` | `is_admin()` | 403 | `GET /users/` 등 사용자 관리 |
| `require_self_or_admin` | `id == user_id` or `is_admin()` | 403 | `GET /users/{id}` |
| `require_staff_or_admin` | `can_manage_products()` | 403 | products 변경 4개 |

## 신규 가드 추가 가이드

- 네이밍: `require_<역할/조건>` (예: `require_staff_or_admin`).
  `require_` 는 "통과 못 하면 403" 의 권한 강제 의미를 명시한다 (인증의 `get_` 과 구분).
- 위치: 본 파일에 함수 정의 + 위 매트릭스에 한 줄 추가
- 회귀 가드: 통합 테스트로 통과/실패 양쪽 검증
  (예: `test_*_as_admin`, `test_*_as_staff`, `test_*_as_regular_user`)
- 도메인 메서드 활용: `User.is_admin()`, `User.can_manage_products()` 등
  (가드는 도메인 정책을 호출만 — 정책의 진실원은 도메인)
"""

from fastapi import Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.user.domain import User


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """현재 인증된 사용자가 관리자인지 확인합니다."""
    if not current_user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


async def require_self_or_admin(
    user_id: int,
    current_user: User = Depends(get_current_user),
) -> User:
    """본인 또는 관리자만 통과하는 권한 가드.

    `user_id` 는 라우터의 path parameter 와 같은 이름으로 FastAPI 가 자동 주입.

    - 본인 (`current_user.id == user_id`) → 통과
    - 관리자 (`current_user.is_admin()`) → 통과
    - 그 외 → 403 Forbidden

    권한 검사는 자원의 존재 확인보다 먼저 평가되어 ID 열거 공격을 차단한다.
    """
    if current_user.id != user_id and not current_user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


async def require_staff_or_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """STAFF 이상이면 통과 (products 변경 정책의 단일 진실원).

    도메인 메서드 `User.can_manage_products()` 를 호출 — 역할 계층이 확장되면
    도메인 한 곳만 변경하면 가드 동작이 따라간다.
    """
    if not current_user.can_manage_products():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user
