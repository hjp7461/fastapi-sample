# [PLAN] pre-commit hook 도입 — 로컬 가드

> PRD: `docs/[PRD]pre_commit_hook_도입.md`
> 브랜치: `feature/pre-commit-hook`
> 분류: 개발 표면

---

## 1. 사전 점검

- [ ] `git status` → `main`, clean
- [ ] `git log --oneline -3` 최상단이 PR #23 머지 (`e55efe2`)
- [ ] `uv run pytest 2>&1 | tail -1` → `64 passed`
- [ ] `gh pr list --state open` → 비어 있음
- [ ] `.pre-commit-config.yaml` / pre-commit 도구 부재 재확인 (현재 없음)
- [ ] 변경 대상:
  - `pyproject.toml` (dev extras + pre-commit)
  - `.pre-commit-config.yaml` (신규)
  - `README.md` (§설치 및 실행 보강)
  - `uv.lock` (pre-commit transitive)

---

## 2. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout -b feature/pre-commit-hook
```

### Step 2 — `pyproject.toml` dev extras 에 pre-commit 추가

```toml
[project.optional-dependencies]
dev = [
    "mypy>=1.2.0",
    "pre-commit>=4.0",
    "ruff>=0.6.0",
]
```

`uv sync --all-extras` 실행 → `uv.lock` 갱신 확인. transitive 변경 정도 확인.

### Step 3 — `.pre-commit-config.yaml` 신설

PRD §5.1 그대로:
- `astral-sh/ruff-pre-commit` (`ruff` + `--fix`, `ruff-format`) — rev `v0.11.4`
- `pre-commit/pre-commit-hooks` (5 hook) — rev `v5.0.0`

### Step 4 — hook 정의 검증 + 전체 파일 실행

```bash
uv run pre-commit validate-config
uv run pre-commit run --all-files
```

기대:
- `validate-config` → "Configuration valid"
- `run --all-files` → 모든 hook Passed (PR #21 으로 이미 lint clean 이라 ruff 차이 없음 예상)

**잠재 영향**:
- `trailing-whitespace` / `end-of-file-fixer` 가 일부 markdown / yaml 파일에서 차이를 만들 가능성 → 발생 시 같은 PR 에서 자동 적용 후 별도 커밋 분리.
- ruff `--fix` 가 PR #21 후 lint clean 이라 차이 없을 것이지만, 변경 발생 시 재커밋 + PR description 에 명시.

### Step 5 — README.md §설치 및 실행 보강

`### 의존성 설치` 단락 끝 또는 별도 `### Pre-commit hook (선택, 권장)` 단락 추가 — PRD §5.3 그대로:
- `uv run pre-commit install` 안내
- `uv run pre-commit run --all-files` 전체 실행 안내

### Step 6 — 회귀 (pytest + ruff)

```bash
/usr/local/bin/mise exec -- uv run pytest 2>&1 | tail -3
/usr/local/bin/mise exec -- uv run ruff check . 2>&1 | tail -2
/usr/local/bin/mise exec -- uv run ruff format --check . 2>&1 | tail -2
```

기대:
- pytest: 64 passed (신규 테스트 0 — pre-commit 자체는 런타임 영향 없음)
- ruff check / format --check: 종료 코드 0

### Step 7 — 커밋 (단일 — hook 자동 수정 있으면 분리)

기본:
- 커밋 1: `chore(dev): pre-commit hook 도입 (ruff + 기본 hooks)`
  - `pyproject.toml`, `uv.lock`, `.pre-commit-config.yaml`, `README.md`, docs PRD/PLAN

만약 Step 4 의 `pre-commit run --all-files` 가 자동 수정을 발생시키면:
- 커밋 2: `style: pre-commit hook 첫 실행 자동 수정 (trailing-whitespace / EOF newline 등)`
  - 영향 받은 파일 별도 커밋

### Step 8 — 푸시 + PR 생성

```bash
git push -u origin feature/pre-commit-hook
```

PR title 예:
```
chore(dev): pre-commit hook 도입 (ruff + 기본 hooks)
```

PR description: 배경/목적 (PRD §1-2), 변경 매트릭스 (PRD §5), 검증 결과 (Step 4/6), 비목적/후속.

---

## 3. 산출물 체크리스트

- [ ] `pyproject.toml`: dev extras 에 `pre-commit>=4.0`
- [ ] `uv.lock`: 갱신 (pre-commit + transitive)
- [ ] `.pre-commit-config.yaml`: 신규 (ruff + 기본 5 hooks)
- [ ] `README.md`: §설치 및 실행에 pre-commit 안내 추가
- [ ] `uv run pre-commit validate-config` → Configuration valid
- [ ] `uv run pre-commit run --all-files` → all hooks Passed
- [ ] `uv run pytest` → 64 passed
- [ ] `uv run ruff check .` / `ruff format --check .` 종료 코드 0
- [ ] 커밋 (한글 메시지 + Co-Authored-By 푸터)
- [ ] PR description 에 변경 매트릭스 + 검증 결과

---

## 4. 테스트 케이스 (신규 0건)

본 PR 은 도구 도입 + 설정 파일이라 런타임 동작 변경 없음 → 신규 단위/통합 테스트 0건. 검증은 도구 자체 명령으로 대체:

| 검증 | 명령 |
| --- | --- |
| 설정 valid | `uv run pre-commit validate-config` |
| 전체 hook 실행 | `uv run pre-commit run --all-files` |
| 기존 회귀 | `uv run pytest` |
| ruff clean | `uv run ruff check .` / `ruff format --check .` |

---

## 5. 회귀 방지

| 검증 | 명령 | 기대 |
| --- | --- | --- |
| pre-commit 동작 | `uv run pre-commit run --all-files` | all hooks Passed |
| 전체 회귀 | `uv run pytest` | 64 passed |
| ruff 가드 | `uv run ruff check .` / `ruff format --check .` | 둘 다 종료 코드 0 |

---

## 6. 롤백

- 단일 PR `revert`. 영향 범위:
  - `pyproject.toml` / `uv.lock` — pre-commit 제거
  - `.pre-commit-config.yaml` 삭제
  - `README.md` 안내 제거
- 이미 `pre-commit install` 한 개발자의 로컬 `.git/hooks/pre-commit` 은 자동 제거 안 됨 → `pre-commit uninstall` 수동 실행 안내.

---

## 7. 후속 (PRD §7)

- CI 도입 (GitHub Actions) — 동일 hook 재사용 (`uv run pre-commit run --all-files` + pytest + alembic)
- mypy hook 활성화 (위반 청산 후)
- 추가 hook (secret detection / conventional commits / mdformat)
- `pre-commit autoupdate` 정기 실행 가이드
- RUNBOOK §환경 변수 단락 보강 (PR #22/#23 후속 묶음)

---

## 8. 참고

- PRD: `docs/[PRD]pre_commit_hook_도입.md`
- PR #21 PRD/PLAN (lint clean baseline 출발선)
- pre-commit docs: https://pre-commit.com/
- `astral-sh/ruff-pre-commit`: https://github.com/astral-sh/ruff-pre-commit
- `pre-commit/pre-commit-hooks`: https://github.com/pre-commit/pre-commit-hooks
