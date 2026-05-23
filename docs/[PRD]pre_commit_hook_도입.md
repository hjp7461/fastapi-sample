# [PRD] pre-commit hook 도입 — 로컬 가드

> 출처: PR #21 §7 후속 "pre-commit hook (`ruff check`, `ruff format --check`)"
> 분류: 개발 표면
> 작업량: 소

---

## 1. 배경

PR #21 에서 black/isort 를 제거하고 ruff 로 단일화하면서 누적 lint 빚을 청산했다. 그러나:

- CI 가 아직 없음 (handoff §6 ⬜ 항목, 별도 작업)
- 개발자가 `uv run ruff check .` / `uv run ruff format --check .` 를 수동으로 호출해야 함
- 커밋 시점에 자동 가드가 없으므로 lint clean baseline 이 한 번의 부주의로 다시 빚 누적 가능

CI 도입 (서버 가드) 전에 **로컬 가드 (pre-commit hook)** 를 먼저 두면:
- 개발 표면에서 즉시 차단 — CI 푸시 후 빨간 화면 보기 전에 로컬에서 자동 수정
- CI 도입 시점에 동일 도구를 재사용 가능 (pre-commit + CI 가 같은 hook 정의 참조)
- 개발자가 잊어도 `git commit` 자체가 hook 실행

본 PR 은 가벼운 로컬 가드만 도입. CI 통합은 별도 후속.

---

## 2. 목적

- `.pre-commit-config.yaml` 신설 — `ruff`, `ruff-format` + 기본 hooks
- dev extras 에 `pre-commit>=4.0` 추가 (`uv sync --all-extras` 만으로 설치)
- `uv run pre-commit install` 한 번이면 로컬 git hook 설정 완료
- README.md 의 §설치 및 실행 단락에 안내 추가

---

## 3. 비목적

