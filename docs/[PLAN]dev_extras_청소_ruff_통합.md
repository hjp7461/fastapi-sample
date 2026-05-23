# [PLAN] dev extras 청소 — black/isort → ruff 단일화

> PRD: `docs/[PRD]dev_extras_청소_ruff_통합.md`
> 브랜치: `feature/dev-extras-ruff-consolidation`
> 분류: 청소 / 도구 일관성

---

## 1. 사전 점검

- [ ] `git status` → `main`, clean
- [ ] `git log --oneline -3` 최상단이 PR #20 머지 (`acd3813`)
- [ ] `uv run pytest 2>&1 | tail -1` → `60 passed`
- [ ] `gh pr list --state open` → 비어 있음
- [ ] ruff 최신 stable 버전 확인 (`uv pip index versions ruff` 또는 PyPI 직접 조회) — PRD §9 의 `>=0.6.0` 기준 충족 여부

---

## 2. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout -b feature/dev-extras-ruff-consolidation
```

### Step 2 — `pyproject.toml` 수정 (단일 편집)

변경 매트릭스 (PRD §5.1 그대로):

| 위치 | Before | After |
| --- | --- | --- |
| `requires-python` | `">=3.9"` | `">=3.12"` |
| `dev` extras | `black, isort, mypy, ruff` 4개 | `mypy, ruff` 2개 |
| `ruff` 버전 | `>=0.0.261` | `>=0.6.0` |
| `[tool.black]` 섹션 | 존재 | 제거 |
| `[tool.isort]` 섹션 | 존재 | 제거 |
| `[tool.mypy] python_version` | `"3.9"` | `"3.12"` |
| `[tool.ruff] target-version` | `"py39"` | `"py312"` |
| `[tool.ruff] select / ignore` | 본체 | `[tool.ruff.lint]` 하위로 이동 |

편집 후 `uv run python -c "import tomllib; tomllib.loads(open('pyproject.toml').read())"` 로 TOML 파싱 검증.

### Step 3 — `uv sync --all-extras` 로 lockfile 갱신

```bash
/usr/local/bin/mise exec -- uv sync --all-extras
git diff --stat uv.lock
```

검증:
- `black`, `isort` 항목이 `uv.lock` 에서 제거됐는지 확인 (`grep -E "^name = \"(black|isort)\"" uv.lock` 결과 없음)
- ruff 버전이 0.6+ 인지 확인 (`grep -A1 'name = "ruff"' uv.lock`)
- 의도치 않은 transitive 변경이 광범위하면 별도 분석 (예: 50줄 이상이면 sanity check)

### Step 4 — `ruff check .` 실행 → 위반 정리

```bash
/usr/local/bin/mise exec -- uv run ruff check .
```

**실제 결과 (실행 시점)**: 113 errors (구버전 ruff 가 룰을 실질적으로 검사하지 않아 빚 누적). 사용자 결정으로 자동 + 수동 수정 본 PR 에 포함.

처리 순서:
1. `ruff format .` 적용 (35 파일 reformat) → 일부 E501 자동 해소
2. `ruff check --fix .` 적용 (41 자동 수정, 주로 import 정렬)
3. 잔여 위반 매트릭스별 처리 (PRD §5.4):
   - `B008` (26건) → `[tool.ruff.lint] ignore = ["B008"]`
   - `B904` (10건) → `raise ... from e` / `from None` 수동 추가
   - `F841` (2건) → 미사용 변수 제거
   - `E501` (8건) → docstring 줄바꿈 + 매트릭스 축약 + 로그 메시지 분리
4. 재검사 — `ruff check .` 종료 코드 0

### Step 5 — `ruff format --check .` 최종 확인

```bash
/usr/local/bin/mise exec -- uv run ruff format --check .
```

기대: 종료 코드 0 (Step 4 의 수동 수정으로 라인이 길어진 케이스가 있으면 `ruff format .` 재적용).

### Step 6 — 전체 회귀 (`uv run pytest`)

```bash
/usr/local/bin/mise exec -- uv run pytest 2>&1 | tail -5
```

기대:
- `60 passed`
- deprecation warning 0건

실패 시 진단:
- 도구 단일화는 런타임 영향 없음 → 실패는 lockfile 의 의도치 않은 transitive 변경 (sqlalchemy/pydantic/fastapi 등) 이 원인일 가능성
- `git diff uv.lock` 으로 변경된 의존성 식별 → 필요 시 pinning 강화

### Step 7 — 커밋 (실제 분리)

커밋 1 (도구 단일화 + docs):
- 대상: `pyproject.toml`, `uv.lock`, `docs/[PRD]*.md`, `docs/[PLAN]*.md`
- 메시지 골자: `chore(deps): black/isort 제거하고 ruff 로 통합` — dev extras 정리, ruff 0.0.261 → 0.11.x, `[tool.ruff.lint]` 신구조, B008 ignore, target py312 통일

커밋 2 (코드 일괄 정리):
- 대상: `app/`, `tests/`, `alembic/` 의 모든 변경 (35 파일 ruff format + 41 ruff check --fix + 수동 수정 B904/F841/E501)
- 메시지 골자: `style: ruff format/check --fix 일괄 적용 + 잔여 위반 수동 정리 (B904/F841/E501)` — 외부 동작 불변, pytest 60/60 회귀 가드

### Step 8 — 푸시 + PR 생성

```bash
git push -u origin feature/dev-extras-ruff-consolidation
```

PR title 예:
```
chore(deps): dev extras 청소 — black/isort 제거하고 ruff 로 단일화
```

PR description 구조:
- 배경/목적 (PRD §1-2 요약)
- 변경 매트릭스 (PRD §5.1)
- 회귀 가드 결과 (pytest 카운트 / ruff 명령 종료 코드)
- 비목적 / 후속 (PRD §3, §7)
- PRD/Plan 링크

---

## 3. 산출물 체크리스트

- [x] `pyproject.toml` 변경 매트릭스 (PRD §5.1) 8건 적용 + B008 ignore 추가
- [x] `uv.lock` 갱신 (black/isort/pathspec/platformdirs 4개 제거 반영)
- [x] `ruff format .` 35 파일 적용
- [x] `ruff check --fix .` 41건 자동 수정
- [x] 잔여 위반 (B904 10건, F841 2건, E501 8건) 수동 정리
- [x] `uv run ruff check .` 종료 코드 0
- [x] `uv run ruff format --check .` 종료 코드 0
- [x] `uv run pytest` → 60 passed, warning 0건
- [ ] 커밋 1~2 (한글 메시지 + Co-Authored-By 푸터)
- [ ] PR description 에 변경 매트릭스 + 검증 결과

---

## 4. 테스트 케이스

본 PR 은 런타임 동작 변경 없음 → 신규 테스트 **0건**. 기존 60개 회귀 테스트로 충분.

추가 자동 검증:
- `ruff check .` 종료 코드 0 (린트 위반 없음)
- `ruff format --check .` 종료 코드 0 (포맷 일관성)
- `uv sync --all-extras` 성공 (lockfile 일관성)

---

## 5. 회귀 방지

| 검증 | 명령 | 기대 |
| --- | --- | --- |
| 전체 회귀 | `uv run pytest` | 60 passed, 0 warning |
| 린트 | `uv run ruff check .` | 종료 코드 0 |
| 포맷 | `uv run ruff format --check .` | 종료 코드 0 |
| 의존성 일관성 | `uv sync --all-extras` | 성공 |

---

## 6. 롤백

- 단일 PR `revert`. `pyproject.toml` + `uv.lock` 두 파일만 영향 → 깔끔.
- 만약 ruff format 결과 커밋이 분리되어 있으면, 그 커밋만 cherry-pick revert 도 가능.

---

## 7. 후속 (이번 PR 범위 밖, PRD §7 그대로)

- pre-commit hook 도입 (`ruff check`, `ruff format --check`)
- GitHub Actions CI 도입 — `uv sync` + ruff + pytest + (PR #14 §7 후속) `alembic upgrade head`
- ruff 룰셋 확장 (`UP`, `SIM`, `RUF` 등)
- mypy 도 ruff type-checker 로 교체 가능성 평가

---

## 8. 참고

- PRD: `docs/[PRD]dev_extras_청소_ruff_통합.md`
- 이전 청소 PR: #9 (미사용 테스트 의존성 정리)
- 관련 환경: `.mise.toml` (Python 3.12.12 고정), `uv.lock`
- ruff docs: https://docs.astral.sh/ruff/configuration/
