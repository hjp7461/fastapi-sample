# [PRD] staff 권한 정책 확장 + 가드 명명 정리 (`require_*` 통일)

## 배경

- PR #19 (Product 조회 컨텍스트 분리) 에서 staff 이상이 inventory 를 조회할 수 있도록 응답 분기가 도입되었으나, **변경 작업 (POST / PUT / DELETE / PATCH)** 은 여전히 admin 전용 (`get_current_active_admin`).
- 도메인에는 `User.can_manage_products()` (= `is_staff_or_above()`) 메서드가 존재하지만 **테스트 외 어디서도 호출되지 않는 dead code**. 즉 "STAFF 도 product 관리가 가능하다" 는 도메인 의도와 실제 라우터 정책이 어긋난 상태.
- PR #20 (권한 가드 모듈 분리) 에서 `app/api/permissions.py` 가 신설됐고, 매트릭스 docstring 에 "`get_<역할/조건>_<목적>` (예: `get_staff_or_admin`)" 가이드가 명시되어 있어, 후속 가드 명명 일관성 정리 시점.
- 현재 가드 이름 (`get_current_active_admin`, `get_self_or_admin`) 은 "**가져오기**" 뉘앙스의 `get_` 으로 시작해, 권한 강제 (= "통과 못 하면 403") 의 의도가 약하게 드러남.

## 목적

1. **staff 권한 정책 확장**: product 도메인의 모든 변경 작업 (POST / PUT / DELETE / PATCH) 을 **staff + admin** 에게 허용한다. 단, **user 도메인 (사용자 관리) 은 admin 전용 유지**.
2. **도메인-라우터 정합성 회복**: `User.can_manage_products()` 가 실제로 라우터 정책의 단일 진실원이 되도록 (또는 dead code 라면 제거).
3. **가드 명명 통일 (`require_*` 패턴)**: 권한 강제 의미가 드러나도록 모든 권한 가드를 `require_` 접두사로 일관. 신규 `require_staff_or_admin` 도 동일 패턴으로 추가.

## 비목적

- staff 와 admin 간의 product 변경 권한 **세부 분기 (예: 가격 변경은 admin 만)** — 정책 복잡도가 커지므로 본 PR 범위 밖. 후속에서 정책 결정 시 별도 가드로 분리.
- 사용자 관리 (`GET /users/`, `GET /users/{id}` 타인 조회) 에 staff 권한 확장 — 의도적으로 admin 전용 유지 (PII 보호 면적 고정).
- 인증 의존성 (`get_current_user`, `get_optional_current_user`) 이름 변경 — "인증 = 신원 확인" 은 `get_` 의미가 적절. 본 PR 은 **권한 가드**만 변경.
- 다른 도메인 (예: order, payment) 에 staff 권한 확장 — 본 저장소엔 존재하지 않음.

## 성공 기준

| 기준 | 검증 |
| --- | --- |
| product 변경 5개 (`POST/PUT/DELETE/{id}`, `PATCH /{id}/inventory`) 모두 staff 로 통과 | 새 회귀 테스트 (staff 통과 매트릭스) |
| 동일 5개가 customer 로 거부 (403) | 새 회귀 테스트 (customer 거부 매트릭스) |
| user 관리 라우터 (`GET /users/`, `GET /users/{id}` 타인 조회) 는 admin 만 통과, staff 거부 (403) | 기존 + 신규 staff 거부 케이스 |
| 모든 가드가 `require_*` 명명 | grep `def get_current_active_admin\|def get_self_or_admin` → 0 hit |
| `permissions.py` docstring 매트릭스 갱신 (3개 가드 + 사용처) | 시각 검토 |
| `can_manage_products()` 정책 결정 반영 (제거 또는 라우터 사용) | grep `can_manage_products` 결과 일치 |
| `uv run pytest` → 전부 통과 (테스트 수 +N) | `tail -1` |
| `ruff check` / `ruff format --check` 종료 코드 0 | 명령 결과 |

## 설계

