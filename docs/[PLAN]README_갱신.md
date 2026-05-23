# [PLAN] README 갱신 — 로깅 / 구조 트리 / 권한 신설 + 명령 표기 보강

> 연결 PRD: `docs/[PRD]README_갱신.md`

## 사전 점검 (Step 0)

- [ ] `git status` clean / `main` baseline / 74 PASS
- [ ] README.md 현재 구조 (line 1-178) + stale 항목 4개 (로깅 / 구조 / 권한 부재 / 명령) 확인 완료

## 작업 분해

### Step 1 — §프로젝트 구조 트리 갱신 (line 20-57)

기존 트리를 신규 5개 모듈 + alembic 디렉토리 + 신규 schemas/domain 메서드 주석 보강 트리로 교체. PRD §"설계 §1" 참고.

### Step 2 — §로깅 단락 재작성 (line 161-174)

거짓 `get_logger` 코드 제거. PRD §"설계 §3" 의 새 단락으로 교체.

### Step 3 — §권한 단락 신설

§API 문서 (line 144-149) 다음, §테스트 (line 151) 앞에 §"권한 정책" 삽입. PRD §"설계 §2" 참고.

### Step 4 — 명령 표기 보강 (6 곳)

- §의존성 설치: `uv pip install -e .[dev,test]` → `uv sync --all-extras` (1 줄로 단순화)
- §데이터베이스 마이그레이션: `alembic` → `uv run alembic` (2 곳)
- §테스트: `pytest` → `uv run pytest`, `pytest --cov=app` → `uv run pytest --cov=app` (2 곳)
- §애플리케이션 실행: `uvicorn` → `uv run uvicorn` (1 곳)

### Step 5 — 검증

```bash
grep -n "get_logger" README.md                           # 0 hit
grep -cn "setup_logging\|LOG_FORMAT" README.md           # ≥ 2
grep -cn "datetime.py\|permissions.py\|providers.py\|masking.py\|alembic/" README.md  # ≥ 5
grep -cn "require_admin\|require_self_or_admin\|require_staff_or_admin" README.md     # ≥ 3
grep -cn "uv run\|uv sync" README.md                     # ≥ 6
uv run pytest 2>&1 | tail -1                             # 74 passed
uv run pre-commit run --all-files                        # 모든 hook Passed
```

### Step 6 — 브랜치 / 커밋 / 푸시 / PR

**브랜치**: `feature/readme-sync`

**커밋**: 통합 1 커밋 — 단일 파일 4 단락 갱신.

**커밋 메시지**:
```
docs(readme): 누적 정합성 회복 (로깅 / 구조 트리 / 권한 신설 + 명령 표기)

PR #14/#15/#17/#20/#23/#26/#27 누적을 README 에 일괄 반영.

- §로깅: 거짓 get_logger 제거 → loguru 직접 import + setup_logging
  + LOG_FORMAT 환경 변수 토글 명시 (PR #23)
- §프로젝트 구조: 신규 5 모듈 (datetime / permissions / providers /
  masking / logging) + alembic/ 디렉토리 + 신규 schemas/도메인 메서드 주석
- §권한 정책 신설: RUNBOOK §9 인덱스 + 가드 3개 (require_*) 명명
  + 정책 변경 순서 RUNBOOK §9.5 안내
- 명령 표기: pytest / alembic / uvicorn → uv run 패턴 + 설치를
  uv sync --all-extras 로 일관 (handoff §1 / RUNBOOK §5)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## 산출물 체크리스트

- [ ] `README.md` §구조 트리 (~30 line 갱신)
- [ ] `README.md` §로깅 (~15 line 재작성)
- [ ] `README.md` §권한 정책 신설 (~15 line)
- [ ] `README.md` 명령 6 곳 표기 보강
- [ ] `docs/[PRD]README_갱신.md` (본 PRD 파일)
- [ ] `docs/[PLAN]README_갱신.md` (본 파일)
- [ ] 회귀: 74 PASS / pre-commit Passed / grep 모두 통과

## 회귀 방지

- **README ↔ 코드 drift**: CI 게이트 또는 회귀 가드 없음. handoff §6 ⬜ "README ↔ 모듈 자동 검증" 같은 후속 검토 가능하나 본 PR 비범위.

## 롤백

`git revert <commit>` — 코드/테스트 영향 0.

## 후속

- README §환경 변수 단락 → RUNBOOK §2 전면 인덱스화 (별도 ⬜).
- 다이어그램 README 인덱스 ↔ README §권한 단락 cross-link 일관성 검토.

## 참고

- PRD: `docs/[PRD]README_갱신.md`
- 원천 PR: #14/#15/#17/#20/#23/#26/#27/#28
- 진실원: `app/core/logging.py`, `app/api/permissions.py`, `docs/RUNBOOK.md` §2 / §9
