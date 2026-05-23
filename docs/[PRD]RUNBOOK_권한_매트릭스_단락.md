# [PRD] RUNBOOK §9 권한 매트릭스 단락 추가

## 배경

- PR #26 (staff 권한으로 product 변경 작업 허용 + 가드 `require_*` 명명 통일) 머지 후, 운영자/온콜이 "STAFF 와 ADMIN 의 차이가 정확히 무엇인가" 를 RUNBOOK 한 곳에서 확인할 진실원이 부재.
- 현재 권한 정책의 진실원은 다음과 같이 코드 여러 곳에 분산:
  - **도메인 메서드**: `app/user/domain.py` (`is_admin`, `is_staff_or_above`, `can_manage_products`)
  - **가드 매트릭스**: `app/api/permissions.py` docstring (3개 가드의 통과 조건)
  - **라우터 매핑**: `app/{user,product}/router.py` (어떤 엔드포인트가 어떤 가드를 쓰는지)
- 운영자 입장에서는 "STAFF 사용자가 가격을 바꿀 수 있나?" / "비활성 사용자 admin 도 GET /users/ 통과하나?" 같은 질문이 즉시 떠오르는데, 코드를 읽어야 한다 → 운영 마찰.
- RUNBOOK 은 `.env` 매트릭스 (§2), 일상 명령 (§5), 트러블슈팅 (§8) 같은 진실원 표를 이미 모아둔 곳. 권한 정책도 같은 카테고리.

## 목적

1. **운영자/온콜 진실원**: 권한 매트릭스 (역할 × 엔드포인트) 를 RUNBOOK 한 단락으로 압축, 즉시 확인 가능하게.
2. **코드와의 정합성 명시**: 매트릭스가 코드의 어느 위치를 반영하는지 (앵커: 도메인 메서드 / 가드 / 라우터) 짧게 명시 → 정책 변경 시 갱신 순서 명확화.
3. **B-2 정책 결정 명시**: "왜 product 변경은 staff 도 되는데 사용자 관리는 admin only 인가" 의 의도 (도메인 경계) 를 한 문장으로 기록 → 향후 재논의 시 의사결정 비용 절감.

## 비목적

- **`§3~§8` 의 § 번호 변경 없음** — `[HANDOFF]` 등 외부 참조의 안정성 유지. §9 신규 + 기존 §9 (참고 문서) → §10 으로 한 칸만 밀어냄.
- **권한 정책 자체 변경 없음** — PR #26 이 정한 매트릭스를 문서로 옮길 뿐.
- **인증 (`get_current_user`) / 토큰 흐름 / OAuth 등 인증 단계 설명 없음** — 본 § 은 권한 (인증 이후 통과/차단) 만 다룸. 인증 흐름은 별도 후속 (`docs/diagram/인증_및_권한.md` 가 이미 있음).
- **세부 권한 분기 시나리오** (가격은 admin 만, audit log 등) — 마스터 목록 ⬜ 후속.
- **README 동기화** — RUNBOOK 단독 갱신. README §권한 단락 추가는 별도 후속.

## 성공 기준

| 기준 | 검증 |
| --- | --- |
| `docs/RUNBOOK.md` 에 §9 "권한 매트릭스" 단락 신설 | 시각 검토 |
| 기존 §9 참고 문서 → §10 (단순 번호 변경) | grep `^## ` 결과 |
| 매트릭스 행: 역할 계층 1개 + 가드 3개 + 엔드포인트별 권한 ≥ 6개 | 표 행 수 |
| `app/api/permissions.py` docstring 매트릭스와 동일 행 (가드 3개) | 시각 비교 |
| 운영자 시점 변경 절차 (정책 변경 시 어느 코드를 어느 순서로 고치는지) 명시 | 단락 존재 |
| PR #26 결정 사항 (B-2 변형) 의 의도 한 문장 명시 | 단락 존재 |
| `pre-commit run --all-files` 종료 코드 0 (markdown 위생) | 명령 결과 |
| 테스트 카운트 변화 없음 (74 PASS 유지) | `uv run pytest 2>&1 \| tail -1` |
| 외부 참조 (`[HANDOFF]` 의 `§2 환경 변수`, `§3 자동화`) stale 여부 0건 | grep |

