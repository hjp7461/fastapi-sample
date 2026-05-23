# [PLAN] RUNBOOK 환경 변수 단락 보강 (+ .env.example 동기화)

> PRD: `docs/[PRD]RUNBOOK_환경변수_단락_보강.md`
> 브랜치: `feature/runbook-env-vars-sync`
> 분류: 문서 (운영 핸드북)

---

## 1. 사전 점검

- [ ] `git status` → `main`, clean
- [ ] `git log --oneline -3` 최상단이 PR #24 머지 (`b4811a3`)
- [ ] `uv run pytest 2>&1 | tail -1` → `64 passed`
- [ ] `gh pr list --state open` → 비어 있음
- [ ] 변경 대상:
  - `docs/RUNBOOK.md` (§2 매트릭스 6행 + 수집 파이프라인 예시)
  - `.env.example` (AUTO_CREATE_TABLES 제거 + 6 변수 추가 + 주석 보강)

---

## 2. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout -b feature/runbook-env-vars-sync
```

### Step 2 — RUNBOOK §2 매트릭스에 6행 추가

PRD §5.1 의 6행을 기존 `BCRYPT_ROUNDS` 행 아래에 추가. 표 정렬은 그대로 유지.

기존 §2 의 "AUTO_CREATE_TABLES 는 PR #14 에서 폐기" 참고 문구를 한 줄 보강 — `.env.example` 도 정리됐다는 사실 명시.

### Step 3 — RUNBOOK §2 끝에 "수집 파이프라인 연결 예시" 단락

PRD §5.2 그대로. 5줄 이내. `LOG_FORMAT=json` + `LOG_FILE` 두 줄짜리 코드 블록.

### Step 4 — `.env.example` 갱신

PRD §5.3 의 예시 형태대로:
- `AUTO_CREATE_TABLES=true` 라인 제거
- 단락 구분 (환경/DB/JWT/bcrypt/응답 PII/로깅/OAuth) 주석으로 명확화
- `USER_ADMIN_EMAIL_MASKING=true` 추가
- `LOG_LEVEL`, `LOG_FORMAT` 활성 (default 값)
- `LOG_FILE`, `LOG_FILE_ROTATION`, `LOG_FILE_RETENTION` 은 주석 처리 (default 미설정/활성화는 의도적 선택)
- `ACCESS_TOKEN_EXPIRE_MINUTES=30` 추가 (RUNBOOK §2 에 있는 변수와 일치)
- `GOOGLE_CLIENT_*` 상단에 "현재 코드 미사용 — 향후 도입 후보" 주석

### Step 5 — 회귀 (pytest + ruff + pre-commit)

문서만 변경이라 회귀 가드는 단순 유지 확인:

```bash
/usr/local/bin/mise exec -- uv run pytest 2>&1 | tail -3
/usr/local/bin/mise exec -- uv run ruff check . 2>&1 | tail -2
/usr/local/bin/mise exec -- uv run ruff format --check . 2>&1 | tail -2
/usr/local/bin/mise exec -- uv run pre-commit run --all-files 2>&1 | tail -10
```

기대:
- pytest 64 passed
- ruff 양쪽 종료 코드 0
- pre-commit 모든 hook Passed (trailing-whitespace / end-of-file-fixer 가 새 markdown / env 파일에 자동 수정 발생 가능 → 발생 시 같은 커밋에 적용)

### Step 6 — 커밋 (단일)

문서 + 예시 두 파일만이라 단일 커밋이 자연스러움:

```
docs(runbook): §2 환경 변수 매트릭스에 PR #22/#23 변수 6개 추가 + .env.example 동기화

- RUNBOOK §2: USER_ADMIN_EMAIL_MASKING + LOG_* 5개 행 추가, 수집 파이프라인
  연결 예시 단락 추가 (LOG_FORMAT=json + LOG_FILE)
- .env.example:
  · AUTO_CREATE_TABLES 제거 (PR #14 에서 폐기됨)
  · 단락 구분 주석으로 가시성 보강
  · USER_ADMIN_EMAIL_MASKING / LOG_LEVEL / LOG_FORMAT 활성
  · LOG_FILE / LOG_FILE_ROTATION / LOG_FILE_RETENTION 은 주석 (의도적 선택)
  · ACCESS_TOKEN_EXPIRE_MINUTES 추가 (RUNBOOK §2 와 일치)
  · GOOGLE_CLIENT_* 에 "현재 코드 미사용 — 향후 도입 후보" 주석

운영자 관점에서 RUNBOOK §2 ↔ .env.example ↔ Settings 세 곳의 진실원 일치 복원.
README.md §로깅 / §프로젝트 구조 트리는 별도 후속 (handoff §6).
```

### Step 7 — 푸시 + PR

```bash
git push -u origin feature/runbook-env-vars-sync
```

PR title 예:
```
docs(runbook): §2 환경 변수 매트릭스 보강 (PR #22/#23 변수 6개) + .env.example 동기화
```

---

## 3. 산출물 체크리스트

- [ ] `docs/RUNBOOK.md` §2: 6행 추가 + 수집 파이프라인 예시 단락
- [ ] `docs/RUNBOOK.md` §2 "AUTO_CREATE_TABLES 폐기" 참고 문구 보강
- [ ] `.env.example`: AUTO_CREATE_TABLES 제거, 6 변수 추가, 주석 보강
- [ ] `uv run pytest` → 64 passed
- [ ] `uv run ruff check .` / `ruff format --check .` 종료 코드 0
- [ ] `uv run pre-commit run --all-files` 모든 hook Passed
- [ ] 커밋 (한글 메시지 + Co-Authored-By 푸터)
- [ ] PR description 에 변경 매트릭스 + 후속 명시

---

## 4. 테스트 케이스 (신규 0건)

문서/예시 변경만이라 단위/통합 테스트 0건. 회귀 가드는 기존 64 + pre-commit.

---

## 5. 회귀 방지

| 검증 | 명령 | 기대 |
| --- | --- | --- |
| 전체 회귀 | `uv run pytest` | 64 passed |
| 린트/포맷 | `uv run ruff check .` / `ruff format --check .` | 둘 다 종료 코드 0 |
| pre-commit | `uv run pre-commit run --all-files` | 모든 hook Passed |

---

## 6. 롤백

- 단일 PR `revert`. 2 파일 (RUNBOOK + .env.example) + docs PRD/PLAN. 코드 무변경이라 영향 0.

---

## 7. 후속 (PRD §7)

- README.md §로깅 단락 갱신 (거짓 `get_logger` 제거, `setup_logging` 반영)
- README.md §프로젝트 구조 트리 갱신 (datetime / permissions / providers / masking / logging 신규)
- GOOGLE_CLIENT_* 변수 정리 (OAuth 도입 결정 후)
- RUNBOOK §3-9 점검 (최신성 검증)
- CI 도입 시 §운영 점검 단락 보강

---

## 8. 참고

- PRD: `docs/[PRD]RUNBOOK_환경변수_단락_보강.md`
- PR #22 / #23 PRD/PLAN (도입 컨텍스트)
- PR #14 PRD/PLAN (AUTO_CREATE_TABLES 폐기)
- `app/core/config.py::Settings` (단일 진실원)
