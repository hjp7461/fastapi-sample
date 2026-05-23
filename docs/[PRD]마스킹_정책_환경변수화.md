# [PRD] 마스킹 정책 환경 변수화 — dev 해제 옵션

> 출처: PR #15 §3 비목적 + §8 결정 사항 "별도 후속에서 옵션화 가능"
> 분류: 운영 정책
> 작업량: 소

---

## 1. 배경

PR #15 (UserResponse PII 마스킹) 에서 `UserAdminView` 의 email 을 `mask_email()` 로 항상 마스킹하기로 결정했다. 운영 안전을 최우선으로 두고 정책을 코드 고정한 결정이었고, §3 비목적 + §8 결정 사항에 "별도 후속에서 옵션화 가능" 으로 명시되어 있었다.

현재 한계:
- 개발자가 로컬에서 `GET /users/{id}` (관리자→타인 조회) 응답 본문을 디버깅할 때 `a***@e***.com` 만 노출 → 어떤 유저인지 식별 못 함
- 통합 테스트가 아닌 수동 탐색 (예: Swagger UI / curl) 에서 매번 DB 직접 조회로 우회해야 함
- 운영 환경에서는 정책 유지가 옳지만, 개발/디버깅 표면에서는 비대칭한 비용

본 PR 은 **마스킹 정책에 환경 변수 토글을 추가** 해서 개발 환경에서만 명시적으로 해제 가능하게 한다. 기본값은 항상 마스킹 적용 (운영 안전).

---

## 2. 목적

- `UserAdminView` 의 email 마스킹을 환경 변수로 토글 가능하게 함
- 기본값은 `True` (마스킹 ON) — 운영/스테이징 환경에서 변경 없이 동작
- 개발자가 `.env` 또는 export 로 `USER_ADMIN_EMAIL_MASKING=false` 설정 시 raw email 노출
- 회귀 가드로 양쪽 동작 (마스킹 on/off) 모두 검증

---

## 3. 비목적

