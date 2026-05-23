# [PRD] dev extras 청소 — black/isort → ruff 단일화

> 출처: PR #9 §6-#1 후속 (미사용 테스트 의존성 정리 시 함께 식별)
> 분류: 청소 / 도구 일관성
> 작업량: 소

---

## 1. 배경

PR #9 에서 미사용 테스트 의존성 14개를 정리하면서, dev extras 의 `black` / `isort` / `mypy` / `ruff` 네 도구가 공존하고 있다는 관성을 §6-#1 후속으로 남겨두었다. 현재 상태:

- `pyproject.toml` `[project.optional-dependencies].dev`:
  - `black>=23.3.0` — 포매터
  - `isort>=5.12.0` — import 정렬
  - `mypy>=1.2.0` — 정적 타입 체크
  - `ruff>=0.0.261` — 린터 + (최신 버전에서는) 포매터
- 설정 섹션 셋 다 존재: `[tool.black]`, `[tool.isort]`, `[tool.ruff]`
- `[tool.ruff]` 의 `select = ["E", "F", "B", "I"]` 에 이미 isort(`I`) 룰이 포함되어 있어 isort 와 역할이 정확히 겹친다.
- 최신 ruff (0.2.0+) 는 `ruff format` 으로 black 호환 포매터를 제공한다 → black 도 역할 중복.
- 추가로 `requires-python = ">=3.9"` / 각 도구의 `target-version = "py39"` 인데 실제 런타임은 `.mise.toml` 의 **Python 3.12.12**. PR #5 (passlib 제거), PR #8 (`datetime.now(UTC)`) 등에서 이미 Python 3.10+ 문법/API 사용 중이라 py39 표기가 거짓이다.

도구 표면이 셋(black, isort, ruff) 으로 분산된 채 셋 다 거의 같은 일을 하면 — 새 컨트리뷰터가 어느 도구를 어떻게 호출해야 할지 결정해야 하고, 설정 충돌 가능성이 잠재한다. 이미 ruff 가 둘을 대체할 수 있으므로 단일화한다.

---

## 2. 목적

- dev extras 에서 `black`, `isort` 제거하고 `ruff` 단일 도구로 포매팅 + 린트 + import 정렬 통합
- ruff 를 최신 버전(0.6+) 으로 업그레이드하고 신 구조(`[tool.ruff.lint]`) 로 마이그레이션
- target Python 버전 표기를 실제 런타임(3.12) 과 일치시켜 거짓 표기 제거
- `ruff format` / `ruff check` 두 명령으로 표면 단순화

---

## 3. 비목적

- **mypy 제거하지 않음**: mypy 는 타입 체크 도구로 ruff 와 역할이 다르다. 본 PR 범위 밖. (다만 mypy 의 `python_version = "3.9"` 도 함께 갱신 — 거짓 표기 제거 동기.)
- **pre-commit hook / CI workflow 도입하지 않음**: 본 PR 은 도구 단일화에 한정. 자동 실행 파이프라인은 별도 후속(§7).
- **ruff 룰 확장하지 않음**: 현재 활성 룰셋(`E F B I`) 유지. 룰 추가/조정은 별도 청소 작업으로 분리.
- ~~**린트 위반 일괄 수정하지 않음**~~ — 실행 중 변경됨. 구버전 ruff(`0.0.261`) 가 룰을 실질적으로 검사하지 않아 빚이 누적되어 있었고, 신버전(0.11.x) 으로 올리니 113 errors / 35 파일 reformat 이 드러났다. 사용자 결정으로 **자동 수정 (ruff format + ruff check --fix) + 잔여 수동 수정** 을 본 PR 에 포함하기로 변경. §9 결정 사항 참조.

---

## 4. 성공 기준

