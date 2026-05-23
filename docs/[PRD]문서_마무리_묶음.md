# [PRD] 문서 마무리 묶음 — 다이어그램 PII 정합 / README §환경 변수 인덱스화 / RUNBOOK §9.5 다이어그램 단계

## 배경

PR #19/#20/#26/#27/#28/#29 흐름으로 권한 / 진실원 정합성은 회복됐지만, 문서 정합성의 **잔여 stale** 3건이 남음:

| 항목 | 현재 상태 | 진실원 |
| --- | --- | --- |
| `docs/diagram/사용자_프로필.md` §3 | `GET /users/{id}` 응답이 `UserResponse` 단일로 묘사 | 실제 (PR #15) — `Union[UserResponse, UserAdminView]`. 본인 → `UserResponse`, 관리자가 타인 → `UserAdminView` (email 마스킹 + 이름 제외, `USER_ADMIN_EMAIL_MASKING` 토글) |
| `docs/diagram/사용자_목록_관리자.md` | 응답이 `List[UserResponse]` 로 묘사 | 실제 (PR #15) — `List[UserSummary]` (PII 0건: id/username/role/is_active/created_at 만). `build_summary(u)` 변환 |
| `README.md` §환경 변수 (line 115-125) | 4개 변수 (SECRET_KEY / DATABASE_URL / ENVIRONMENT / LOG_LEVEL) | RUNBOOK §2 가 진실원 (BCRYPT_ROUNDS / USER_ADMIN_EMAIL_MASKING / LOG_FORMAT / LOG_FILE / LOG_FILE_ROTATION / LOG_FILE_RETENTION 등 6+ 변수 부재) |
| `docs/RUNBOOK.md` §9.5 | 5단계 (도메인 → 가드 → 라우터 → 테스트 → RUNBOOK) | PR #28 으로 다이어그램이 정합 대상에 포함됨 — "다이어그램" 단계 부재 시 다음 정책 변경 PR 에서 다이어그램 drift 위험 |

## 목적

1. **`사용자_프로필.md` §3 의 PII 마스킹 다이어그램 정합** — viewer 가 본인 ↔ 관리자 분기 + `build_admin_view(user)` + `USER_ADMIN_EMAIL_MASKING` 토글 명시. (PR #15 의 시각화 정합)
2. **`사용자_목록_관리자.md` 응답 모델 정합** — `List[UserResponse]` → `List[UserSummary]` + `build_summary(u)` 변환 + PII 0건 명시. (PR #15 의 시각화 정합)
3. **README §환경 변수 인덱스화** — 4 변수 나열을 **RUNBOOK §2 인덱스 한 단락**으로 축약. 진실원 분산 해소.
4. **RUNBOOK §9.5 6단계 확장** — 정책 변경 시 갱신 순서에 "다이어그램 (`docs/diagram/`)" 단계 추가. PR #28 이후 표면 drift 방지 구조 보강.

## 비목적

- **다른 다이어그램 갱신** — `상품_*.md`, `회원가입_로그인.md`, `인증_및_권한.md` 는 PR #28 에서 이미 정합 회복. 본 PR 범위 밖.
- **README §환경 변수 단락 전면 재작성 (필수 변수 목록 새로 작성)** — RUNBOOK §2 가 진실원이라 README 에선 인덱스 한 단락만으로 충분. 변수 매트릭스 복제 부재가 정책.
- **RUNBOOK 의 다른 § 갱신** — 본 PR 은 §9.5 한 단락만.
- **코드 변경** — 0 (문서 전용).
- **테스트 추가** — 다이어그램/문서는 자동화 회귀 가드 없음 (수동 점검).

## 성공 기준

| 기준 | 검증 |
| --- | --- |
| `사용자_프로필.md` §3 다이어그램에 `Union[UserResponse, UserAdminView]` + `build_admin_view` 표시 | grep `UserAdminView\|build_admin_view` ≥ 2 |
| `사용자_목록_관리자.md` 의 응답 표/다이어그램이 `List[UserSummary]` + `build_summary` 표시 | grep `UserSummary\|build_summary` ≥ 2 / `List[UserResponse]` 0 hit |
| `README.md` §환경 변수가 RUNBOOK §2 인덱스 단락으로 축약 (5+ 변수 나열 제거) | grep `RUNBOOK.md` ≥ 1 + 변수 나열 행 ≤ 2 |
| `RUNBOOK.md` §9.5 가 6단계 (다이어그램 포함) | grep `^[0-9]\. ` in §9.5 ≥ 6 |
| `pre-commit run --all-files` 종료 코드 0 | 명령 결과 |
| 테스트 카운트 변화 없음 (74 PASS) | `uv run pytest 2>&1 \| tail -1` |
| 외부 § 참조 (`§2`, `§9` 등) 안정성 유지 | grep |

## 설계

### 1. `사용자_프로필.md` §3 갱신

**현재 (line 102-155)**: 의존성 표 + mermaid + 핵심 포인트. 응답은 `200 OK + UserResponse` 단일.

**갱신**:
- 표 "성공" 행: `200 OK + UserResponse` → `200 OK + Union[UserResponse, UserAdminView]`
- 다이어그램의 마지막 응답 분기 추가:
  - `if current_user.id == user.id` → `UserResponse`
  - else (admin 이 타인 조회) → `build_admin_view(user)` → `UserAdminView` (email 마스킹 + 이름 제외)
- 핵심 포인트에 한 줄 추가: `USER_ADMIN_EMAIL_MASKING` 토글 안내 (RUNBOOK §2 참조)

### 2. `사용자_목록_관리자.md` 갱신

**현재**: 응답 표 `List[UserResponse]` / 다이어그램 마지막 화살표 `200 OK + List[UserResponse]`.

**갱신**:
- 표 "성공" 행: `List[UserResponse]` → `List[UserSummary]`
- 다이어그램의 service → router 단계 후 router → client 응답:
  - `Note over Router: [build_summary(u) for u in users]`
  - `Router-->>Client: 200 OK<br/>List[UserSummary]` (PII 0건)
- 핵심 포인트에 한 줄 추가: `UserSummary` 의도 (PR #15 — 목록 페이지 PII 무차별 노출 방지)

### 3. `README.md` §환경 변수 갱신 (line 115-125)

**현재**:
```bash
# .env
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite+aiosqlite:///./app.db
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

**갱신**:
```markdown
### 환경 변수 설정

환경 변수 매트릭스의 진실원은 [`docs/RUNBOOK.md`](docs/RUNBOOK.md) §2 입니다.
빠른 시작에는 `.env.example` 을 복사하세요:

```bash
cp .env.example .env
# 필요한 값만 수정 (특히 SECRET_KEY 는 운영에서 반드시 무작위 값으로)
```

전체 변수 목록 / 기본값 / 의미는 RUNBOOK §2 표 참고. 본 README 는 인덱스만 제공합니다.
```

### 4. `RUNBOOK.md` §9.5 6단계 확장

**현재 5단계**:
1. 도메인 메서드
2. 권한 가드
3. 라우터
4. 회귀 테스트
5. 본 RUNBOOK §9

**갱신 6단계** (5번 뒤에 다이어그램 추가):
1. 도메인 메서드
2. 권한 가드
3. 라우터
4. 회귀 테스트
5. 본 RUNBOOK §9
6. **다이어그램** (`docs/diagram/`) — 가드/응답 분기/Endpoint × 역할 매트릭스가 다이어그램과 1:1 일치하도록 갱신. PR #28 흐름.

### 5. 파일 변경 요약

| 파일 | 변경량 |
| --- | --- |
| `docs/diagram/사용자_프로필.md` | §3 표 1행 + mermaid 응답 분기 (~10 line) + 핵심 포인트 1줄 |
| `docs/diagram/사용자_목록_관리자.md` | 표 1행 + mermaid 응답 분기 (~3 line) + 핵심 포인트 1줄 |
| `README.md` | §환경 변수 단락 재작성 (~10 line) |
| `docs/RUNBOOK.md` | §9.5 1단계 추가 |

## 영향

- **신규 컨트리뷰터 / 운영자**: PII 응답 분기를 다이어그램으로 즉시 이해. README 의 환경 변수 = RUNBOOK §2 단일 진실원.
- **코드 변경 0** / 테스트 카운트 변화 없음 (74 PASS).
- **외부 § 참조 안정성** 유지 (§ 번호 변경 없음).
- **handoff §6 ⬜ 3건 동시 해소** + 마지막 잔여 문서 stale 청산.

## 리스크

1. **README §환경 변수 단순화로 빠른 시작 정보 부족** — 신규 컨트리뷰터가 RUNBOOK 까지 가야 하는 1-hop 비용.
   - 완화: `.env.example` 복사 명령 + "SECRET_KEY 는 무작위" 만 명시. 그 외는 RUNBOOK §2 가 위치적으로 가까움 (`docs/RUNBOOK.md` 1 클릭).
2. **다이어그램 mermaid 응답 분기 추가 시 가독성 저하** — 분기 수 증가.
   - 완화: 본문 분기 1단계만 추가 (`if viewer is self` vs else). 색상/스타일 추가 없음.

## 결정 사항 (확정)

- [x] **3+1 단락 묶음 1 PR** (다이어그램 2 + README + RUNBOOK §9.5).
- [x] **README §환경 변수: 변수 매트릭스 복제 안 함**. RUNBOOK §2 인덱스 + `.env.example` 안내만.
- [x] **RUNBOOK §9.5 6단계** — 다이어그램을 마지막에 추가 (RUNBOOK 갱신 후 다이어그램 — 표면이 진실원 갱신 순서).
- [x] **`사용자_프로필.md` §1/§2 (me 조회/수정) 는 변경 없음** — 본인만 사용하므로 PII 분기 없음. §3 만 변경.

## 참고

- PR #15 (UserResponse PII 마스킹 — `UserAdminView` / `UserSummary` 도입)
- PR #22 (`USER_ADMIN_EMAIL_MASKING` 환경 변수 토글)
- PR #25 (RUNBOOK §2 환경 변수 매트릭스 보강)
- PR #27 (RUNBOOK §9 권한 매트릭스 신설)
- PR #28 (다이어그램 5개 갱신 — 본 PR 의 직접적 보강 대상)
- PR #29 (README 누적 정합성 회복 — 본 PR 의 §환경 변수 단락 보강 대상)
- 진실원: `app/user/schemas.py` (UserAdminView / UserSummary 정의), `docs/RUNBOOK.md` §2 / §9
