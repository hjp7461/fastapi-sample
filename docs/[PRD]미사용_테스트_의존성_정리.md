# 미사용 테스트 의존성 정리 PRD

| 항목       | 내용                                                                          |
| ---------- | ----------------------------------------------------------------------------- |
| 작성일     | 2026-05-22                                                                    |
| 작성자     | conner                                                                        |
| 상태       | 제안 (Draft)                                                                  |
| 도메인     | 빌드 / 의존성                                                                 |
| 대상 범위  | `pyproject.toml` 의 `[project.optional-dependencies].test`                    |
| 관련 발견  | 테스트 아키텍처 PRD §7-#4 의 잔여 이슈                                         |

---

## 1. 배경

`pyproject.toml` 의 `test` 옵셔널 의존성에는 본 프로젝트가 실제로 사용하지 않는 비동기 테스트 백엔드 4 개가 포함되어 있다.

```toml
# pyproject.toml:71-81 (현재)
test = [
    "pytest>=8.3.5",
    "pytest-asyncio>=0.26.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.24.0",
    "pytest-html>=4.1.1",
    "pytest-tornasync>=0.6.0.post2",  # ← 미사용
    "pytest-trio>=0.8.0",              # ← 미사용
    "pytest-twisted>=1.14.3",          # ← 미사용
    "twisted>=24.11.0",                # ← 미사용
]
```

### 1.1 사용 현황

```
$ grep -rn "tornasync\|pytest_trio\|pytest_twisted\|twisted\|trio" app/ tests/ --include="*.py"
(no output)
```

**코드 어디서도 import / 사용되지 않음.**

### 1.2 lockfile 에 자동으로 끌려온 transitive 패키지

- `tornado` (pytest-tornasync 의존성)
- `trio` (pytest-trio 의존성)

→ 4 개 직접 + 2 개 transitive 가 사실상 dead weight.

### 1.3 추정 경위

본 프로젝트는 `pytest-asyncio` 의 `asyncio_mode = auto` 로 동작한다. 과거 작업자가 비동기 백엔드를 평가하면서 여러 옵션을 의존성에 추가했지만 최종적으로 asyncio 만 채택했고, 미사용 의존성이 정리되지 않은 채 남은 것으로 추정된다.

---

## 2. 목적

- 미사용 테스트 의존성 4 개 + transitive 2 개 제거.
- `uv sync` 시 설치 시간 단축 및 lockfile 군더더기 제거.
- 테스트 백엔드를 `pytest-asyncio` 단일로 명확히 함 (의도 표명).

### 비목적

- 다른 의존성 (개발 dev extras, runtime dependencies) 정리 — 본 PR 은 test extras 만 한정.
- pytest 자체나 pytest-asyncio 버전 업그레이드.
- 신규 테스트 백엔드 도입 평가.
- 의존성 버전 핀 (`>=` → `==`) 정책 변경.

---

## 3. 성공 기준

| 지표                                                          | 목표값       |
| ------------------------------------------------------------- | ------------ |
| `pyproject.toml` 의 test extras 에서 미사용 패키지 4 개 제거  | 4 개 제거     |
| `uv.lock` 에서 해당 패키지 (+ transitive) 제거                | 6 개 제거     |
| 기존 회귀 테스트                                              | 34/34 PASS 유지 |
| 새 환경에서 `uv sync --all-extras` 정상 완료                  | 정상 완료    |

---

## 4. 설계

### 4.1 `pyproject.toml` 변경

```toml
# 변경 전
test = [
    "pytest>=8.3.5",
    "pytest-asyncio>=0.26.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.24.0",
    "pytest-html>=4.1.1",
    "pytest-tornasync>=0.6.0.post2",
    "pytest-trio>=0.8.0",
    "pytest-twisted>=1.14.3",
    "twisted>=24.11.0",
]

# 변경 후
test = [
    "pytest>=8.3.5",
    "pytest-asyncio>=0.26.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.24.0",
    "pytest-html>=4.1.1",
]
```

### 4.2 `uv sync` 로 lockfile 동기화

```bash
uv sync --all-extras
```

자동으로:
- pytest-tornasync, pytest-trio, pytest-twisted, twisted 제거
- transitive: tornado, trio 제거 (다른 직접 의존성이 끌어오지 않는다면)

### 4.3 mypy override 영향

`pyproject.toml:104` 의 mypy override 리스트를 확인 → 본 패키지들은 포함되어 있지 않음 (확인됨). 추가 변경 불요.

---

## 5. 영향 받는 파일

| 파일                  | 변경 종류                                | 비고                          |
| --------------------- | ---------------------------------------- | ----------------------------- |
| `pyproject.toml`      | test extras 에서 4 줄 제거               | 단순 라인 삭제                |
| `uv.lock`             | passlib 제거 + transitive 자동 동기화    | `uv sync --all-extras` 자동   |

---

## 6. 테스트 영향

본 변경은 **의존성 제거만 수행** 하고 코드 변경 없음. 신규 테스트 불요. 기존 34 케이스가 동일하게 PASS 해야 한다.

| 검증                                  | 변경 전 | 변경 후 |
| ------------------------------------- | ------- | ------- |
| `uv run pytest` 통과                  | 34/34   | 34/34   |
| `uv sync --all-extras` 정상 완료      | ✅      | ✅      |

---

## 7. 리스크 및 미해결 이슈

| #   | 항목                                                                              | 대응                                                                |
| --- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| 1   | transitive 인 `tornado` / `trio` 가 다른 직접 의존성에서 끌려오는 경우            | `uv.lock` 의 dependency tree 확인 후 의도된 잔존이면 그대로 둠       |
| 2   | 향후 비동기 백엔드 평가 시 다시 추가 필요                                          | 그때 필요한 패키지만 명시적으로 재추가. dead weight 보다 깔끔        |
| 3   | CI 캐시에 잔존하는 deleted 패키지                                                  | 캐시 키가 `uv.lock` 해시 기반이면 자동 무효화. 별도 대응 불요       |
| 4   | 다른 환경 (다른 개발자의 venv) 와의 격차                                          | 다른 개발자가 `uv sync` 재실행 시 자동 정리. README 에 가이드 명시 가능 |

### 결정 사항 (확정)

- [x] 제거 대상: `pytest-tornasync`, `pytest-trio`, `pytest-twisted`, `twisted` (4 개)
- [x] transitive (`tornado`, `trio`) 는 `uv sync` 가 자동 처리
- [x] mypy override 변경 불요 (포함 안 되어 있음)
- [x] 신규 테스트 불요 (기존 회귀로 검증)

---

## 8. 참고

- 코드 위치: `pyproject.toml:71-81`
- 사용 처 검색 명령: `grep -rn "tornasync\|trio\|twisted" app/ tests/`
- pytest 비동기 백엔드 비교: https://pytest-asyncio.readthedocs.io/
- 선례: PR #5 (passlib 제거), PR #6 / #8 (잔여 청소)