1. `pyproject.toml`:
   - `dev` extras 에서 `black`, `isort` 제거
   - `[tool.black]`, `[tool.isort]` 섹션 제거
   - `ruff` 버전 `>=0.6.0` 으로 상향 (실제 최신 stable 기준 — 실행 시 시점 latest 확인)
   - `[tool.ruff]` → `[tool.ruff]` (line-length, target-version) + `[tool.ruff.lint]` (select, ignore) 신구조
   - `target-version`/`requires-python`/`[tool.mypy] python_version` 을 `py312` / `>=3.12` / `3.12` 로 갱신
2. `uv sync --all-extras` 후 `uv run ruff check .` / `uv run ruff format --check .` 두 명령 모두 종료 코드 0
3. `uv run pytest` → **60/60 PASS**, deprecation warning **0건** 유지
4. `ruff format .` / `ruff check --fix .` 적용 후 차이 흡수. 잔여 위반은 본 PR 에서 수동 정리 (B904/F841/E501) + B008 룰 ignore (FastAPI `Depends()` 패턴).

---

## 5. 설계

### 5.1 `pyproject.toml` 변경 매트릭스

| 위치 | Before | After |
| --- | --- | --- |
| `requires-python` | `">=3.9"` | `">=3.12"` |
| `dev` extras | `black, isort, mypy, ruff` | `mypy, ruff` |
| `ruff` 버전 | `>=0.0.261` | `>=0.6.0` (실행 시점 stable) |
| `[tool.black]` 섹션 | 존재 | 제거 |
| `[tool.isort]` 섹션 | 존재 | 제거 |
| `[tool.mypy] python_version` | `"3.9"` | `"3.12"` |
| `[tool.ruff]` 본체 | `line-length`, `target-version`, `select`, `ignore` | `line-length`, `target-version="py312"` |
| `[tool.ruff.lint]` 신설 | — | `select = ["E","F","B","I"]`, `ignore = ["B008"]` |

### 5.2 ruff 명령 표면

| 목적 | 명령 |
| --- | --- |
| 린트 검사 | `uv run ruff check .` |
| 린트 자동 수정 | `uv run ruff check --fix .` |
| 포맷 검사 | `uv run ruff format --check .` |
| 포맷 적용 | `uv run ruff format .` |

### 5.3 회귀 가드

- 본 PR 의 회귀 가드는 **pytest 60/60 PASS + warning 0건**. (도구 단일화는 런타임 동작에 영향 없음. B904 의 `raise ... from e` 추가 / F841 미사용 변수 제거도 외부 동작 불변 → 기존 테스트 스위트로 충분.)
- 추가로 `ruff check .` / `ruff format --check .` 두 명령이 모두 종료 코드 0 인지 확인.

### 5.4 위반 처리 매트릭스 (실행 중 식별)

| 룰코드 | 건수 | 처리 |
| --- | --- | --- |
| `B008` (function-call-in-default-argument) | 26 | `[tool.ruff.lint] ignore` 추가 — FastAPI `Depends()`/`Field()` 가 시그니처 기본값에 호출이 들어가는 표준 패턴이라 룰 의도와 무관 |
| `B904` (raise-without-from-inside-except) | 10 | `raise ... from e` 또는 `from None` 명시 (의도성 표현). `app/api/dependencies.py` 1건은 `from None` (JWT 내부 trace 숨김), 나머지 9건은 `from e` (체이닝) |
| `E501` (line-too-long) | 8 | docstring 줄바꿈 + 매트릭스 칼럼 축약 + 로그 메시지 string concat 분리 |
| `F841` (unused-variable) | 2 | 미사용 로컬 변수 제거 (`tests/product/test_router.py`) |
| `ruff format` 차이 | 35 파일 | `ruff format .` 자동 적용 |
| `ruff check --fix` | 41 | 자동 수정 적용 (주로 import 정렬 `I001`) |

---

## 6. 영향

