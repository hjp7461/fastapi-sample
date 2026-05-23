# [PRD] 다이어그램 갱신 — `require_*` 명명 + staff 권한 매트릭스 + Product 조회 컨텍스트

## 배경

`docs/diagram/*.md` 의 시퀀스 다이어그램 7개는 PR #10 / #19 / #20 / #26 누적 변경이 일부만 반영된 상태:

| 다이어그램 | stale 항목 |
| --- | --- |
| `인증_및_권한.md` | PR #20 (`permissions.py` 분리) / PR #26 (`require_*` 명명 + `require_staff_or_admin` 신규) 미반영. §2 가 `get_current_active_admin` 단일 가드 가정. |
| `사용자_프로필.md` | PR #20 (`get_self_or_admin` 이 `permissions.py` 로 이관) / PR #26 (`require_self_or_admin` 명명) 미반영. |
| `사용자_목록_관리자.md` | PR #20 / PR #26 (`require_admin`) 미반영. role 검사 분기를 문자열 비교 (`user.role != "admin"`) 로 묘사 — 도메인 메서드 (`is_admin()`) 정합 부재. |
| `상품_관리_관리자.md` | PR #20 / PR #26 미반영 — **STAFF 도 통과** 라는 새 정책이 누락. `get_current_active_admin` 가 4개 다이어그램 모두에 등장. |
| `상품_조회.md` | **PR #19 (Product 조회 컨텍스트 분리) 완전 미반영.** 응답이 항상 `ProductResponse` 로 묘사 — 실제로는 viewer 별 `ProductPublicView` (anonymous/customer) vs `ProductResponse` (staff/admin) 분기. |
| `README.md` | 인덱스 표의 `인증_및_권한.md` 설명이 옛 가드 이름. |
| `회원가입_로그인.md` | 권한 무관, 변경 없음. |

이 다이어그램들은 신규 개발자/온콜이 흐름 파악에 쓰는 진실원의 일부 — stale 인 상태로 두면 RUNBOOK §9 (정책 진실원) 와의 정합성이 어긋나 운영 마찰.

## 목적

1. **가드 이름 일관성 복원** — 모든 다이어그램이 `require_*` 명명을 사용. 가드 매트릭스 (RUNBOOK §9.2) 와 1:1.
2. **staff 권한 매트릭스 반영** — `상품_관리_관리자.md` 의 4개 endpoint 가 STAFF + ADMIN 통과임을 명시.
3. **Product 조회 컨텍스트 정합** — `상품_조회.md` 가 PR #19 의 viewer 분기 (`get_optional_current_user` + `is_staff_or_above()` + `ProductPublicView`/`ProductResponse` Union 응답) 를 정확히 묘사.
4. **도메인 메서드 정합** — 가드/응답 분기의 검사 표현을 문자열 비교가 아닌 도메인 메서드 (`is_admin()`, `is_staff_or_above()`, `can_manage_products()`) 로 통일.

## 비목적

- **파일명 변경 없음** — `상품_관리_관리자.md` 그대로 유지 (운영자 익숙한 분류 + 외부 참조 안정성). 본문 첫 단락에 "STAFF + ADMIN 통과" 만 명시.
- **PR #15 UserResponse PII 마스킹 (`UserAdminView`) 반영** — `사용자_프로필.md` §3 에 응답 분기 (`Union[UserResponse, UserAdminView]`) 가 들어가야 완전한 정합이지만, 본 PR 의 핵심은 가드 명명 + staff 권한 + Product viewer 분기. PII 마스킹 다이어그램 반영은 별도 후속.
- **`사용자_목록_관리자.md` 의 `UserSummary` 응답 모델 반영** — PR #15 에서 `UserResponse` → `UserSummary` 로 응답 모델이 바뀌었는데 다이어그램은 옛 모델로 묘사. 본 PR 비목적 (별도 후속).
- **다이어그램 신규 추가** — 기존 6개 (+README) 갱신만. 새 흐름 다이어그램 추가는 별도.
- **코드/테스트 변경 없음** — 문서 전용.

## 성공 기준