- **CI 도입 안 함** — 별도 후속 (handoff §6 ⬜). 본 PR 은 로컬 가드만.
- **mypy hook 도입 안 함** — mypy 가 dev extras 에 있지만 본 프로젝트의 mypy 호출 흔적이 없고, 활성화 시 위반 noise 가능. 별도 작업으로 분리.
- **자동 `pre-commit install`** 안 함 — `git clone` 후 자동 실행이 아니라 명시적 수동 실행. README 안내만.
- **추가 hook 확장 (예: secret detection, conventional commits, mdformat)** 안 함 — 별도 후속.
- **기존 코드 수정 안 함** — 본 PR 로 lint 위반이 새로 노출되지 않아야 함 (PR #21 으로 이미 clean).

---

## 4. 성공 기준

1. `pyproject.toml` `dev` extras 에 `pre-commit>=4.0` 추가
2. `.pre-commit-config.yaml` 신설:
   - `astral-sh/ruff-pre-commit` (`ruff`, `ruff-format`) — 본 프로젝트와 동일한 룰 (`pyproject.toml` 참조)
   - `pre-commit/pre-commit-hooks` (`trailing-whitespace`, `end-of-file-fixer`, `check-toml`, `check-yaml`, `check-merge-conflict`)
3. `uv run pre-commit run --all-files` 실행 시 모든 hook 종료 코드 0 (기존 코드가 이미 clean)
4. README.md §설치 및 실행 단락에 `pre-commit install` 안내
5. 기존 64 테스트 PASS 유지 + `ruff check` / `ruff format --check` 종료 코드 0 유지

---

## 5. 설계

### 5.1 `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.11.4   # pyproject.toml 의 ruff 버전과 일치
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-toml
      - id: check-yaml
      - id: check-merge-conflict
```

- `ruff --fix` 는 자동 수정 → 차이 발생 시 hook 실패 + staged 파일 변경. 개발자가 재커밋.
- `ruff-format` 도 동일 패턴 (변경 시 재커밋).
- `rev: v0.11.4` 는 `pyproject.toml` 의 ruff 와 일치 (불일치 시 룰 차이 발생). 후속 ruff 업그레이드 시 두 곳 같이 갱신.

### 5.2 `pyproject.toml` 변경

```toml
[project.optional-dependencies]
dev = [
    "mypy>=1.2.0",
    "pre-commit>=4.0",
    "ruff>=0.6.0",
]
```

### 5.3 README.md §설치 및 실행 단락 보강

`### 의존성 설치` 단락 끝 또는 별도 `### Pre-commit hook (선택)` 단락 추가:

```markdown
### Pre-commit hook (선택, 권장)

ruff check / ruff format 을 커밋 시점에 자동 실행:

\`\`\`bash
uv run pre-commit install
\`\`\`

이후 `git commit` 시 hook 이 자동 실행되어 lint/포맷 위반이 있으면 차단합니다.
전체 파일에 한 번 실행하려면:

\`\`\`bash
uv run pre-commit run --all-files
\`\`\`
```

### 5.4 검증 매트릭스

| 검증 | 명령 | 기대 |
| --- | --- | --- |
| 도구 설치 | `uv sync --all-extras` 후 `uv run pre-commit --version` | 4.x 출력 |
| hook 정의 valid | `uv run pre-commit validate-config` | OK |
| 전체 파일 hook 실행 | `uv run pre-commit run --all-files` | 모든 hook Passed |
| 회귀 | `uv run pytest` | 64 passed |
| 기존 ruff 가드 | `uv run ruff check .` / `ruff format --check .` | 종료 코드 0 |

---

## 6. 영향

- **개발 환경**: `uv sync --all-extras` 시 pre-commit 추가 설치 (가벼움, ~수 MB). `pre-commit install` 명시 실행 시 git hook 활성화.
- **운영 환경**: 무영향 (런타임 의존성 무변동).
- **CI**: 본 PR 범위 밖. 후속 CI 도입 시 동일 hook 재사용 가능.
- **다른 개발자**: pre-commit install 안 하면 자동 가드 없음 — 자율 선택. README 권장.

---

## 7. 후속 작업 (이번 PR 범위 밖)

- CI 도입 (GitHub Actions) — `uv sync` + `pre-commit run --all-files` + pytest + alembic upgrade head
- mypy hook 활성화 (mypy 위반 청산 후)
- 추가 hook (secret detection, conventional commits, mdformat 등)
- `pre-commit autoupdate` 정기 실행 가이드 (rev 핀 갱신)
- RUNBOOK §환경 변수 단락 보강 (PR #22/#23 후속과 묶을 수도)

---

## 8. 리스크

| 리스크 | 가능성 | 대응 |
| --- | --- | --- |
| `.pre-commit-config.yaml` 의 ruff rev 와 `pyproject.toml` 의 ruff 버전 불일치 → 룰 차이 | 중 | rev 를 `pyproject.toml` 의 ruff 와 일치 (v0.11.4). 후속 업그레이드 시 두 곳 같이 갱신. PR description 에 명시. |
| 개발자가 `pre-commit install` 안 함 → 가드 무효 | 중 | README 권장 + 후속 CI 가 서버 가드로 작동. 강제는 안 함. |
| hook 자체가 첫 실행에서 광범위 수정 → 본 PR 의 검증 단계에서 차이 발생 | 낮음 | PR #21 으로 이미 lint clean. `pre-commit run --all-files` 결과로 사전 확인. 만약 차이 있으면 본 PR 에서 별도 커밋으로 분리. |
| `trailing-whitespace` / `end-of-file-fixer` 가 docs 의 의도적 trailing newline 등을 변경 | 낮음 | docs 가 markdown 이라 trailing-whitespace 영향 없음. EOF newline 은 표준. 만약 차이 있으면 같은 PR 에서 적용. |
| pre-commit 4.x 가 Python 3.12 호환성 이슈 | 낮음 | 4.0 부터 Python 3.9+ 공식 지원. 본 프로젝트는 3.12. |

---

## 9. 결정 사항 (확정)

- [x] **dev extras 에 pre-commit 추가** — `uv sync --all-extras` 만으로 설치, 별도 install 방식 안 씀.
- [x] **ruff rev 는 v0.11.4 핀** (pyproject.toml 과 일치). 후속 갱신 시 두 곳 같이.
- [x] **`--fix` 자동 수정 활성** — 차이 발생 시 hook 실패 + 자동 수정 후 재커밋 패턴.
- [x] **기본 hooks 5종 포함** — trailing-whitespace / end-of-file-fixer / check-toml / check-yaml / check-merge-conflict.
- [x] **자동 install 안 함** — `pre-commit install` 은 수동, README 안내만.
- [x] **README §설치 및 실행 안내 추가** — 본 PR 범위 안. RUNBOOK 환경 변수 단락은 별도 후속.
- [x] **CI / mypy / 추가 hook 비범위** — 별도 후속.

---

## 10. 참고

- PR #21 (`docs/[PRD][PLAN]dev_extras_청소_ruff_통합.md`) — lint clean baseline 출발선
- `.pre-commit-config.yaml` 작성 가이드: https://pre-commit.com/
- `astral-sh/ruff-pre-commit`: https://github.com/astral-sh/ruff-pre-commit
- `pre-commit/pre-commit-hooks`: https://github.com/pre-commit/pre-commit-hooks
- `pyproject.toml` `dev` extras (PR #21 후 형태)
- README.md §설치 및 실행 (line 84+)
