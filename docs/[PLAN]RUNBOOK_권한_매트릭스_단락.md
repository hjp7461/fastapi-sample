# [PLAN] RUNBOOK §9 권한 매트릭스 단락 추가

> 연결 PRD: `docs/[PRD]RUNBOOK_권한_매트릭스_단락.md`

## 사전 점검 (Step 0)

- [ ] `git status` clean / `main` baseline
- [ ] `uv run pytest 2>&1 | tail -1` → **74 passed**
- [ ] `docs/RUNBOOK.md` 현재 §9 (참고) 위치 (line 190~199) 확인 완료
- [ ] 외부 § 참조 grep 완료 — `[HANDOFF]` 의 `§2 환경 변수`, `§3 자동화` 등은 §1~§8 범위 → 영향 없음

## 작업 분해

### Step 1 — RUNBOOK 헤딩 시프트 (§9 → §10)

**파일**: `docs/RUNBOOK.md`

**작업**: 기존 `## 9. 참고 문서 / 링크` → `## 10. 참고 문서 / 링크` 로 변경 (단순 치환).

**검증**: `grep -n "^## " docs/RUNBOOK.md` → §1~§8 + §10 만 존재 (§9 슬롯 비어있음).

### Step 2 — §9 권한 매트릭스 신설

**파일**: `docs/RUNBOOK.md` (Step 1 의 §10 바로 앞에 §9 신설)

**작업**: PRD §"설계 §1" 의 4개 소단락 (§9.1~§9.5) 을 그대로 삽입.

- §9.1 역할 계층 (계층 다이어그램 + 도메인 메서드 표 3행)
- §9.2 권한 가드 (3행 표 + 401/400 사전 평가 주석)
- §9.3 엔드포인트 × 역할 매트릭스 (~13행)
- §9.4 정책 결정 (B-2 변형 의도 명시)
- §9.5 정책 변경 시 갱신 순서 (5단계)

**검증**: `grep -n "^## " docs/RUNBOOK.md` → §1~§10 연속 / `grep -n "^### " docs/RUNBOOK.md` → §9.1~§9.5 5개.

### Step 3 — 정합성 검증

**작업**:

1. `app/api/permissions.py` docstring 매트릭스 ↔ RUNBOOK §9.2 행 일치 시각 비교
2. `app/user/domain.py` 메서드 시그니처 ↔ RUNBOOK §9.1 도메인 메서드 표 일치
3. `tests/{user,product}/test_router.py` 의 매트릭스 (anonymous/customer/staff/admin) ↔ RUNBOOK §9.3 셀 값 일치
4. `pre-commit run --all-files` 통과

**검증 명령**:

```bash
grep -n "require_admin\|require_self_or_admin\|require_staff_or_admin" app/api/permissions.py docs/RUNBOOK.md
uv run pytest 2>&1 | tail -1
uv run pre-commit run --all-files
```

기대 결과:
- 가드 이름 6 hit 일치
- 74 passed
- pre-commit 모든 hook Passed

### Step 4 — 커밋 / 푸시 / PR

**브랜치**: `feature/runbook-permission-matrix`

**커밋**: 단일 커밋 — 헤딩 시프트 + §9 신설이 한 파일이라 분리 의미 적음.

**커밋 메시지**:
```
docs(runbook): §9 권한 매트릭스 단락 신설 (역할 계층 / 가드 / 엔드포인트 × 역할 / 정책 변경 순서)

PR #26 후속 — STAFF/ADMIN 권한 정책의 운영자 진실원을 RUNBOOK 으로
이관. 도메인 메서드 → 가드 → 라우터 → 테스트 → RUNBOOK 갱신 순서를
§9.5 에 명시해 향후 정책 drift 방지.

기존 §9 (참고 문서) → §10 으로 한 칸만 밀어 외부 § 참조 (§1~§8)
안정성 유지.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

**PR 본문**: 본 PLAN §"PR 본문 초안" 참고.

## PR 본문 초안 (Step 4 에서 사용)

**제목**: `docs(runbook): §9 권한 매트릭스 단락 신설 + §10 참고 시프트`

**본문**:

```markdown
## 배경
PR #26 머지로 STAFF/ADMIN 권한 정책 (B-2 변형: product 변경은 staff/admin, 사용자 관리는 admin only) 이 확정됐지만 운영자가 한 곳에서 확인할 진실원이 RUNBOOK 에 부재. 코드 3곳 (도메인 메서드 / 가드 / 라우터) 을 거쳐야 정책 파악 가능.

## 변경
- `docs/RUNBOOK.md` §9 "권한 매트릭스" 신설:
  - §9.1 역할 계층 (`CUSTOMER ⊂ STAFF ⊂ ADMIN`) + 도메인 메서드 3행
  - §9.2 권한 가드 (`require_admin` / `require_self_or_admin` / `require_staff_or_admin`) 3행 + 인증 단계 우선 주석
  - §9.3 엔드포인트 × 역할 매트릭스 (anonymous/CUSTOMER/STAFF/ADMIN) 13행
  - §9.4 B-2 정책 결정 의도 (도메인 경계 = product / user)
  - §9.5 정책 변경 시 갱신 순서 (도메인 → 가드 → 라우터 → 테스트 → RUNBOOK)
