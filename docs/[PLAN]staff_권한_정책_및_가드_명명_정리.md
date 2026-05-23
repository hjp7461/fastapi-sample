# [PLAN] staff 권한 정책 확장 + 가드 명명 정리 (`require_*` 통일)

> 연결 PRD: `docs/[PRD]staff_권한_정책_및_가드_명명_정리.md`

## 사전 점검 (Step 0)

- [ ] `git status` clean / `main` brand new
- [ ] `uv run pytest 2>&1 | tail -1` → **64 passed** (baseline)
- [ ] PRD §결정 사항 모두 ✓ 상태
- [ ] **conftest 에 staff fixture 부재 확인 완료** — Step 1 에서 추가
- [ ] **기존 customer 거부 케이스 1건** (`test_create_product_as_regular_user`, line 130) 만 존재 → Step 5 에서 나머지 4개 추가
- [ ] `app/api/permissions.py` 의 매트릭스 docstring 위치 확인 (line 7-13)
- [ ] 가드 함수가 테스트 함수명에 차용된 곳 (예: `test_get_self_or_admin_blocks_before_existence_check`) — **테스트 함수명은 동작 표현이므로 유지** (가드 이름 변경과 무관)

## 작업 분해

### Step 1 — conftest 에 staff 픽스처 추가

**파일**: `tests/conftest.py`

**작업**:

1. `admin_user` 패턴을 그대로 따라 `staff_user` 픽스처 추가 (role=`UserRole.STAFF`).
2. 동일 패턴으로 `staff_auth_headers` 픽스처 추가.

**검증**: `uv run pytest -q` → 픽스처 추가만으로 회귀 없음 (수가 변하지 않음).

### Step 2 — `app/api/permissions.py` 가드 명명 변경 + `require_staff_or_admin` 추가

**파일**: `app/api/permissions.py`

**작업**:

1. `get_current_active_admin` → `require_admin` 으로 함수명 변경.
2. `get_self_or_admin` → `require_self_or_admin` 으로 함수명 변경.
3. 신규 함수 추가:
   ```python
   async def require_staff_or_admin(
       current_user: User = Depends(get_current_user),
   ) -> User:
       """STAFF 이상이면 통과. (정책: 라우터는 도메인 메서드만 호출)"""
       if not current_user.can_manage_products():
           raise HTTPException(
               status_code=status.HTTP_403_FORBIDDEN,
               detail="Not enough permissions",
           )
       return current_user
   ```
4. 모듈 docstring 매트릭스 갱신:
   - 3행 (require_admin / require_self_or_admin / require_staff_or_admin)
   - 사용처 열 갱신 (products 쓰기 → `products POST/PUT/DELETE/inventory PATCH`)
5. "신규 가드 추가 가이드" 의 예시도 `require_*` 로 통일.

**검증**: `ruff check app/api/permissions.py` → 0 errors.

### Step 3 — `app/product/router.py` 가드 교체

**파일**: `app/product/router.py`

**작업**:

1. import 변경: `from app.api.permissions import get_current_active_admin` → `require_staff_or_admin`
2. 변경 5개 endpoint 의 `Depends(get_current_active_admin)` → `Depends(require_staff_or_admin)` (총 5곳).
3. docstring "(관리자 전용)" → "(staff/admin 전용)" 으로 변경 (5곳).
   - 단 `update_product_inventory` 는 staff 의 일상 업무이므로 "(staff/admin 전용)" 으로 통일.

**검증**:
- `ruff check app/product/router.py` → 0 errors.
- `uv run pytest tests/product/test_router.py -q` → 기존 admin 통과 케이스는 그대로 통과해야 함 (admin ⊂ staff_or_admin). customer 거부 1건 (`test_create_product_as_regular_user`) 도 통과해야 함.

### Step 4 — `app/user/router.py` 가드 이름 변경 (정책 변경 없음)

**파일**: `app/user/router.py`

**작업**:

1. import 변경: `from app.api.permissions import get_current_active_admin, get_self_or_admin` → `require_admin, require_self_or_admin`
2. `Depends(get_self_or_admin)` → `Depends(require_self_or_admin)` (1곳, GET /users/{id})
3. `Depends(get_current_active_admin)` → `Depends(require_admin)` (1곳, GET /users/)

**검증**:
- `ruff check app/user/router.py` → 0 errors.
- `uv run pytest tests/user/test_router.py -q` → 기존 19건 그대로 통과 (이름만 변경, 동작 동일).

### Step 5 — product 회귀 테스트 추가 (staff 통과 + customer 거부 매트릭스)

**파일**: `tests/product/test_router.py`

**작업**:

`staff` 통과 케이스 (+4) — `as_admin` 패턴을 staff fixture 로 미러링:

