# [PLAN] 다이어그램 갱신 — `require_*` 명명 + staff 권한 + Product 조회 컨텍스트

> 연결 PRD: `docs/[PRD]다이어그램_권한_갱신.md`

## 사전 점검 (Step 0)

- [ ] `git status` clean / `main` baseline / 74 PASS
- [ ] 갱신 대상 파일 5개 + README 확인 완료
- [ ] 외부 참조 `[PLAN]사용자_조회_인증_누락.md:191` 1건 — 역사 기록, 갱신 안 함
- [ ] 회원가입_로그인.md 는 변경 없음 (권한 무관)

## 작업 분해

### Step 1 — `인증_및_권한.md` §2 재작성

**파일**: `docs/diagram/인증_및_권한.md`

**작업**:
1. 머리말 (line 1-4) 갱신: 인증 + 권한 가드 명명 통일.
2. §1 유지. 사용처 목록에 `get_optional_current_user` (선택적 인증) 1줄 추가.
3. §2 재작성 — 옛 단일 가드 (`get_current_active_admin`) → 가드 매트릭스 (3행 표) + 통합 다이어그램 1개:
   - 표: `require_admin` / `require_self_or_admin` / `require_staff_or_admin` × (통과 조건, 호출 도메인 메서드, 사용처)
   - 다이어그램: 일반화된 `Guard` participant 가 `User.<도메인 메서드>` 호출 → 통과/403 분기
