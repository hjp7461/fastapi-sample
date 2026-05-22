# 미사용 테스트 의존성 정리 구현 Plan

| 항목         | 내용                                                                       |
| ------------ | -------------------------------------------------------------------------- |
| 작성일       | 2026-05-22                                                                 |
| 연관 PRD     | [`[PRD]미사용_테스트_의존성_정리.md`](./[PRD]미사용_테스트_의존성_정리.md) |
| 상태         | 제안 (Draft)                                                               |
| 추정 작업량  | 약 15 분                                                                   |
| 제거 대상    | `pytest-tornasync`, `pytest-trio`, `pytest-twisted`, `twisted`             |

> 본 작업은 의존성 제거만 수행한다. 코드 변경 0, 신규 테스트 0.

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 기준 최신 상태에서 `feature/cleanup-test-deps` 브랜치 생성
- [ ] `uv run pytest` 현재 34/34 PASS 확인
- [ ] 제거 대상 패키지가 실제로 코드에서 사용되지 않는지 재확인

```bash
grep -rn "tornasync\|pytest_trio\|pytest_twisted\|twisted\|trio" app/ tests/ --include="*.py"
# → 출력 없음 (확인됨)
```

- [ ] 변경 전 `uv.lock` 의 관련 패키지 수 기준선 측정

```bash
grep -c '^name = "pytest-tornasync"' uv.lock
grep -c '^name = "pytest-trio"' uv.lock
grep -c '^name = "pytest-twisted"' uv.lock
grep -c '^name = "twisted"' uv.lock
grep -c '^name = "tornado"' uv.lock
grep -c '^name = "trio"' uv.lock
# 각각 1 (제거 후 0 으로 감소해야 함)
```

---

## 1. 작업 분해

### Step 1. `pyproject.toml` 에서 4 줄 제거

**대상**: `pyproject.toml:71-81`

```toml
# 변경 전 (test 옵셔널 의존성)
test = [
    "pytest>=8.3.5",
    "pytest-asyncio>=0.26.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.24.0",
    "pytest-html>=4.1.1",
    "pytest-tornasync>=0.6.0.post2",  # ← 제거
    "pytest-trio>=0.8.0",              # ← 제거
    "pytest-twisted>=1.14.3",          # ← 제거
    "twisted>=24.11.0",                # ← 제거
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

### Step 2. `uv sync` 로 lockfile 동기화

```bash
uv sync --all-extras
```

uv 가 자동 수행:
- 직접 의존성 4 개 제거
- transitive: `tornado`, `trio` 도 다른 직접 의존성이 끌어오지 않으면 제거

**검증**

```bash
grep -c '^name = "pytest-tornasync"' uv.lock  # → 0
grep -c '^name = "pytest-trio"' uv.lock        # → 0
grep -c '^name = "pytest-twisted"' uv.lock     # → 0
grep -c '^name = "twisted"' uv.lock            # → 0
```

### Step 3. 전체 회귀 검증

```bash
uv run pytest -v
```

34/34 PASS 확인.

```bash
# 환경이 새로 동기화되었는지 확인 — 설치 패키지 수 비교
uv pip list | wc -l
```

---

## 2. 산출물 체크리스트

- [ ] `pyproject.toml` — test extras 에서 4 줄 제거
- [ ] `uv.lock` — uv sync 로 갱신, 6 개 패키지 (직접 4 + transitive 2) 제거 확인
- [ ] `uv run pytest -v` **34/34 PASS**
- [ ] `grep -c '^name = "pytest-tornasync"' uv.lock` → 0
- [ ] `grep -c '^name = "twisted"' uv.lock` → 0

---

## 3. 테스트 케이스 (완료 판정 기준)

**신규 테스트 불요**. 다음 기존 테스트가 동일하게 PASS 해야 한다.

| 그룹                       | 케이스 수 | 검증 포인트                              |
| -------------------------- | --------- | ---------------------------------------- |
| 사용자 라우터              | 8         | pytest-asyncio 기반 비동기 흐름          |
| 상품 라우터                | 12        | pytest-asyncio 기반 비동기 흐름          |
| 보안 (test_security)       | 5         | 동기 + pytest-asyncio 혼재                |
| datetime handling          | 2         | 동기 + pytest-asyncio 혼재                |
| 권한 메서드 (test_role)    | 3         | 동기 (의존성 무관)                       |
| 기타 (`__init__` 등)       | 4         |                                          |
| **합계**                   | **34**    | 모든 케이스 PASS                          |

본 변경이 회귀를 일으킨다면 pytest-asyncio 가 다른 백엔드 (tornasync/trio/twisted) 와 충돌이 있었던 경우인데, 코드 어디서도 그 백엔드들이 사용되지 않으므로 영향이 있을 수 없다.

---

## 4. 회귀 방지 체크리스트

PR 머지 전 모두 확인.

- [ ] `uv run pytest` **34/34 PASS**
- [ ] `uv.lock` 에서 4 개 직접 의존성 모두 제거 확인
- [ ] `uv.lock` 에서 transitive `tornado`, `trio` 도 제거 확인 (다른 의존성이 끌어오는 경우 잔존 가능 — 확인만)
- [ ] `pyproject.toml` 의 `[tool.mypy.overrides]` 에는 영향 없음 (포함 안 되어 있음)
- [ ] 새 환경에서 `uv sync --all-extras` 후 `pytest` 정상 동작
- [ ] CI 가 있다면 캐시 무효화 자동 확인 (`uv.lock` 해시 변화)

---

## 5. 롤백 전략

- 본 작업은 `pyproject.toml` + `uv.lock` 2 파일 변경.
- 별도 브랜치 (`feature/cleanup-test-deps`) 에서 작업. 문제 시 `git checkout main` 으로 원복.
- `git checkout main -- pyproject.toml uv.lock` 후 `uv sync` 로 원상 복구 가능.

---

## 6. 후속 작업 (별도 이슈 권장)

| #   | 항목                                                                | 권장 처리                                  |
| --- | ------------------------------------------------------------------- | ------------------------------------------ |
| 1   | dev extras 의 미사용 의존성 점검 (black/isort/mypy/ruff)            | ruff 가 black+isort 대체 가능 — 별도 PR     |
| 2   | runtime dependencies 의 사용 현황 점검 (예: `python-jose` 사용 여부) | 별도 청소 PR                               |
| 3   | uv tool 자체의 transitive lock 정책 검토                            | uv 문서 / 운영 가이드                      |

---

## 7. 참고

- 관련 PRD: [`[PRD]미사용_테스트_의존성_정리.md`](./[PRD]미사용_테스트_의존성_정리.md)
- 핵심 파일: `pyproject.toml:71-81`
- 사용처 검색 명령: `grep -rn "tornasync\|trio\|twisted" app/ tests/`
- 선례: PR #5 (passlib 제거 — 동일한 단일 의존성 제거 패턴)