| 기준 | 검증 |
| --- | --- |
| `grep -rn "get_current_active_admin\|get_self_or_admin" docs/diagram/` → 0 hit | grep |
| 5개 다이어그램 (`인증_및_권한.md`, `사용자_프로필.md`, `사용자_목록_관리자.md`, `상품_관리_관리자.md`, `상품_조회.md`) + README 갱신 | 시각 검토 |
| `상품_관리_관리자.md` 1줄: "STAFF + ADMIN 통과" 명시 + 4개 다이어그램 모두 `require_staff_or_admin` 표시 | grep `require_staff_or_admin` 4 hit |
| `상품_조회.md` 다이어그램에 `get_optional_current_user` + viewer 분기 + `ProductPublicView` 표시 | grep |
| `인증_및_권한.md` §2 가 가드 3개 (`require_admin` / `require_self_or_admin` / `require_staff_or_admin`) 매트릭스 표 + 통과 조건 1:1 매핑 | 시각 검토 |
| 도메인 메서드 표현 일관: `user.role != "admin"` → `not user.is_admin()`, `current_user.is_admin()` 유지 | grep `user.role != ` → 0 hit |
| `pre-commit run --all-files` 종료 코드 0 | 명령 결과 |
| 테스트 카운트 변화 없음 (74 PASS) | `uv run pytest 2>&1 \| tail -1` |
| RUNBOOK §9 매트릭스 ↔ 다이어그램 가드 명명 1:1 | grep `require_` 일치 |

## 설계

### 1. `인증_및_권한.md` 재구성

**현재**: `get_current_user` (§1) + `get_current_active_admin` (§2) 2-§ 구조.

**갱신**:
- 머리말: "인증 (`get_current_user` / `get_optional_current_user`) + 권한 가드 (`require_admin` / `require_self_or_admin` / `require_staff_or_admin`) 의 흐름"
- §1 `get_current_user` — 본문 유지 (시그니처/흐름 변경 없음). 사용처 목록에 `get_optional_current_user` 한 줄 추가 (선택적 인증 — Product 조회에서 사용).
- §2 권한 가드 (`permissions.py`) — 3개 가드 매트릭스 표 + 공통 다이어그램 1개 (가드 일반화)
  - 매트릭스 표 (3행): 가드 / 통과 조건 (도메인 메서드) / 사용처
  - 다이어그램: `Route → Guard → User`. Guard 가 `User.<도메인 메서드>` 호출 → 통과/실패 분기. participant 이름은 `Guard` (가드 일반)
- "핵심 포인트" 갱신: PR #20 모듈 분리 + PR #26 도메인 정책 진실원

### 2. `사용자_프로필.md` §3 갱신

- `get_self_or_admin` (4 hit) → `require_self_or_admin`
- "핵심 포인트" 의 `get_self_or_admin` 언급 → 새 이름

### 3. `사용자_목록_관리자.md` 갱신

- `get_current_active_admin` (4 hit) → `require_admin`
- 다이어그램 분기 `user.role != "admin"` → `not user.is_admin()`
- "핵심 포인트" 의 시그니처 예시 갱신

### 4. `상품_관리_관리자.md` 갱신 (가장 큰 변경)

- 머리말: "**모두 `require_staff_or_admin` 으로 보호 — STAFF + ADMIN 통과**"
- 4개 endpoint 의 의존성 행: `get_current_active_admin` → `require_staff_or_admin`
- 4개 다이어그램의 participant: `Admin as get_current_active_admin` → `Guard as require_staff_or_admin`
- "관리자 검사 통과 가정" → "권한 검사 통과 가정 (`can_manage_products()`)"
- 첫 다이어그램 (상품 생성) 의 분기 라벨: "관리자 통과" → "권한 통과 (STAFF/ADMIN)"
- 실패 응답: `customer` 가 403 임을 명시

### 5. `상품_조회.md` 갱신 (PR #19 정합)

**§1 `GET /products/{id}` 변경 사항**:
- 인증 "불필요" → **"선택적 (`get_optional_current_user`)"**
- 성공 응답: `200 OK + ProductResponse` → `200 OK + ProductResponse (staff/admin) | ProductPublicView (그 외)`
- 다이어그램에 의존성 단계 (Router → OptDep → JWT/User) 추가 + viewer 분기 (`is_staff_or_above()` 통과 → `ProductResponse`, 아니면 `build_public_view(product) → ProductPublicView`)

**§2 `GET /products/` 동일 패턴**:
- 응답: `List[ProductResponse]` → `List[ProductResponse] (staff/admin) | List[ProductPublicView] (그 외)`
- 다이어그램에 viewer 분기 동일 적용

**핵심 포인트** §:
- "공개 엔드포인트" → "**선택적 인증** — viewer 의 권한 계층에 따라 응답 컨텍스트가 달라진다 (PR #19)"
- `ProductPublicView` 의 의미 (inventory 제외) 한 줄 명시

### 6. `README.md` 인덱스 갱신

