# 사용자 조회 엔드포인트 인증 누락 개선 PRD

| 항목       | 내용                                              |
| ---------- | ------------------------------------------------- |
| 작성일     | 2026-05-22                                        |
| 작성자     | conner                                            |
| 상태       | 제안 (Draft)                                      |
| 도메인     | User                                              |
| 대상 범위  | `app/user/router.py:82 get_user_by_id`             |
| 관련 발견  | `docs/diagram/사용자_프로필.md` 작성 중 코드-테스트 정책 불일치 캐치 |

---

## 1. 배경

`GET /api/v1/users/{user_id}` 엔드포인트는 **인증 의존성이 선언되어 있지 않다.** 누구나 user_id 만 알면 사용자 정보 (email, username 등) 를 조회할 수 있다.

```python
# app/user/router.py:82
@router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(
        user_id: int,
        user_service: UserService = Depends(lambda: Container.user_service())
) -> Any:
    """특정 사용자 정보를 조회합니다."""
    try:
        return await user_service.get_user(user_id)
    ...
```

반면 테스트(`tests/user/test_router.py::test_get_user_by_id`)는 **`auth_headers` 를 넘기는 형태로 작성되어 있어**, 정책상으로는 인증이 전제되어 있다고 추정된다. 즉 **구현과 테스트가 동일한 정책을 표현하지 않는다.**

이는 PR #1 에서 수정한 `GET /users/` 의 admin 가드 누락과 동일한 카테고리의 보안 이슈다.

---

## 2. 목적

- `GET /users/{user_id}` 가 명확하고 일관된 권한 정책을 가지도록 한다.
- 정책-구현-테스트의 3자가 동일한 시맨틱을 표현하도록 정렬한다.
- `UserResponse` 에 포함되는 PII (email, username) 의 무차별 노출을 차단한다.

### 비목적

- 사용자 도메인의 다른 엔드포인트 권한 재검토 — 별도 이슈로 분리.
- `UserResponse` 스키마 변경 (필드 마스킹 등) — 본 PRD 범위 외.
- 페이징/필터링 등 기능 확장.
- 감사 로그(audit) 도입.

---

## 3. 성공 기준

| 지표                                                  | 목표값                    |
| ----------------------------------------------------- | ------------------------- |
| 인증 헤더 없이 `GET /users/{id}` 호출                 | 401 Unauthorized          |
| 비활성 사용자 토큰으로 호출                           | 400 Bad Request           |
| 권한 미달 토큰으로 호출 (정책에 따라)                 | 403 Forbidden             |
| 정책에 부합하는 토큰으로 호출                         | 200 OK + `UserResponse`   |
| 존재하지 않는 user_id 조회 (인증 통과 후)             | 404 Not Found             |
| `uv run pytest` 통과율                                | 18/18 유지                |

---

## 4. 정책 옵션

| 옵션 | 정책                                | 적용 의존성                                          | 비교                                                                                                       |
| ---- | ----------------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| A    | **인증된 사용자라면 누구나**        | `Depends(get_current_user)`                          | 가장 단순. 사용자 디렉토리가 다소 공개적인 서비스에 적합. 본인 정보 외부 노출 우려 있음                     |
| B    | **본인 또는 관리자만** (Recommended) | `Depends(get_current_user)` + 라우터 본문 분기       | 일반 SaaS 패턴. 본인 정보는 자유 조회, 타인은 관리자만 허용. 분기 1줄 추가                                  |
| C    | **관리자만**                        | `Depends(get_current_active_admin)`                  | `list_users` 와 동일 수준의 엄격한 보호. 일반 사용자는 `GET /users/me` 로만 본인 조회 가능                  |

> **권장**: B. 본인이 본인을 조회하는 케이스는 빈번하므로 `me` 우회로만 막는 건 UX 손해. 타인 조회는 관리자에 한정해 PII 노출 최소화.

### 옵션 B 구현 스케치

```python
@router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(
        user_id: int,
        current_user: Any = Depends(get_current_user),
        user_service: UserService = Depends(lambda: Container.user_service())
) -> Any:
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    try:
        return await user_service.get_user(user_id)
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
```

---

## 5. 영향 받는 파일

| 파일                                          | 변경 종류           | 비고                                                                       |
| --------------------------------------------- | ------------------- | -------------------------------------------------------------------------- |
| `app/user/router.py`                          | 의존성/분기 추가    | `get_current_user` import 및 핸들러 시그니처/본문 수정                     |
| `tests/user/test_router.py`                   | 케이스 추가 (선택) | 옵션 B 채택 시: 타인 조회 시 403 케이스 추가 권장                          |
| `docs/diagram/사용자_프로필.md`               | 다이어그램 갱신     | 인증 단계 표시 추가                                                        |

> 본 PRD 는 프로덕션 라우터 1개 + 보조 변경 으로 끝나는 범위다.

---

## 6. 테스트 영향

| 기존 테스트                                      | 영향                                                              |
| ------------------------------------------------ | ----------------------------------------------------------------- |
| `test_get_user_by_id`                            | 이미 `auth_headers` 사용 → 옵션 A/B 모두 변경 없이 PASS            |
| `test_get_nonexistent_user`                      | 이미 `auth_headers` 사용 → 변경 없이 PASS                          |

추가 케이스 (옵션 B 채택 시):

```python
async def test_get_other_user_as_regular_user(client, auth_headers, db_session):
    # 다른 사용자 시드 후 일반 사용자 토큰으로 조회 → 403
    ...
```

---

## 7. 리스크 및 결정 사항

| #   | 항목                                                                 | 대응                                                          |
| --- | -------------------------------------------------------------------- | ------------------------------------------------------------- |
| 1   | 옵션 C 선택 시 일반 사용자가 본인 ID 로 조회 불가                    | `GET /users/me` 가 존재하므로 UX 영향 미미                    |
| 2   | 옵션 B 의 분기 로직이 라우터 본문에 위치 → 비즈니스 룰의 분산        | 클린 아키텍처 관점에서 의존성으로 추상화하는 것이 더 깔끔할 수 있음. 추후 `get_self_or_admin` 같은 의존성으로 추출 검토 |
| 3   | `role == "admin"` 문자열 비교                                        | 별도 이슈(UserRole enum 정합성 - 테스트 아키텍처 PRD 잔여 #1)와 함께 다루는 것을 권장 |

### 결정 필요 사항

- [ ] 옵션 A / B / C 중 채택안 확정 (권장: B)
- [ ] 추가 테스트 케이스 작성 여부 (권장: 옵션 B 채택 시 작성)

---

## 8. 참고

- 인증 의존성:
  - `app/api/dependencies.py:20 get_current_user`
  - `app/api/dependencies.py:60 get_current_active_admin`
- 관련 시퀀스 다이어그램: [`docs/diagram/사용자_프로필.md`](./diagram/사용자_프로필.md)
- 선례: PR #1 의 `GET /users/` admin 가드 추가