4. 핵심 포인트 갱신 (PR #20 모듈 분리 + PR #26 정책 진실원).

**검증**: `grep -n "get_current_active_admin\|get_self_or_admin" docs/diagram/인증_및_권한.md` → 0 hit.

### Step 2 — `사용자_프로필.md` §3 갱신

**작업**:
1. `get_self_or_admin` (4 hit) → `require_self_or_admin` (표 의존성 행 1 + mermaid participant 1 + 화살표 1 + 핵심 포인트 1).

**검증**: `grep "get_self_or_admin" docs/diagram/사용자_프로필.md` → 0 hit.

### Step 3 — `사용자_목록_관리자.md` 갱신

**작업**:
1. `get_current_active_admin` (4 hit) → `require_admin`.
2. 분기 라벨 `user.role != "admin"` → `not user.is_admin()` (도메인 메서드 정합).
3. 핵심 포인트의 시그니처 예시 갱신 (`Depends(require_admin)`).

**검증**: `grep "get_current_active_admin\|user.role" docs/diagram/사용자_목록_관리자.md` → 0 hit.

### Step 4 — `상품_관리_관리자.md` 갱신 (가장 큰 변경)

**작업**:
1. 머리말 갱신: "**모두 `require_staff_or_admin` 으로 보호 — STAFF + ADMIN 통과**".
2. 4개 endpoint (POST/PUT/DELETE/PATCH-inventory) 의 변경:
   - 표 의존성 행 4개: `get_current_active_admin` → `require_staff_or_admin`
   - mermaid participant 4개: `Admin as get_current_active_admin` → `Guard as require_staff_or_admin`
   - mermaid 화살표 4개: `Depends(get_current_active_admin)` → `Depends(require_staff_or_admin)`
   - "관리자 검사 통과 가정" → "권한 검사 통과 가정 (`can_manage_products()`)"
3. 첫 다이어그램 분기 라벨 "관리자 통과" → "권한 통과 (STAFF/ADMIN)".
4. 실패 응답 표에 "customer → 403" 명시.

**검증**: `grep -c "get_current_active_admin" docs/diagram/상품_관리_관리자.md` → 0 / `grep -c "require_staff_or_admin" docs/diagram/상품_관리_관리자.md` → ≥ 12.

### Step 5 — `상품_조회.md` PR #19 반영

**작업**:
1. §1 `GET /products/{id}`:
   - 머리말 "인증이 필요 없는 공개" → "**선택적 인증** — viewer 별 응답 분기 (PR #19)".
   - 표 인증 행: "불필요" → "선택적 (`get_optional_current_user`)".
   - 표 성공 행: `200 OK + ProductResponse` → `200 OK + Union[ProductResponse, ProductPublicView]`.
   - mermaid 재작성:
     - `participant OptDep as get_optional_current_user` 추가.
     - viewer 분기: `is_staff_or_above()` 통과 → `ProductResponse`, 아니면 `build_public_view(product) → ProductPublicView`.
2. §2 `GET /products/` 동일 패턴 (목록).
3. 핵심 포인트 갱신: `ProductPublicView` 의미 (inventory 제외) 1줄 + viewer 컨텍스트 결정의 진실원 (`app/product/router.py`의 `get_product_by_id` / `list_products`).

**검증**: `grep "ProductPublicView\|get_optional_current_user\|is_staff_or_above" docs/diagram/상품_조회.md` → 각 ≥ 1 hit.

### Step 6 — `README.md` 인덱스 갱신

**작업**:
1. `인증_및_권한.md` 설명 행: `get_current_user, get_current_active_admin 의존성` → `get_current_user / get_optional_current_user 인증 + 권한 가드 (require_*)`.
2. `상품_조회.md` 설명에 viewer 분기 한 마디 추가 (선택).
3. `상품_관리_관리자.md` 설명에 "STAFF + ADMIN" 한 마디 추가 (선택).

**검증**: `grep "get_current_active_admin" docs/diagram/README.md` → 0 hit.

### Step 7 — 전체 grep 정합성 검증

**명령**:
```bash
grep -rn "get_current_active_admin\|get_self_or_admin" docs/diagram/
grep -rn "user\.role != " docs/diagram/
uv run pytest 2>&1 | tail -1
uv run pre-commit run --all-files
```

**기대 결과**:
- 다이어그램 디렉토리에 옛 가드/문자열 role 비교 0 hit.
- pytest 74 passed.
- pre-commit 모든 hook Passed.

### Step 8 — 브랜치 / 커밋 / 푸시 / PR

**브랜치**: `feature/diagram-permission-update`

**커밋 전략**: 통합 1 커밋 — 변경이 단일 주제 (가드 명명 + staff 권한 + Product viewer) 이고 파일 간 의존성 (다이어그램 ↔ README 인덱스) 이 있어 통합이 자연스러움.

**커밋 메시지**:
```
docs(diagram): require_* 명명 + staff 권한 매트릭스 + Product 조회 컨텍스트 정합

PR #20/#26 명명 + 정책 / PR #19 응답 분기를 다이어그램 5개에 일괄
반영해 RUNBOOK §9 및 코드와의 진실원 일치를 회복.

- 인증_및_권한.md §2: 권한 가드 매트릭스 (3 가드) + 통합 다이어그램
- 사용자_프로필.md / 사용자_목록_관리자.md: 가드 명명 + 도메인 메서드 정합
- 상품_관리_관리자.md: require_staff_or_admin (STAFF + ADMIN 통과)
- 상품_조회.md: get_optional_current_user + viewer 분기 (PR #19)
- README.md: 인덱스 설명 갱신

회원가입_로그인.md 는 권한 무관, 변경 없음.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## PR 본문 초안 (Step 8 에서 사용)

```markdown
## 배경
`docs/diagram/` 의 시퀀스 다이어그램 7개 중 5개가 PR #19 / #20 / #26 누적 변경을 미반영 — 신규 개발자/온콜의 진실원 부정합 해소.

## 변경 매트릭스

| 다이어그램 | 옛 → 새 |
| --- | --- |
| `인증_및_권한.md` | `get_current_active_admin` 단일 §2 → 권한 가드 3 (`require_admin` / `require_self_or_admin` / `require_staff_or_admin`) 매트릭스 + 통합 다이어그램 |
| `사용자_프로필.md` | `get_self_or_admin` → `require_self_or_admin` |
| `사용자_목록_관리자.md` | `get_current_active_admin` → `require_admin` + 도메인 메서드 정합 (`not user.is_admin()`) |
| `상품_관리_관리자.md` | 4개 endpoint 가드 → `require_staff_or_admin` + 머리말/분기 라벨 "STAFF + ADMIN" 명시 |
| `상품_조회.md` | 공개 가정 → `get_optional_current_user` + viewer 분기 (`is_staff_or_above` → `ProductResponse`, 그 외 → `ProductPublicView`) |
| `README.md` | 인덱스 설명 갱신 |
| `회원가입_로그인.md` | 변경 없음 |

## 영향
- **코드 변경 0** / 테스트 카운트 변화 0 (74 PASS 유지)
- RUNBOOK §9 (PR #27) ↔ 다이어그램 가드 명명 1:1
- 외부 참조 (`[PLAN]사용자_조회_인증_누락.md:191`) 역사 기록 유지

## 테스트 플랜 (리뷰어용)
- [ ] `uv run pytest` → 74 passed
- [ ] `uv run pre-commit run --all-files` → 모든 hook Passed
- [ ] `grep -rn "get_current_active_admin\|get_self_or_admin" docs/diagram/` → 0 hit
- [ ] `grep -rn "user\.role != " docs/diagram/` → 0 hit
- [ ] GitHub PR 페이지에서 mermaid 다이어그램 5개 모두 정상 렌더링 (시각 확인)
- [ ] 다이어그램 가드 명명이 `app/api/permissions.py` 및 RUNBOOK §9.2 와 일치

## 비목적
- `사용자_프로필.md` 의 PII 마스킹 (PR #15 `UserAdminView`) 다이어그램 반영 — 별도 후속
- `사용자_목록_관리자.md` 의 `UserSummary` 응답 모델 반영 (PR #15) — 별도 후속
- 파일명 변경 / 다이어그램 신규 추가 / 코드 변경 — 본 PR 비범위

## 후속
- 위 비목적 2건 (PII 마스킹 / `UserSummary`) — 별도 ⬜
- README §권한 단락 추가 (RUNBOOK §9 인덱스) — 마스터 목록 ⬜

## PRD / PLAN
- `docs/[PRD]다이어그램_권한_갱신.md`
- `docs/[PLAN]다이어그램_권한_갱신.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## 산출물 체크리스트

- [ ] `docs/diagram/인증_및_권한.md` §2 재작성
- [ ] `docs/diagram/사용자_프로필.md` §3 가드 명명
- [ ] `docs/diagram/사용자_목록_관리자.md` 가드 명명 + 분기 표현
- [ ] `docs/diagram/상품_관리_관리자.md` 머리말 + 4 다이어그램 가드/라벨
- [ ] `docs/diagram/상품_조회.md` PR #19 viewer 분기 반영
- [ ] `docs/diagram/README.md` 인덱스 표
- [ ] `docs/[PRD]다이어그램_권한_갱신.md` (본 PRD 파일)
- [ ] `docs/[PLAN]다이어그램_권한_갱신.md` (본 파일)
- [ ] 회귀: 74 PASS / pre-commit Passed / grep 정합성 0 hit

## 회귀 방지

- **mermaid 렌더링 깨짐**: PR description 에 "GitHub PR 페이지 다이어그램 렌더링 확인" 항목 명시. 깨지면 PR 내 추가 커밋으로 즉시 수정.
- **다음 정책 변경 시 다이어그램 drift**: RUNBOOK §9.5 의 갱신 순서 (도메인 → 가드 → 라우터 → 테스트 → RUNBOOK) 다음 단계로 "다이어그램" 을 추가하는 것도 검토 — 단 본 PR 비범위 (RUNBOOK 갱신 안 함). 후속에서 결정.

## 롤백

`git revert <commit>` — 코드/테스트 영향 0 이라 운영 위험 없음.

## 후속

1. **`사용자_프로필.md` §3 의 PII 마스킹 (PR #15 `UserAdminView`)** — `Union[UserResponse, UserAdminView]` 응답 분기 다이어그램 반영.
2. **`사용자_목록_관리자.md` 의 `UserSummary` 응답 모델 (PR #15)** — `List[UserResponse]` → `List[UserSummary]` 변경.
3. **README §권한 단락** — RUNBOOK §9 인덱스 (PR #27 후속, 마스터 목록 ⬜ 기존 행).
4. **RUNBOOK §9.5 에 "다이어그램 갱신" 단계 추가 검토** — 정책 drift 방지의 다음 표면.

## 참고

- PRD: `docs/[PRD]다이어그램_권한_갱신.md`
- 원천 PR: #19, #20, #26, #27
- 코드 진실원: `app/api/permissions.py`, `app/api/dependencies.py`, `app/user/domain.py`, `app/product/router.py`
- 문서 진실원: `docs/RUNBOOK.md` §9 (권한 매트릭스)