### 1. 가드 변경 매트릭스

| 기존 (PR #20) | 신규 (이번 PR) | 통과 조건 | 사용처 (이번 PR 적용 후) |
| --- | --- | --- | --- |
| `get_current_active_admin` | `require_admin` | `is_admin()` | `GET /users/` , `GET /users/{id}` (타인 조회 분기 안) |
| `get_self_or_admin` | `require_self_or_admin` | `id == user_id` 또는 `is_admin()` | `GET /users/{id}` |
| (신규) | `require_staff_or_admin` | `is_staff_or_above()` | `POST /products/`, `PUT /products/{id}`, `DELETE /products/{id}`, `PATCH /products/{id}/inventory` |

> 참고: `GET /products/`, `GET /products/{id}` 는 가드를 **사용하지 않고** `get_optional_current_user` + 본문 분기 (`is_staff_or_above()`) 로 응답 형태만 갈라짐 (PR #19 정책). 본 PR 에서 그대로 유지.

### 2. `can_manage_products()` 처리

옵션:

- (a) **제거 (권장)** — 라우터 가드가 정책의 단일 진실원. 도메인 메서드가 라우터에 사용되지 않으면 진실원 두 곳으로 갈라져 또 다른 dead code 가 생김.
- (b) **유지** — 도메인 메서드를 정책 표현으로 남기고, 가드는 도메인 메서드를 호출 (`if not current_user.can_manage_products()`).

본 PRD 의 결정: **(b) 유지 + `require_staff_or_admin` 내부에서 호출**.

이유:
- §1 매트릭스에서 `require_staff_or_admin` 의 통과 조건을 도메인 의미 (`can_manage_products`) 로 표현 가능 → 향후 staff/admin 외 새 역할 도입 시 도메인만 수정.
- `is_admin()` / `is_staff_or_above()` 등 다른 도메인 메서드가 가드에서 호출되는 기존 패턴과 일치 (책임 분리: 가드 = HTTP 응답, 도메인 = 정책 판단).
- 테스트 `test_can_manage_products_delegates_to_staff_or_above` 유지 — staff/admin 외 역할 확장 시 회귀 가드.

### 3. 파일 변경 요약

- `app/api/permissions.py`
  - 함수 이름 변경 (2개)
  - 신규 함수 1개 (`require_staff_or_admin`, `can_manage_products()` 호출)
  - 매트릭스 docstring 갱신 (3행, 사용처 갱신)
- `app/product/router.py`
  - `from app.api.permissions import get_current_active_admin` → `require_staff_or_admin`
  - 변경 5개 엔드포인트의 `Depends(get_current_active_admin)` → `Depends(require_staff_or_admin)`
- `app/user/router.py`
  - import 두 줄: `get_current_active_admin` → `require_admin`, `get_self_or_admin` → `require_self_or_admin`
  - 사용처 두 곳 갱신
- `tests/product/test_router.py`
  - 기존 admin 통과 케이스는 그대로 (admin ⊂ staff_or_admin)
  - **신규 케이스**: staff 로 5개 변경 endpoint 통과 (+5)
  - **신규 케이스**: customer 로 5개 변경 endpoint 거부 (+5)
- `tests/user/test_router.py`
  - 이름 변경에 따른 `Container.user_service.override` 키는 그대로지만, 가드 의존성 override 가 있다면 갱신 (현재 코드 점검 후 결정)
  - **신규 케이스**: staff 로 `GET /users/`, `GET /users/{id}` (타인) 접근 시 403 (+2) — admin only 유지 회귀 가드
- `tests/user/test_role.py`
  - `test_can_manage_products_delegates_to_staff_or_above` 유지

### 4. 회귀 가드 매트릭스

| 엔드포인트 | customer | staff | admin |
| --- | --- | --- | --- |
| `POST /products/` | 403 | 201 ✨ | 201 |
| `PUT /products/{id}` | 403 | 200 ✨ | 200 |
| `DELETE /products/{id}` | 403 | 204 ✨ | 204 |
| `PATCH /products/{id}/inventory` | 403 | 200 ✨ | 200 |
| `GET /users/` | 403 | 403 ✨ | 200 |
| `GET /users/{id}` (타인) | 403 | 403 ✨ | 200 |

(✨ = 본 PR 에서 추가/변경되는 회귀 가드)

## 영향

- **권한 확장 (정책 변화)**: STAFF 사용자가 product 변경 작업을 수행할 수 있게 됨. 운영자에게 RUNBOOK §역할 단락이 있다면 갱신 필요 (현재는 없음, 후속으로 RUNBOOK 권한 매트릭스 단락 추가 검토).
- **API 동작 변경 없음 (호출자 입장)**: HTTP 시그니처는 동일. 권한 통과 조건만 완화.
- **테스트 수 증가**: +12 (staff 통과 5 + customer 거부 5 + user 관리 staff 거부 2) 예상 (실제 수는 PLAN 작성 후 확정).
- **외부 클라이언트**: staff 토큰으로 product 변경 호출이 이제 통과. 기존 admin 토큰은 계속 통과 (호환성 유지).

## 리스크

1. **테스트 픽스처에 staff 사용자가 없을 수 있음** — 현재 conftest 점검 후, 필요시 staff fixture 추가.
   - 영향 범위: tests/product/test_router.py
   - 완화: PLAN 의 Step 0 에서 fixture 보완.
2. **GET /users/{id} 가드 매개변수 (`user_id`)**: `require_self_or_admin` 이름만 변경되고 동작은 동일하지만, FastAPI path parameter 자동 주입 동작에 의존 — 이름 변경 후에도 동일하게 동작하는지 확인.
3. **staff 사용자의 product 변경 audit log 부재** — 현재 audit log 자체가 미구현 (마스터 목록 ⬜). 본 PR 범위 밖이지만 운영 가시성 측면에서 후속 우선순위 상승 신호.
4. **`can_manage_products()` 명명 의도 약화**: staff 가 inventory 조회 + 변경 모두 가능해지면서 "manage" 의미가 더 적합해짐. 동시에 향후 가격 변경 등 admin 전용 분기가 도입되면 메서드 의미 충돌 가능 → 비목적에 명시한 "세부 분기" 정책 결정 시 재검토.

## 결정 사항 (확정)

- [x] **B-2 변형 적용**: product 변경 작업 5개를 staff + admin 허용. 사용자 관리는 admin only 유지.
- [x] **명명 일괄 변경**: `require_*` 패턴으로 통일 (`require_admin`, `require_self_or_admin`, 신규 `require_staff_or_admin`).
- [x] **`can_manage_products()` 유지**: `require_staff_or_admin` 내부에서 호출. 도메인 정책 의미 표현 + 향후 역할 확장 시 단일 변경 지점.
- [x] **인증 의존성 (`get_current_user` 등) 이름 변경 없음**: 본 PR 은 권한 가드 (`require_*`) 만.
- [x] **세부 분기 (가격 변경 admin only 등) 는 후속**: 본 PR 에서 모든 변경 작업을 staff + admin 으로 통일.
- [x] **PR 범위**: permissions.py + product/router + user/router + 회귀 테스트 3종. RUNBOOK / docs 갱신은 본 PR 산출물이 단순하면 동봉, 복잡해지면 후속 분리 (PLAN 작성 시 결정).

## 참고

- PR #19 (Product 조회 컨텍스트 분리) — staff inventory 조회 권한 기반.
- PR #20 (권한 가드 모듈 분리) — `permissions.py` 신설, 매트릭스 docstring 가이드.
- `app/user/domain.py:44-50` — `is_staff_or_above()`, `can_manage_products()`.
- `docs/[PRD]권한_정책_모듈_분리.md` — 가드 명명 가이드 출처.
- 마스터 목록 §6 후속 3건 (staff 정책 / `staff_or_admin` 가드 / 가드 이름 변경) 을 본 PR 에서 한 번에 해소.