1. `test_create_product_as_staff` (POST /products/, 201)
2. `test_update_product_as_staff` (PUT /products/{id}, 200)
3. `test_update_inventory_as_staff` (PATCH /products/{id}/inventory, 200)
4. `test_delete_product_as_staff` (DELETE /products/{id}, 204)

`customer` 거부 케이스 (+4) — 기존 `test_create_product_as_regular_user` 외 4건:

5. `test_update_product_as_regular_user` (PUT, 403)
6. `test_update_inventory_as_regular_user` (PATCH, 403)
7. `test_delete_product_as_regular_user` (DELETE, 403)
8. `test_create_product_as_anonymous` (POST, 401) — 토큰 없이 호출, 인증 단계에서 차단됨을 명시

> 8번은 권한이 아닌 인증 회귀 가드이지만, 매트릭스 완전성 측면에서 한 번 명시. 다른 변경 endpoint 의 anonymous 케이스는 기존 GET 의 anonymous 테스트에서 이미 패턴이 확립되어 있어 한 건만 추가.

**검증**:
- `uv run pytest tests/product/test_router.py -q` → +8 통과 (총 18 → 26).

### Step 6 — user 관리 가드 회귀 테스트 보강 (staff 거부)

**파일**: `tests/user/test_router.py`

**작업**:

기존에 `test_access_admin_endpoint_as_regular_user` (line 357) 와 `test_access_admin_endpoint_as_admin` (line 371) 매트릭스가 있음. staff 거부 케이스 1건 추가 + GET /users/{id} 타인 조회 staff 거부 케이스 1건 추가:

1. `test_access_admin_endpoint_as_staff` (GET /users/, 403) — staff 가 사용자 목록 조회 시도 시 거부 (admin only 정책 회귀 가드).
2. `test_get_other_user_as_staff_is_forbidden` (GET /users/{id} 타인, 403) — staff 가 다른 사용자 조회 시 `require_self_or_admin` 가드에서 거부.

**검증**:
- `uv run pytest tests/user/test_router.py -q` → +2 통과 (총 19 → 21).

### Step 7 — `app/user/domain.py` 검토 (변경 없음 확정)

**작업**:

- `can_manage_products()` 메서드는 **유지** (PRD §결정 (b)). `require_staff_or_admin` 에서 호출하므로 더 이상 dead code 가 아님.
- `app/user/domain.py` 코드 변경 없음.
- `tests/user/test_role.py::test_can_manage_products_delegates_to_staff_or_above` 는 그대로 유지 (위임 동작 회귀 가드).

**검증**: `grep -rn "can_manage_products" app/ tests/` → 호출 1곳 (permissions.py) + 정의 1곳 + 테스트 1곳 = 3 hit (이전엔 정의 + 테스트 = 2 hit, dead code 였음).

### Step 8 — 전체 회귀 + lint

**작업**:

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check
uv run ruff format --check
uv run pre-commit run --all-files
```

**기대 결과**:
- `64 + 8 (product) + 2 (user) = 74 passed`
- `ruff check` 종료 코드 0
- `ruff format --check` 종료 코드 0
- 모든 pre-commit hook Passed

### Step 9 — 커밋 + 푸시 + PR 생성

**작업**:

1. 브랜치 생성: `feature/staff-permissions-and-require-guards`
2. 커밋 (한글 + Heredoc + Co-Authored-By 푸터):
   - 분리 안: ① permissions 가드 명명 + 신규 ② product 라우터 정책 + 테스트 ③ user 라우터 이름 변경 + 테스트
   - 통합 안: 1개 커밋 (변경량이 라우터 2개 + 가드 1파일 + 테스트 2파일로 작아 통합이 자연스러움)
   - **결정: 통합 1커밋** (각 파일이 단일 주제로 응집, 분리 시 가독성 이득 미미)
3. 푸시 + `gh pr create` (제목/본문은 본 PLAN §"PR 본문 초안" 참고).

## PR 본문 초안 (Step 9 에서 사용)

**제목**: `feat(api): staff 권한으로 product 변경 작업 허용 + 가드 require_* 명명 통일`

**본문**:

```markdown
## 배경
- PR #19 staff inventory 조회 권한 후, 변경 작업이 admin-only 였던 정책 불일치 해소.
- `User.can_manage_products()` (staff 이상) 가 라우터에 미반영된 dead code 였던 문제 동시 해소.
- PR #20 가드 매트릭스 docstring 의 신규 가드 가이드 (`get_<역할/조건>_<목적>`) → 권한 강제 의미가 분명한 `require_*` 로 일관화.

## 변경 매트릭스