- 기존 §9 (참고) → §10 으로 시프트 (헤딩 번호만 변경, 본문 동일)

## 영향
- **코드 변경 0** / 테스트 카운트 변화 0 (74 PASS 유지)
- 외부 § 참조 (`§2 환경 변수`, `§3 자동화` 등) 안정성 100% 유지
- 운영자 시점 진실원 일치: `app/api/permissions.py` ↔ `app/user/domain.py` ↔ RUNBOOK §9

## 테스트 플랜 (리뷰어용)
- [ ] `uv run pytest` → 74 passed
- [ ] `uv run pre-commit run --all-files` → 모든 hook Passed
- [ ] `grep -n "^## " docs/RUNBOOK.md` → §1~§10 연속
- [ ] RUNBOOK §9.2 의 가드 3행이 `app/api/permissions.py` docstring 매트릭스와 일치
- [ ] RUNBOOK §9.3 매트릭스 셀이 `tests/{user,product}/test_router.py` 회귀 테스트의 상태 코드와 일치

## 비목적
- 권한 정책 자체 변경 없음 (PR #26 결과를 문서로 반영)
- 인증 흐름 설명 없음 (`docs/diagram/인증_및_권한.md` 가 진실원)
- README §권한 단락 추가 — 별도 후속

## 후속
- 다이어그램 (`docs/diagram/`) 옛 가드 이름 + staff 권한 반영
- README §권한 단락 추가 (선택)
- 권한 정책 변경 시 RUNBOOK §9 갱신 회귀 가드 도입 검토

## PRD / PLAN
- `docs/[PRD]RUNBOOK_권한_매트릭스_단락.md`
- `docs/[PLAN]RUNBOOK_권한_매트릭스_단락.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## 산출물 체크리스트

- [ ] `docs/RUNBOOK.md` §9 권한 매트릭스 신설 (4 소단락 + 정책 변경 순서)
- [ ] `docs/RUNBOOK.md` §9 → §10 (참고 문서) 헤딩 시프트
- [ ] `docs/[PRD]RUNBOOK_권한_매트릭스_단락.md` (이 PRD 본 파일)
- [ ] `docs/[PLAN]RUNBOOK_권한_매트릭스_단락.md` (본 파일)
- [ ] 회귀: 74 PASS / pre-commit Passed / 외부 § 참조 stale 0건

## 테스트 케이스 (회귀 가드)

문서 변경 단독이라 신규 자동화 테스트는 없음. 다음 grep 들이 정합성 가드:

```bash
# §9 신설 확인
grep -n "^## 9\. 권한 매트릭스" docs/RUNBOOK.md

# §10 시프트 확인
grep -n "^## 10\. 참고" docs/RUNBOOK.md

# 가드 이름 일치 (RUNBOOK ↔ permissions.py)
grep -n "require_admin\|require_self_or_admin\|require_staff_or_admin" app/api/permissions.py docs/RUNBOOK.md

# 외부 § 참조 stale 여부
grep -n "RUNBOOK §" docs/[HANDOFF]세션_이어가기.md
```

## 회귀 방지

1. **권한 정책 drift**: §9.5 갱신 순서를 RUNBOOK 단락 자체에 명시 → 향후 정책 변경 PR 의 PRD 가 §9 갱신을 산출물 체크리스트에 포함하기 쉬워짐.
2. **§ 번호 안정성**: 외부 참조 (§1~§8) 변경 없음. §10 (참고) 만 한 칸 밀려서, 만약 외부에서 `§9 참고` 같은 표현이 있다면 갱신 — 현재는 0 hit.

## 롤백

`git revert <commit>` 으로 단순 롤백. 코드/테스트 영향 0 이라 운영 위험 없음.

## 후속

PRD §"리스크 / 비목적" 의 후속:

1. **다이어그램 (`docs/diagram/`)** 의 옛 가드 이름 (`get_current_active_admin` 등) → `require_*` 갱신 + staff 권한 매트릭스 반영. 마스터 목록 ⬜ 기존 행 (`다이어그램 staff 권한 + require_* 명명 반영`) 우선순위 그대로.
2. **README §권한 단락** — 본 PR 머지 후 README 도 권한 진실원 인덱스 한 줄로 RUNBOOK §9 를 가리키게.
3. **권한 정책 변경 회귀 가드** — pre-commit 또는 CI 에서 "`app/api/permissions.py` 변경 시 RUNBOOK §9 도 같은 PR 에 포함" 강제. 도입 시점 미정 (정책 변경 빈도가 낮아 비용 대비 효과 추후 검토).

## 참고

- PRD: `docs/[PRD]RUNBOOK_권한_매트릭스_단락.md`
- 원천 PR: #26
- 진실원 파일: `app/api/permissions.py`, `app/user/domain.py`
- 회귀 테스트 매트릭스: `tests/{user,product}/test_router.py`