## 설계

### 1. 새 §9 단락 구성

**제목**: `## 9. 권한 매트릭스`

**소단락**:

#### 9.1 역할 계층

```
CUSTOMER ⊂ STAFF ⊂ ADMIN
```

- `CUSTOMER`: 기본 사용자 (회원가입 직후).
- `STAFF`: 일선 현장 운영자 — 상품/재고 관리 가능, 사용자 관리는 불가.
- `ADMIN`: 모든 권한.

도메인 메서드 (`app/user/domain.py`):

| 메서드 | 의미 | True 인 역할 |
| --- | --- | --- |
| `is_admin()` | ADMIN 전용 여부 | ADMIN |
| `is_staff_or_above()` | STAFF 이상 여부 | STAFF, ADMIN |
| `can_manage_products()` | 상품 관리 권한 (= `is_staff_or_above`) | STAFF, ADMIN |

#### 9.2 권한 가드 (= `app/api/permissions.py`)

| 가드 | 통과 조건 | 실패 | 호출하는 도메인 메서드 |
| --- | --- | --- | --- |
| `require_admin` | ADMIN | 403 | `is_admin()` |
| `require_self_or_admin` | 본인 (`id == user_id`) ∨ ADMIN | 403 | `is_admin()` |
| `require_staff_or_admin` | STAFF 이상 | 403 | `can_manage_products()` |

> 인증 단계 (`get_current_user`) 가 먼저 실행되어 401 (토큰 없음/만료) / 400 (비활성 사용자) 을 반환한 뒤 가드가 평가된다.

#### 9.3 엔드포인트 × 역할 매트릭스

| 엔드포인트 | anonymous | CUSTOMER | STAFF | ADMIN | 가드 |
| --- | --- | --- | --- | --- | --- |
| `POST /users/` (회원가입) | 201 | 201 | 201 | 201 | (없음) |
| `POST /users/token` (로그인) | 200/401 | — | — | — | (없음) |
| `GET /users/me` | 401 | 200 | 200 | 200 | `get_current_user` |
| `PUT /users/me` | 401 | 200 | 200 | 200 | `get_current_user` |
| `GET /users/{id}` (본인) | 401 | 200 | 200 | 200 | `require_self_or_admin` |
| `GET /users/{id}` (타인) | 401 | 403 | 403 | 200 | `require_self_or_admin` |
| `GET /users/` | 401 | 403 | 403 | 200 | `require_admin` |
| `GET /products/{id}` | 200 (Public) | 200 (Public) | 200 (Full) | 200 (Full) | (없음, 응답 분기) |
| `GET /products/` | 200 (Public) | 200 (Public) | 200 (Full) | 200 (Full) | (없음, 응답 분기) |
| `POST /products/` | 401 | 403 | 201 | 201 | `require_staff_or_admin` |
| `PUT /products/{id}` | 401 | 403 | 200 | 200 | `require_staff_or_admin` |
| `DELETE /products/{id}` | 401 | 403 | 204 | 204 | `require_staff_or_admin` |
| `PATCH /products/{id}/inventory` | 401 | 403 | 200 | 200 | `require_staff_or_admin` |

> "Public" = `ProductPublicView` (inventory 제외), "Full" = `ProductResponse` (inventory 포함). 자세한 응답 분기는 `app/product/router.py` 의 `get_product_by_id` / `list_products`.

> 타인 조회는 응답이 `UserAdminView` 로 마스킹됨 (`USER_ADMIN_EMAIL_MASKING` 환경 변수 토글 — §2 참조).

#### 9.4 정책 결정 (B-2 변형)