- **`UserAdminView` 의 first_name / last_name 제외 정책 토글하지 않음** — 응답 스키마 자체에 그 필드가 없음. 토글하면 모델 형태가 달라져 OpenAPI / Pydantic 영향. 별도 후속.
- **`UserSummary` (목록) 의 PII 0건 정책 토글하지 않음** — PII 자체를 응답에서 제외하는 정책이고, 목록 조회의 정상 응답 모양에 해당. 토글 의미가 모호.
- **`ProductPublicView` 의 inventory 제외 토글하지 않음** — 이건 마스킹 정책이 아니라 영업정보 가시성 정책 (PR #19). 별개 관심사.
- **`ENVIRONMENT` 변수와 결합한 자동 해제 (예: development 면 자동 OFF) 안 함** — 묵시적 정책은 위험. 항상 명시적 환경 변수 override 만.
- **마스킹 헬퍼 (`app/user/masking.py`) 의 `app/core/masking.py` 승격 안 함** — 별도 후속 (다른 도메인 사용 시점). 본 PR 은 호출처 변경 없음.

---

## 4. 성공 기준

1. `Settings` 에 `USER_ADMIN_EMAIL_MASKING: bool = True` 추가. `.env` 또는 환경 변수로 `false` 시 해제.
2. `build_admin_view()` 가 settings 의 토글을 참조해서 분기:
   - True (default) → `email = mask_email(user.email)`
   - False → `email = user.email` (raw)
3. `UserAdminView` 의 docstring 갱신: "기본적으로 email 은 `a***@e***.com` 형태 (`USER_ADMIN_EMAIL_MASKING=false` 면 raw)"
4. 신규 회귀 가드 테스트 +1:
   - `monkeypatch` 로 `USER_ADMIN_EMAIL_MASKING=False` 후 `GET /users/{id}` (관리자→타인) 응답 email 이 raw 이메일 그대로
   - 비고: default (마스킹 ON) 케이스는 기존 `test_get_other_user_as_admin_returns_masked_view` 가 완전 커버 → 중복 회피
5. 기존 60 테스트 PASS 유지 (default True 라 기존 회귀 영향 없음). 총 **61 passed**.

---

## 5. 설계

### 5.1 `Settings` 추가

```python
# app/core/config.py
class Settings(BaseSettings):
    ...
    # 응답 PII 정책
    USER_ADMIN_EMAIL_MASKING: bool = os.getenv("USER_ADMIN_EMAIL_MASKING", "true").lower() == "true"
```

기존 BCRYPT_ROUNDS / DB_ECHO 패턴과 동일한 형태 (BaseSettings + os.getenv default + lower()).

### 5.2 `build_admin_view` 분기

```python
# app/user/schemas.py
from app.core.config import settings

def build_admin_view(user) -> UserAdminView:
    """도메인 User 를 관리자용 응답으로 변환.

    email 마스킹은 `settings.USER_ADMIN_EMAIL_MASKING` 토글에 따라 결정.
    기본 True (운영 안전). 개발 환경에서 `false` 로 명시 시 raw 노출.
    """
    return UserAdminView(
        id=user.id,
        username=user.username,
        email=mask_email(user.email) if settings.USER_ADMIN_EMAIL_MASKING else user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
```

### 5.3 회귀 가드 매트릭스

| 케이스 | 호출 | 기대 응답 email | 회귀 가드 |
| --- | --- | --- | --- |
| default (마스킹 ON), 관리자→타인 | `GET /users/{타인 id}` with admin token | `a***@e***.com` 형태 (`***` 포함) | 기존 `test_get_other_user_as_admin_returns_masked_view` |
| 환경 변수 해제 (false), 관리자→타인 | 위 동일 + monkeypatch | raw email (e.g. `target@example.com`) | **신규** `test_admin_view_email_raw_when_masking_disabled` |
| 본인 조회 | `GET /users/me` | 토글 무관 (항상 raw — UserResponse 사용) | 기존 `test_get_current_user_returns_full_pii` 등 |

본인 조회는 `UserResponse` 를 사용해서 토글 영향이 전혀 없으므로, 기존 테스트가 회귀 가드 역할.

### 5.4 테스트 전략

`monkeypatch` 로 settings 객체의 `USER_ADMIN_EMAIL_MASKING` 속성을 변경. PR #13 의 monkeypatch 사용 패턴과 동일.

```python
def test_admin_view_email_unmasked_when_toggle_off(monkeypatch, client, admin_auth_headers, test_user):
    from app.core.config import settings
    monkeypatch.setattr(settings, "USER_ADMIN_EMAIL_MASKING", False)
    response = await client.get(f"/api/v1/users/{test_user['id']}", headers=admin_auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == test_user["email"]  # raw
```

---

## 6. 영향

- **운영 환경**: 무변동. 기본값 True 이므로 `.env` 에 추가 명시 없으면 마스킹 그대로 적용.
- **개발 환경**: `.env.example` 또는 RUNBOOK 에 옵션 명시 (PR 범위 안). `USER_ADMIN_EMAIL_MASKING=false` 사용 시 raw 노출.
- **테스트**: 기존 60건은 default True 이므로 영향 없음. +2 회귀 가드 추가.
- **OpenAPI 스펙**: 무변동 (응답 모델 형태 동일, 내용만 토글).

---

## 7. 후속 작업 (이번 PR 범위 밖)

- 마스킹 헬퍼 `app/user/masking.py` → `app/core/masking.py` 승격 (다른 도메인에서 PII 마스킹 필요 시점)
- `UserAdminView` 의 first_name / last_name 토글 (정책 검토 후 필요 시)
- 다른 PII 응답 (감사 로그, audit log 등) 의 마스킹 정책 통합 (audit log 도입 시점)
- RUNBOOK 에 환경 변수 단락 보강 (BCRYPT_ROUNDS / DATABASE_URL 옆에 USER_ADMIN_EMAIL_MASKING 추가)

---

## 8. 리스크

| 리스크 | 발생 가능성 | 대응 |
| --- | --- | --- |
| 운영 환경에서 실수로 `USER_ADMIN_EMAIL_MASKING=false` 설정 → PII 노출 | 낮음 (명시 설정 필요) | RUNBOOK §환경 변수 단락에 경고 명시. 가능하다면 ENVIRONMENT=production 일 때 False 무효화 — 그러나 본 PR 비범위 (묵시적 정책 회피). |
| `build_admin_view` 가 settings 직접 참조 → 모듈 결합도 증가 | 낮음 | 이미 라우터에서 settings 참조 (SECRET_KEY, ALGORITHM 등). schemas 가 settings 참조해도 패턴 일관성 유지. 인자 주입은 호출처 부담 증가로 deferred. |
| Pydantic Settings 의 bool 파싱 비표준 (`"True"`, `"1"`, `"yes"` 등) | 낮음 | os.getenv + lower() == "true" 로 명시. `.env` 패턴 일관. |
| monkeypatch 테스트가 다른 테스트에 영향 (race condition) | 낮음 | `monkeypatch.setattr` 는 함수 종료 시 자동 복원. pytest fixture 격리. |

---

## 9. 결정 사항 (확정)

- [x] **환경 변수 이름**: `USER_ADMIN_EMAIL_MASKING` (User 도메인 + Admin view + email + masking — 범위 명시)
- [x] **default**: `True` (운영 안전)
- [x] **분기 위치**: `build_admin_view()` 내부 (settings 직접 참조). 인자 주입 형태로 추후 리팩토링 가능.
- [x] **ENVIRONMENT 와 결합 안 함** — 묵시적 정책 회피. 명시 토글만.
- [x] **범위: email 마스킹만** — first/last_name 제외 정책은 스키마 자체이므로 별도 후속.
- [x] **회귀 가드 +1** — 토글 해제 시 raw 만 신규 추가. default 마스킹은 기존 `test_get_other_user_as_admin_returns_masked_view` 가 완전 커버 (중복 회피).

---

## 10. 참고

- `docs/[PRD]UserResponse_PII_마스킹.md` (PR #15) — §3 비목적, §8 결정 사항의 후속 근거
- `docs/[PLAN]UserResponse_PII_마스킹.md` (PR #15) — §후속 작업 목록
- `app/user/schemas.py` (`UserAdminView`, `build_admin_view`)
- `app/user/masking.py` (`mask_email`)
- `app/core/config.py` (Settings 패턴)
- `tests/user/test_router.py` (기존 마스킹 매트릭스 테스트)
- `docs/RUNBOOK.md` (환경 변수 단락 — 후속 갱신)