- **개발자 표면**: 포매팅/정렬 명령이 `ruff format` / `ruff check` 두 개로 일관됨 (기존 `black .` / `isort .` 호출 흔적은 docs/scripts 에 없음 — 영향 없음 확인됨).
- **CI**: 아직 GitHub Actions 가 없으므로 영향 없음. CI 도입(§7) 시 자연스럽게 `ruff check` / `ruff format --check` 만 추가하면 됨.
- **잠금 파일**: `uv.lock` 에서 `black`, `isort` 항목 제거. ruff 버전 상향 반영.
- **런타임 의존성**: 무변동 (`dev` extras 만 변경).

---

## 7. 후속 작업 (이번 PR 범위 밖)

- pre-commit hook 도입 (`ruff check`, `ruff format --check`)
- GitHub Actions CI 도입 — `uv sync` + `ruff check` + `ruff format --check` + `pytest` (PR #14 §7 의 `alembic upgrade head` 통합과 함께 묶을 수 있음)
- ruff 룰셋 확장 검토 (`UP`, `SIM`, `RUF` 등 권장 룰셋 추가 시점)
- mypy 도 ruff type-checker 로 교체 가능성 평가 (ruff 가 type-check 도입 시점)

---

## 8. 리스크

| 리스크 | 발생 가능성 | 대응 |
| --- | --- | --- |
| `ruff format` 적용 시 기존 코드와 diff 가 광범위하게 발생 | 중 | 본 PR 에서 자동 적용. 별도 커밋으로 분리해서 review 부담 분산. |
| ruff 0.6+ 가 기존 `select` 룰에 새 룰 추가하여 위반 노출 | 낮 | 룰셋이 명시적이므로 새 룰 자동 추가 없음. 만약 동일 룰코드의 의미가 바뀌었다면 위반 노출 가능 — 발생 시 본 PR 에서 분리. |
| `requires-python = ">=3.12"` 상향으로 누군가의 로컬이 3.9~3.11 인 경우 | 낮 | `.mise.toml` 이 3.12 고정이고 현재 사용자만 사용 중이므로 영향 없음. |
| `uv.lock` 갱신으로 의도치 않은 transitive 업데이트 발생 | 낮 | `uv sync --all-extras` 결과를 commit 직전 diff 검사. ruff 외 transitive 변경이 있으면 lock 만 별도 커밋. |

---

## 9. 결정 사항 (확정)

- [x] **mypy 는 dev extras 에 유지** — 타입 체크는 ruff 가 대체 못 함. python_version 표기만 3.12 로 갱신.
- [x] **target Python 3.12 로 통일** — `requires-python`, `[tool.ruff] target-version`, `[tool.mypy] python_version` 모두. PR #5 / #8 이 이미 Python 3.10+ 문법을 도입한 상태라 거짓 표기 제거가 자연스러움.
- [x] **ruff format + check --fix 자동 적용 결과 본 PR 에 포함** — 35 파일 reformat + 41건 자동 수정. 회귀 가드는 pytest 60/60. 코드 변경량이 광범위하지만 자동 수정이라 review 부담 제한적.
- [x] **잔여 위반 (B904/F841/E501) 도 본 PR 에서 수동 정리** — 도구 단일화 후 lint clean 상태로 마무리해야 후속 PR 의 ruff check 가드가 의미를 가짐.
- [x] **B008 룰만 ignore 추가** — FastAPI `Depends()` 가 표준 패턴. 룰 동작 자체가 부적절. 그 외 룰셋은 동결.
- [x] **ruff 룰셋 확장 없음** — `["E","F","B","I"]` 그대로. `UP`, `SIM`, `RUF` 등은 별도 후속.
- [x] **CI / pre-commit 도입 없음** — 본 PR 은 도구 단일화 + 잔여 빚 청산에만 집중.

---

## 10. 참고

- PR #9 §6-#1 (미사용 의존성 정리 시 식별된 후속)
- PR #5 (passlib 제거 — Python 3.12 호환성 동기)
- PR #8 (`datetime.now(UTC)` — Python 3.10+ 문법)
- `.mise.toml` (Python 3.12.12 고정)
- ruff docs: https://docs.astral.sh/ruff/configuration/ (`[tool.ruff.lint]` 구조 마이그레이션)