- 표의 `인증_및_권한.md` 설명: `get_current_user, get_current_active_admin 의존성` → `get_current_user / get_optional_current_user 인증 + 권한 가드 (require_*)`
- `상품_조회.md` 설명에 "viewer 분기 (PR #19)" 보강 (선택)
- `상품_관리_관리자.md` 설명에 "STAFF + ADMIN" 보강 (선택)

### 7. 파일 변경 요약

| 파일 | 변경량 |
| --- | --- |
| `docs/diagram/README.md` | ~3 줄 |
| `docs/diagram/인증_및_권한.md` | §2 구조 재작성 + 매트릭스 표 신설 (~40 줄) |
| `docs/diagram/사용자_프로필.md` | §3 의 4 hit 치환 + 핵심 포인트 (~10 줄) |
| `docs/diagram/사용자_목록_관리자.md` | 4 hit 치환 + 분기 표현 + 핵심 포인트 (~10 줄) |
| `docs/diagram/상품_관리_관리자.md` | 15 hit 치환 + 머리말 + 분기 라벨 (~30 줄) |
| `docs/diagram/상품_조회.md` | 다이어그램 2개 + 표/핵심 포인트 (~40 줄) |
| `docs/diagram/회원가입_로그인.md` | 변경 없음 |

## 영향

- **신규 개발자/온콜**: 다이어그램 ↔ RUNBOOK §9 ↔ 코드 (가드/도메인) 가 모두 같은 명명/매트릭스. 학습 마찰 감소.
- **코드 변경 0** / 테스트 카운트 변화 없음 (74 PASS).
- **과거 PRD/PLAN 의 다이어그램 참조 (1건, `[PLAN]사용자_조회_인증_누락.md:191`)** — 역사 기록 유지, 갱신 안 함.
- **mermaid 렌더링**: participant 이름 변경 시 mermaid 문법 손상 가능성 확인 필요 — 단순 식별자 치환이라 위험 낮음.

## 리스크

1. **mermaid 다이어그램 렌더링 깨짐** — participant 이름의 특수문자 / 길이 문제.
   - 완화: 변경 후 GitHub PR 페이지에서 시각적으로 mermaid 렌더링 확인 (PR description 에 명시).
2. **§2 권한 가드 통합 시 가독성 저하** — 3개 가드를 1개 다이어그램으로 일반화하면 가드별 차이가 흐려질 수 있음.
   - 완화: 매트릭스 표 (가드 × 통과 조건 × 사용처) 로 차이를 표 단계에서 압축 + 다이어그램은 공통 흐름 1개만 유지. 가드별 상세는 RUNBOOK §9.2 참조.
3. **`상품_조회.md` 갱신 범위가 PRD 비목적 (다이어그램 신규 추가) 과 가까워짐** — 사실상 다이어그램이 거의 재작성 수준.
   - 완화: 기존 § 구조 (1: 단건, 2: 목록) 유지. mermaid 만 교체.

## 결정 사항 (확정)

- [x] **파일명 유지** (`상품_관리_관리자.md` 그대로) — 외부 참조 안정성.
- [x] **`상품_조회.md` 의 PR #19 반영 포함** — 다이어그램 정합성 한 번에 마무리.
- [x] **§2 권한 가드 통합 다이어그램 1개** + 매트릭스 표로 가드 3개 차이 압축.
- [x] **`회원가입_로그인.md` 변경 없음** — 권한 무관.
- [x] **PR #15 PII 마스킹 / `UserSummary` 응답 모델 반영은 별도 후속** — 본 PR 비목적.
- [x] **README §권한 단락 추가는 별도 후속** — 본 PR 은 다이어그램 디렉토리에 한정.
- [x] **mermaid 렌더링 검증**: PR description 의 테스트 플랜에 "GitHub PR 페이지에서 다이어그램 렌더링 확인" 항목 포함.

## 참고

- PR #26 (staff 권한 + `require_*` 명명) — 본 PR 의 직접적 원천.
- PR #20 (권한 가드 모듈 분리) — `permissions.py` 신설.
- PR #19 (Product 조회 컨텍스트 분리) — `상품_조회.md` 갱신의 원천.
- PR #10 (`get_self_or_admin` 의존성 추출) — 사용자 프로필 다이어그램의 첫 도입.
- PR #27 (RUNBOOK §9 권한 매트릭스) — 본 PR 의 정합 대상 (다이어그램 ↔ RUNBOOK).
- 코드 진실원: `app/api/permissions.py`, `app/api/dependencies.py`, `app/user/domain.py`, `app/product/router.py`.