- **product 변경 4개 (POST/PUT/DELETE/PATCH-inventory)** 는 STAFF + ADMIN 모두 허용.
- **사용자 관리 (GET /users/, GET /users/{id} 타인)** 는 ADMIN 전용.
- 의도: **도메인 경계 = product (현장 운영) vs user (관리)**. STAFF 는 현장 운영자, ADMIN 은 인사/계정 관리 책임자.
- 원천 PR: #19 (조회 컨텍스트 분리), #26 (변경 권한 확장 + `require_*` 명명).

#### 9.5 정책 변경 시 갱신 순서

권한 정책을 바꿀 때는 항상 이 순서로 갱신한다 (진실원 → 표면).

1. **도메인 메서드** (`app/user/domain.py`) — `is_*`/`can_*` 추가 또는 의미 변경.
2. **권한 가드** (`app/api/permissions.py`) — 도메인 메서드를 호출하는 가드 추가/조정 + 매트릭스 docstring.
3. **라우터** (`app/{user,product}/router.py`) — `Depends(가드)` 교체.
4. **회귀 테스트** — 역할 × 엔드포인트 매트릭스를 통합 테스트로 가드 (`tests/{user,product}/test_router.py` 패턴).
5. **본 RUNBOOK §9** — 매트릭스 표 동기화.

### 2. 기존 §9 (참고 문서) → §10 으로 이동

내용 그대로 §10 으로 헤딩만 변경. 본문 변경 없음.

### 3. 파일 변경 요약

- `docs/RUNBOOK.md`:
  - §9 (참고) → §10 으로 변경 (헤딩 단순 치환)
  - §9 "권한 매트릭스" 신설 (위 4개 소단락 + 정책 변경 순서)
  - 라인 수 +~80 예상

## 영향

- **운영자**: 권한 정책 진실원을 RUNBOOK 한 곳에서 확인 가능. 코드를 안 봐도 됨.
- **다른 docs**: 외부 참조 안정성 100% 유지 (§2, §3 등 번호 그대로).
- **코드**: 변경 없음. 테스트 카운트 변화 없음 (74 PASS).
- **`[HANDOFF]`** §10 참고 파일 단락 등에서 RUNBOOK 의 § 번호를 직접 적은 곳이 있다면 갱신 (현재는 없음).

## 리스크

1. **§9 권한 매트릭스와 코드 불일치 (drift)** — 정책이 바뀌었는데 RUNBOOK 갱신을 잊는 경우.
   - 완화: §9.5 갱신 순서를 단락 자체에 명시 + 마스터 목록에 후속 ⬜ "권한 정책 변경 시 RUNBOOK 갱신 회귀 가드" 추가 검토.
2. **`tests/user/test_router.py:317 test_get_self_or_admin_blocks_before_existence_check`** 의 함수명이 가드 옛 이름을 차용 — 정책 진실원이 RUNBOOK 으로 모이면서 운영자가 함수명을 혼동할 가능성.
   - 완화: 본 PR 비목적. RUNBOOK §9 에 가드 이름의 새 명명 (`require_*`) 만 사용하면 운영자 혼동 영향 없음.

## 결정 사항 (확정)

- [x] **§9 권한 매트릭스 + §10 참고** 로 신설 (외부 § 참조 안정성 우선).
- [x] **4개 소단락 + 정책 변경 순서** 구조 (§9.1~§9.5).
- [x] **권한 정책 자체 변경 없음** — PR #26 의 결과를 문서로 반영.
- [x] **README 동기화는 별도 후속** — 본 PR 은 RUNBOOK 단독.
- [x] **인증 흐름 설명 없음** — `docs/diagram/인증_및_권한.md` 가 진실원.

## 참고

- PR #26 (staff 권한 + `require_*` 명명)
- PR #19 (Product 조회 컨텍스트 분리)
- PR #20 (권한 가드 모듈 분리)
- PR #25 (RUNBOOK §2 환경 변수 매트릭스 보강) — 유사한 진실원 단락 추가 사례
- `app/api/permissions.py` (가드 docstring 매트릭스 — 본 §9.2 와 동기화 대상)
- `app/user/domain.py` (역할 메서드 — 본 §9.1 의 진실원)