| 엔드포인트 | customer | staff | admin |
| --- | --- | --- | --- |
| `POST /products/` | 403 | 201 ✨ | 201 |
| `PUT /products/{id}` | 403 ✨ | 200 ✨ | 200 |
| `DELETE /products/{id}` | 403 ✨ | 204 ✨ | 204 |
| `PATCH /products/{id}/inventory` | 403 ✨ | 200 ✨ | 200 |
| `GET /users/` | 403 | 403 ✨ | 200 |
| `GET /users/{id}` (타인) | 403 | 403 ✨ | 200 |

(✨ = 이번 PR 회귀 가드 / 새 정책)

## 가드 명명 (3개)

- `get_current_active_admin` → `require_admin`
- `get_self_or_admin` → `require_self_or_admin`
- (신규) `require_staff_or_admin` (= `User.can_manage_products()` 호출)

## 테스트 플랜 (리뷰어용)
- [ ] `uv run pytest` → 74 passed
- [ ] `git grep -n "get_current_active_admin\|get_self_or_admin" app/ tests/` → 0 hit
- [ ] `git grep -n "can_manage_products" app/ tests/` → 3 hit (정의 / 가드 호출 / 위임 회귀 테스트)
- [ ] product 변경 4개에 대해 staff 토큰으로 통과 (4건)
- [ ] product 변경 4개에 대해 customer 토큰으로 403 (PUT/PATCH/DELETE 3건 신규 + POST 기존 1건)
- [ ] user 관리 2개에 대해 staff 토큰으로 403 (신규 2건)

## 비목적
- staff 와 admin 간 product 세부 권한 분기 (가격 변경 admin only 등) — 후속 정책 결정 후.
- audit log — 별도 후속.

## 후속
- RUNBOOK 에 권한 매트릭스 단락 추가 검토.
- audit log 도입 시 staff product 변경 가시성 우선.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## 산출물 체크리스트

- [ ] `app/api/permissions.py`: 함수 2개 이름 변경 + 신규 1개 + docstring 매트릭스 갱신
- [ ] `app/product/router.py`: import + Depends 5곳 + docstring 5곳
- [ ] `app/user/router.py`: import + Depends 2곳
- [ ] `tests/conftest.py`: staff_user, staff_auth_headers 픽스처
- [ ] `tests/product/test_router.py`: +8 테스트
- [ ] `tests/user/test_router.py`: +2 테스트
- [ ] `app/user/domain.py`: 변경 없음 (PRD §결정 (b))
- [ ] `tests/user/test_role.py`: 변경 없음 (위임 회귀 가드 유지)

## 테스트 케이스 (회귀 가드)

PRD §성공 기준의 매트릭스를 코드로 반영. 총 신규 +10, 합산 64 → 74.

## 회귀 방지

1. **가드 명명 회귀**: `git grep -n "get_current_active_admin\|get_self_or_admin"` → 0 hit (코드 + 테스트 + docs 영역). 본 PR 머지 후 매트릭스 단일 진실원.
2. **정책 회귀**: staff/customer/admin 6개 셀 (4 product 변경 + 2 user 관리) 매트릭스를 테스트로 가드.
3. **도메인 정합성 회귀**: `can_manage_products()` 호출처 1곳 (`require_staff_or_admin`). 향후 staff/admin 외 역할 추가 시 도메인 메서드 한 곳만 변경하면 됨.

## 롤백

`git revert <merge-commit>` 으로 단순 롤백 가능. 정책 변경 (staff 권한 확장) 은 데이터 변경 없이 코드 레벨이라 안전. 가드 이름 변경도 import path 한 줄 변경.

운영 환경에서 staff 가 product 변경한 이력이 발생한 후 롤백 시 — 데이터는 그대로 남고 staff 권한만 회수됨 (정상 시나리오).

## 후속

PRD §리스크 / 비목적 / 후속 의 후속 우선순위:

1. **RUNBOOK §권한 매트릭스 단락 추가**: 운영자/온콜이 staff 와 admin 권한 차이를 즉시 확인할 진실원. 본 PR 이후 ⬜ 마스터 목록에 행 추가.
2. **audit log**: staff 의 product 변경 가시성 확보 (PR #11/#13 의 운영 가시성 흐름의 다음 단계). 마스터 목록 ⬜ 기존 행 우선순위 상승 신호.
3. **세부 분기 가드**: 향후 "가격 변경은 admin 만" 등 정책이 도입되면 `require_admin` (이미 있음) 으로 명시적 분기. 본 PR 의 `require_staff_or_admin` 와 동거 가능 (가드는 동작 단위로 분리).

## 참고

- PRD: `docs/[PRD]staff_권한_정책_및_가드_명명_정리.md`
- 직전 관련 PR: #19 (Product 조회 컨텍스트 분리), #20 (권한 가드 모듈 분리)
- 권한 가드 진실원: `app/api/permissions.py`
- 도메인 메서드 진실원: `app/user/domain.py`
