# [PLAN] 문서 마무리 묶음 — 다이어그램 PII / README §환경 / RUNBOOK §9.5

> 연결 PRD: `docs/[PRD]문서_마무리_묶음.md`

## 사전 점검 (Step 0)

- [ ] `git status` clean / `main` baseline / 74 PASS
- [ ] PR #15 의 `UserAdminView` / `UserSummary` / `build_admin_view` / `build_summary` 가 `app/user/schemas.py` 에 존재 확인 완료
- [ ] `app/user/router.py` 의 `GET /users/{id}` 가 본인/관리자 분기로 응답 형태 결정 확인 완료
- [ ] `docs/diagram/사용자_프로필.md` 와 `사용자_목록_관리자.md` 의 변경 위치 확인 완료
- [ ] `README.md` §환경 변수 (line 115-125) 위치 확인 완료
- [ ] `docs/RUNBOOK.md` §9.5 (line 250-258) 위치 확인 완료

## 작업 분해

### Step 1 — `사용자_프로필.md` §3 PII 마스킹 반영

1. 표 "성공" 행: `200 OK + UserResponse` → `200 OK + Union[UserResponse, UserAdminView]`
2. mermaid 마지막 응답 단계에 분기 추가:
   - `if current_user.id == user.id` → `Router-->>Client: 200 OK<br/>UserResponse` (본인)
   - `else (admin 이 타인 조회)` → `Note over Router: build_admin_view(user)` → `Router-->>Client: 200 OK<br/>UserAdminView (email 마스킹 + 이름 제외)`
3. 핵심 포인트에 1줄 추가: `USER_ADMIN_EMAIL_MASKING` 환경 변수로 마스킹 토글 가능 (운영 ON / dev 디버깅 시 OFF, RUNBOOK §2 참조)

### Step 2 — `사용자_목록_관리자.md` `UserSummary` 반영

1. 표 "성공" 행: `List[UserResponse]` → `List[UserSummary]`
2. mermaid 의 router → client 단계:
   - 기존: `Router-->>Client: 200 OK<br/>List[UserResponse]`
   - 갱신: `Note over Router: [build_summary(u) for u in users]` + `Router-->>Client: 200 OK<br/>List[UserSummary] (PII 0건)`
3. 핵심 포인트에 1줄 추가: `UserSummary` 의도 (PR #15 — 목록 페이지의 이메일/이름 무차별 노출 방지, id/username/role/is_active/created_at 만 노출)

### Step 3 — `README.md` §환경 변수 인덱스화

기존 `.env` 4 변수 나열을 RUNBOOK §2 인덱스 + `.env.example` 복사 안내로 재작성. PRD §"설계 §3" 그대로.

### Step 4 — `RUNBOOK.md` §9.5 6단계 확장

5단계 (RUNBOOK §9) 뒤에 6번 다이어그램 단계 추가. PRD §"설계 §4" 그대로.

### Step 5 — 검증

```bash
# 다이어그램 정합
grep -cn "UserAdminView\|build_admin_view" docs/diagram/사용자_프로필.md       # ≥ 2
grep -cn "UserSummary\|build_summary" docs/diagram/사용자_목록_관리자.md       # ≥ 2
grep -c "List\[UserResponse\]" docs/diagram/사용자_목록_관리자.md              # 0

# README §환경 변수
grep -c "SECRET_KEY=\|DATABASE_URL=\|ENVIRONMENT=\|LOG_LEVEL=" README.md       # ≤ 2 (코드 블록 안내가 줄거나 사라짐)
grep -c "RUNBOOK.md" README.md                                                  # ≥ 1 (인덱스)

# RUNBOOK §9.5 6단계
sed -n '250,265p' docs/RUNBOOK.md | grep -c "^[0-9]\. "                         # ≥ 6

# 회귀
uv run pytest 2>&1 | tail -1                                                   # 74 passed
uv run pre-commit run --all-files                                              # 모든 hook Passed
```

### Step 6 — 브랜치 / 커밋 / 푸시 / PR

**브랜치**: `feature/docs-final-cleanup`

**커밋**: 통합 1 커밋. 모두 단일 주제 (문서 잔여 stale 청산).

**커밋 메시지**:
```
docs: 다이어그램 PII 정합 + README §환경 인덱스 + RUNBOOK §9.5 다이어그램 단계

PR #15 (UserAdminView / UserSummary) / PR #22 (USER_ADMIN_EMAIL_MASKING) /
PR #25 (RUNBOOK §2) / PR #28 (다이어그램 진실원 정합) 누적의 잔여 문서
stale 청산.

- 사용자_프로필.md §3: 응답 분기 (Union[UserResponse, UserAdminView])
  + build_admin_view + USER_ADMIN_EMAIL_MASKING 토글 안내
- 사용자_목록_관리자.md: List[UserResponse] → List[UserSummary]
  + build_summary + PII 0건 명시
- README §환경 변수: 4 변수 나열 → RUNBOOK §2 인덱스 + .env.example
  안내 (진실원 분산 해소)
- RUNBOOK §9.5: 5단계 → 6단계 (다이어그램 갱신 단계 추가, PR #28 흐름)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## 산출물 체크리스트

- [ ] `docs/diagram/사용자_프로필.md` §3 (표 + mermaid + 핵심 포인트)
- [ ] `docs/diagram/사용자_목록_관리자.md` (표 + mermaid + 핵심 포인트)
- [ ] `README.md` §환경 변수 (line 115-125 → 인덱스 단락으로 재작성)
- [ ] `docs/RUNBOOK.md` §9.5 (5→6 단계)
- [ ] `docs/[PRD]문서_마무리_묶음.md` (본 PRD)
- [ ] `docs/[PLAN]문서_마무리_묶음.md` (본 파일)
- [ ] 회귀: 74 PASS / pre-commit Passed / grep 모두 통과

## 회귀 방지

문서 영역 자동 회귀 가드 없음 (수동 검토). RUNBOOK §9.5 의 6단계가 향후 정책 변경 PR 의 산출물 체크리스트에 다이어그램 갱신을 자연스럽게 포함시키는 절차적 가드 역할.

## 롤백

`git revert <commit>` — 코드/테스트 영향 0.

## 후속

- README §환경 변수 단락이 RUNBOOK §2 인덱스화되면서, RUNBOOK §2 와 `.env.example` 의 정합성 더욱 중요해짐 — PR #25 이후 누적 변수가 추가될 때 RUNBOOK §2 / `.env.example` 동기화는 매 PR 산출물 체크리스트에 포함되어야 함 (회귀 가드 자체는 별도 후속).

## 참고

- PRD: `docs/[PRD]문서_마무리_묶음.md`
- 원천 PR: #15, #22, #25, #27, #28, #29
- 진실원: `app/user/schemas.py`, `docs/RUNBOOK.md` §2 / §9
