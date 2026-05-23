# [PLAN] loguru sink / 포맷 설정 — 운영 로깅 표준화

> PRD: `docs/[PRD]loguru_sink_포맷_설정.md`
> 브랜치: `feature/loguru-sink-format-config`
> 분류: 운영 인프라

---

## 1. 사전 점검

- [ ] `git status` → `main`, clean
- [ ] `git log --oneline -3` 최상단이 PR #22 머지 (`079188f`)
- [ ] `uv run pytest 2>&1 | tail -1` → `61 passed`
- [ ] `gh pr list --state open` → 비어 있음
- [ ] 변경 대상 파일:
  - `app/core/config.py` (Settings + 5 환경 변수 + field validator)
  - `app/core/logging.py` (신규)
  - `app/main.py` (setup_logging() 호출 추가)
  - `tests/core/test_logging.py` (신규 — 회귀 가드 +3)

---

## 2. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout -b feature/loguru-sink-format-config
```

### Step 2 — `Settings` 환경 변수 5개 추가

`app/core/config.py`:

- BCRYPT_ROUNDS / USER_ADMIN_EMAIL_MASKING 옆에 "로깅 설정" 단락 신설
- 환경 변수:
  ```python
  LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
  LOG_FORMAT: str = os.getenv("LOG_FORMAT", "text")
  LOG_FILE: Optional[str] = os.getenv("LOG_FILE") or None
  LOG_FILE_ROTATION: str = os.getenv("LOG_FILE_ROTATION", "10 MB")
  LOG_FILE_RETENTION: str = os.getenv("LOG_FILE_RETENTION", "7 days")
  ```
- field_validator:
  - `LOG_LEVEL` ∈ {DEBUG, INFO, WARNING, ERROR, CRITICAL}
  - `LOG_FORMAT` ∈ {text, json}
- `Optional` import 누락 확인 (현재 `from typing import List` 만 → `Optional` 추가)

검증: `uv run python -c "from app.core.config import settings; print(settings.LOG_LEVEL, settings.LOG_FORMAT, settings.LOG_FILE)"` → `INFO text None`

### Step 3 — `app/core/logging.py` 신설

PRD §5.2 그대로 작성:
- `InterceptHandler` 클래스 (stdlib logging → loguru)
- `_TEXT_FORMAT` 상수
- `setup_logging()` 함수
  - `logger.remove()` 호출 → default handler 제거
  - stderr sink 추가 (format/serialize/colorize 분기)
  - LOG_FILE 설정 시 file sink 추가
  - `logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)`
  - noisy logger 명시 교체 (`uvicorn`, `uvicorn.access`, `sqlalchemy.engine`)

### Step 4 — `app/main.py` 에 `setup_logging()` 호출

```python
from app.core.logging import setup_logging
setup_logging()  # FastAPI app 생성 전, 다른 import 와 같은 단락
```

배치는 `from app.api.router import api_router` 위에 (의존 순서: settings → logging → router/container).

### Step 5 — 회귀 가드 테스트 3건

`tests/core/test_logging.py` 신설:

| # | 이름 | 시나리오 | 기대 |
| --- | --- | --- | --- |
| 1 | `test_setup_logging_text_default` | default 설정, `setup_logging()` 호출 → `logger.warning("probe-msg")` | stderr 출력에 "WARNING" + "probe-msg" 포함 |
| 2 | `test_setup_logging_json_format` | `monkeypatch.setattr(settings, "LOG_FORMAT", "json")` + setup_logging() → `logger.warning("probe-msg")` | stderr 출력의 마지막 라인이 `json.loads` 로 파싱 가능, `record.message == "probe-msg"` |
| 3 | `test_intercept_handler_routes_stdlib_to_loguru` | setup_logging() → `logging.getLogger("test_intercept").warning("via-stdlib")` | stderr 출력에 "via-stdlib" 포함 (loguru sink 통과) |

테스트 fixture:
- `capsys` 로 stderr 캡처
- 각 테스트 끝에 `logger.remove()` 로 cleanup (다음 테스트 영향 차단)

### Step 6 — 회귀 (`uv run pytest`)

```bash
/usr/local/bin/mise exec -- uv run pytest 2>&1 | tail -5
```

기대: **64 passed** (61 + 3 신규), warning 0건.

**잠재 영향**: `setup_logging()` 이 main.py import 시점에 호출 → 다른 테스트에서 logger 출력이 stderr 로 캡처될 수 있음. pytest 가 capsys/capfd 로 격리하므로 영향 없을 것. 만약 발생 시 별 fixture 로 conftest 에서 setup_logging 우회 옵션 도입.

### Step 7 — ruff check / format --check

```bash
/usr/local/bin/mise exec -- uv run ruff check . 2>&1 | tail -2
/usr/local/bin/mise exec -- uv run ruff format --check . 2>&1 | tail -2
```

기대: 둘 다 종료 코드 0.

### Step 8 — 커밋 분리

커밋 1 (설정 + 모듈 신설):
- `app/core/config.py`, `app/core/logging.py`, `app/main.py`, docs
- 메시지: `feat(logging): loguru sink/포맷 환경 변수 설정 + stdlib logging InterceptHandler 도입`

커밋 2 (회귀 가드):
- `tests/core/test_logging.py`
- 메시지: `test(logging): setup_logging 회귀 가드 +3 (text default / json / InterceptHandler)`

분리 이유: 모듈 신설 자체와 회귀 가드의 책임이 다름 — review 표면 분산.

### Step 9 — 푸시 + PR

```bash
git push -u origin feature/loguru-sink-format-config
```

PR title 예:
```
feat(logging): loguru sink/포맷 환경 변수 설정 + stdlib logging InterceptHandler 도입
```

PR description: 배경/목적 (PRD §1-2), 변경 매트릭스 (PRD §5), 회귀 가드 결과, 비목적/후속.

---

## 3. 산출물 체크리스트

- [ ] `app/core/config.py`: 환경 변수 5개 + field_validator 2개 + Optional import
- [ ] `app/core/logging.py`: 신규 (InterceptHandler + setup_logging)
- [ ] `app/main.py`: setup_logging() 호출
- [ ] `tests/core/test_logging.py`: 회귀 가드 +3
- [ ] `uv run pytest` → 64 passed (61 → 64)
- [ ] `uv run ruff check .` 종료 코드 0
- [ ] `uv run ruff format --check .` 종료 코드 0
- [ ] 커밋 1~2 (한글 메시지 + Co-Authored-By 푸터)
- [ ] PR description 에 변경 매트릭스 + 검증 결과

---

## 4. 테스트 케이스 (신규 3건, PRD §5.4 그대로)

| # | 이름 | 핵심 검증 |
| --- | --- | --- |
| 1 | `test_setup_logging_text_default` | default text 출력에 WARNING/메시지 포함 |
| 2 | `test_setup_logging_json_format` | JSON parseable 출력 |
| 3 | `test_intercept_handler_routes_stdlib_to_loguru` | stdlib logging → loguru sink 통과 |

기존 61개 회귀: 영향 없어야 함 (default 가 기존 동작 호환).

---

## 5. 회귀 방지

| 검증 | 명령 | 기대 |
| --- | --- | --- |
| 전체 회귀 | `uv run pytest` | 64 passed, 0 warning |
| 린트 | `uv run ruff check .` | 종료 코드 0 |
| 포맷 | `uv run ruff format --check .` | 종료 코드 0 |
| settings default | `uv run python -c "from app.core.config import settings; print(settings.LOG_LEVEL, settings.LOG_FORMAT, settings.LOG_FILE)"` | `INFO text None` |
| 환경 변수 override | `LOG_FORMAT=json uv run python -c "..."` → JSON 적용 검증 |  |
| InterceptHandler | 회귀 #3 | stdlib → loguru sink 통과 |

---

## 6. 롤백

- 두 커밋 `revert`. 4 파일 (config / logging / main / test) + docs.
- 환경 변수 미사용 환경에서는 default 동작이 기존과 호환이라 롤백 안 해도 즉시 영향 없음.
- 만약 다른 PR 이 `app/core/logging.py` 를 참조하기 시작했다면 그 PR 도 함께 revert 검토.

---

## 7. 후속 (PRD §7)

- Sentry / 외부 sink 통합
- request_id contextvars 주입 (FastAPI middleware)
- 다운그레이드 감지 로그 dedup (handoff §6 별도 항목)
- audit log (별도 PRD)
- 로그 대시보드/알람 룰 셋업
- RUNBOOK §환경 변수 단락 보강 (LOG_* 5개 추가)

---

## 8. 참고

- PRD: `docs/[PRD]loguru_sink_포맷_설정.md`
- PR #13 PRD/PLAN (loguru 첫 도입 컨텍스트)
- `app/main.py`, `app/user/service.py` (loguru 호출 위치)
- loguru docs: https://loguru.readthedocs.io/
