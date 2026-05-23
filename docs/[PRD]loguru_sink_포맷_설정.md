# [PRD] loguru sink / 포맷 설정 — 운영 로깅 표준화

> 출처: PR #13 §3 비목적 "loguru sink/포맷 설정 변경 (별도 setup 모듈, JSON 출력 등) — 본 PR 은 기본 stderr sink 그대로"
> 분류: 운영 인프라
> 작업량: 중

---

## 1. 배경

PR #13 에서 비밀번호 재해시 정책 운영 가시화를 위해 loguru 를 첫 도입했다. `logger.warning` / `logger.exception` 호출 두 곳 (`app/user/service.py`). 그러나 sink 설정은 loguru 의 default (stderr, plain text) 그대로 두고 §3 비목적에 "별도 setup 모듈, JSON 출력 등은 후속" 으로 명시했다.

현재 한계:
- 운영 환경에서 stderr plain text 로그를 수집 파이프라인 (Datadog / CloudWatch / ELK 등) 으로 보내려면 JSON 포맷이 표준. 현재 default 는 수집 시점에 파싱 비용
- 로그 레벨이 코드 고정 (DEBUG 노이즈 / WARNING 누락 등을 환경별로 조정 못 함)
- 파일 출력 / rotation 정책 없음 — stderr 만 의존
- uvicorn / sqlalchemy / FastAPI 의 stdlib logging 호출이 loguru 와 분리된 채 두 표면 공존 — 일관성 떨어짐
- 다운그레이드 / 재해시 실패 로그가 운영 수집 파이프라인과 자동 연결 안 됨 (PR #13 §7 후속의 핵심 목표)

본 PR 은 **`app/core/logging.py::setup_logging()` 단일 setup 함수 + 환경 변수 기반 sink/포맷 분기** 를 도입한다.

---

## 2. 목적

- `app/core/logging.py::setup_logging()` 신설 — 환경 변수 기반 sink/포맷/레벨 구성을 단일 진입점에서 처리
- 환경 변수: `LOG_LEVEL`, `LOG_FORMAT` (text/json), `LOG_FILE` (선택), `LOG_FILE_ROTATION`, `LOG_FILE_RETENTION`
- stdlib `logging` 호출 (`uvicorn`, `sqlalchemy`, FastAPI) 도 loguru 로 통과시키는 `InterceptHandler` 도입 — 로깅 표면 단일화
- main.py 의 import 시점에 `setup_logging()` 호출
- default 설정은 기존 동작과 호환 (stderr / INFO / text) — 회귀 가드 영향 없음

---

## 3. 비목적

- **Sentry / 외부 sink 연동 안 함** — 외부 서비스 의존이라 별도 환경 변수 + 라이브러리 도입 필요. 별도 후속.
- **request_id contextvars 주입 안 함** — FastAPI middleware 추가가 필요해 영향 범위 큼. 별도 후속.
- **샘플링 / rate limiting 안 함** — 양 폭증 시점에 별도 후속 (handoff §6 의 "다운그레이드 감지 로그 dedup" 항목과 연계).
- **audit log (DB/외부 시스템 기록) 안 함** — 별도 PRD (handoff §6).
- **다운그레이드/재해시 호출처 변경 안 함** — 기존 `logger.warning` / `logger.exception` 호출은 그대로. 본 PR 은 sink/포맷만.
- **uvicorn access log 형식 통합 안 함** — uvicorn 의 access log 포맷팅은 별도 옵션. InterceptHandler 가 통과만 시키고, 포맷은 loguru 의 통일 포맷 그대로 적용.

---

## 4. 성공 기준

1. `app/core/logging.py::setup_logging() -> None` 신설:
   - 기본 stderr sink 한 개 + (LOG_FILE 설정 시) file sink 한 개
   - LOG_FORMAT=json 시 JSON serializer 적용 (`serialize=True`)
   - LOG_FORMAT=text 시 plain text 포맷 (시간 / 레벨 / 모듈 / 메시지)
   - LOG_LEVEL 환경 변수 적용 (default INFO)
   - 기존 default loguru handler 제거 (`logger.remove()`) 후 재구성 — 중복 출력 차단
2. `InterceptHandler` 가 stdlib logging 호출을 loguru 로 통과:
   - `logging.getLogger("uvicorn")`, `logging.getLogger("sqlalchemy")` 등의 출력이 loguru 의 통일 포맷으로 노출
3. `app/main.py` 가 import 시점에 `setup_logging()` 호출
4. `Settings` 에 환경 변수 5개 추가 (LOG_LEVEL / LOG_FORMAT / LOG_FILE / LOG_FILE_ROTATION / LOG_FILE_RETENTION)
5. 신규 회귀 가드:
   - `setup_logging()` 호출 후 `logger.warning("test")` 출력이 stderr 에 plain text (default) — capsys 검증
   - `LOG_FORMAT=json` 환경에서 같은 호출이 JSON 파싱 가능
   - InterceptHandler 가 `logging.getLogger("test").warning("x")` 호출을 loguru sink 로 통과
6. 기존 61 테스트 PASS 유지 (default 설정이 기존 동작 호환).

---

## 5. 설계

### 5.1 `Settings` 추가 (5개 환경 변수)

```python
# app/core/config.py
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT: str = os.getenv("LOG_FORMAT", "text")  # text | json
LOG_FILE: Optional[str] = os.getenv("LOG_FILE")     # None 이면 file sink 미활성
LOG_FILE_ROTATION: str = os.getenv("LOG_FILE_ROTATION", "10 MB")
LOG_FILE_RETENTION: str = os.getenv("LOG_FILE_RETENTION", "7 days")
```

`LOG_LEVEL`, `LOG_FORMAT` field validator 로 허용값 검증 (`DEBUG|INFO|WARNING|ERROR|CRITICAL`, `text|json`).

### 5.2 `app/core/logging.py::setup_logging()`

```python
"""애플리케이션 로깅 설정 — loguru 단일 표면."""

import logging
import sys
from loguru import logger
from app.core.config import settings


class InterceptHandler(logging.Handler):
    """stdlib logging 호출을 loguru 로 통과시킨다."""

    def emit(self, record: logging.LogRecord) -> None:
        # loguru 레벨 매핑
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        # caller frame 찾기 (loguru 가 호출 위치를 정확히 표시하도록)
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


_TEXT_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def setup_logging() -> None:
    """환경 변수 기반 로깅 구성. import 시점에 1회 호출."""
    logger.remove()  # default handler 제거

    # stderr sink
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format=_TEXT_FORMAT if settings.LOG_FORMAT == "text" else "{message}",
        serialize=settings.LOG_FORMAT == "json",
        colorize=settings.LOG_FORMAT == "text",
    )

    # file sink (선택)
    if settings.LOG_FILE:
        logger.add(
            settings.LOG_FILE,
            level=settings.LOG_LEVEL,
            format=_TEXT_FORMAT if settings.LOG_FORMAT == "text" else "{message}",
            serialize=settings.LOG_FORMAT == "json",
            rotation=settings.LOG_FILE_ROTATION,
            retention=settings.LOG_FILE_RETENTION,
        )

    # stdlib logging → loguru intercept
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for noisy in ("uvicorn", "uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).handlers = [InterceptHandler()]
```

### 5.3 `app/main.py` 호출

```python
from app.core.logging import setup_logging
setup_logging()  # FastAPI app 생성 전, import 시점에
```

### 5.4 회귀 가드 매트릭스

| 케이스 | 검증 |
| --- | --- |
| default (LOG_FORMAT=text, no file) | `setup_logging()` 후 `logger.warning("x")` → stderr 출력에 "WARNING" + "x" 포함 |
| LOG_FORMAT=json | monkeypatch → 같은 호출의 stderr 출력이 JSON parseable (`json.loads(line)`) |
| InterceptHandler | `logging.getLogger("test_intercept").warning("y")` → loguru sink 통과 |
| 기존 행동 보존 | 61개 회귀 테스트 PASS (`pytest` 출력 캡처가 깨지지 않음) |

### 5.5 테스트 전략

- pytest 의 `capsys` fixture 로 stderr 캡처
- `setup_logging()` 을 fixture 로 호출 (각 테스트 격리 — monkeypatch 로 settings 변경 후 setup_logging 재호출)
- `logger.remove()` + `setup_logging()` 패턴이라 race 없음 (single sink)

---

## 6. 영향

- **운영 환경**: `LOG_FORMAT=json` + `LOG_FILE=/var/log/app.log` 같은 .env 만 추가하면 수집 파이프라인 즉시 연결 가능.
- **개발 환경**: default 가 colorized text + stderr 라 가독성 유지. 변경 없이 동작.
- **테스트**: default text 유지 → capsys 출력 안정. 신규 회귀 가드 +3 정도.
- **uvicorn / sqlalchemy 로그**: InterceptHandler 통과로 loguru 통일 포맷. 첫 도입 시 약간의 출력 차이 가능 (stdout vs stderr / 색상 등) — PR description 에 명시.
- **알람/대시보드**: 본 PR 은 sink 까지. 실제 대시보드/알람 룰은 별도 운영 작업.

---

## 7. 후속 작업 (이번 PR 범위 밖)

- Sentry / 외부 sink 통합 (Sentry SDK + DSN 환경 변수)
- request_id contextvars 주입 (FastAPI middleware) — 분산 트레이싱 기반
- 다운그레이드 감지 로그 dedup (per-process 캐시 또는 샘플링) — handoff §6 별도 항목
- audit log (DB/외부 기록) — 별도 PRD
- log 대시보드/알람 룰 셋업 (운영 작업)
- RUNBOOK §환경 변수 단락 보강 (LOG_* 5개 추가) — 본 PR 범위 안에 포함할지 별도 후속할지 진행 중 판단

---

## 8. 리스크

| 리스크 | 가능성 | 대응 |
| --- | --- | --- |
| `setup_logging()` 의 `logger.remove()` 가 다른 호출처의 sink 도 제거 | 중 | 본 프로젝트는 loguru sink 추가 호출 없음. main.py 의 import 시점 호출이라 단일 진입점. 향후 다른 모듈이 sink 추가하지 않도록 docstring 명시. |
| InterceptHandler 가 기존 stdlib logging 호출을 두 번 출력 (stdlib + loguru) | 중 | `logging.basicConfig(force=True)` + 명시적 noisy logger handler 교체로 차단. 테스트로 검증. |
| pytest 환경에서 `setup_logging()` 호출이 conftest 의 logger 사용에 충돌 | 낮음 | conftest 가 logger 사용 안 함. 테스트 fixture 로 격리. |
| LOG_FILE 경로의 디렉토리가 없거나 권한 없음 | 낮음 | loguru 가 자동 생성 시도. 실패 시 stderr 출력. RUNBOOK 후속에 명시. |
| LOG_FORMAT=json 일 때 colorize 가 활성화되어 ANSI escape 가 JSON 에 포함 | 낮음 | `colorize=False` 명시 (json 분기). 회귀 가드로 JSON parseable 검증. |
| uvicorn access log 가 loguru 통과로 형식 변화 → 모니터링 룰 영향 | 낮음 | 본 프로젝트는 운영 미배포 단계. PR description 에 변경 명시. |

---

## 9. 결정 사항 (확정)

- [x] **단일 setup 함수** `app/core/logging.py::setup_logging()`. main.py 의 import 시점에 1회 호출.
- [x] **환경 변수 5개**: `LOG_LEVEL`, `LOG_FORMAT`, `LOG_FILE`, `LOG_FILE_ROTATION`, `LOG_FILE_RETENTION`. default 는 기존 동작 호환.
- [x] **InterceptHandler 본 PR 에 포함** — uvicorn / sqlalchemy 의 stdlib logging 호출도 loguru 로 통과. 로깅 표면 단일화.
- [x] **field validator 로 LOG_LEVEL / LOG_FORMAT 허용값 검증** — 운영 실수 조기 차단.
- [x] **Sentry / request_id / audit log 비범위** — 별도 후속.
- [x] **호출처 변경 없음** — 기존 `logger.warning` / `logger.exception` 그대로. sink/포맷만 변화.
- [x] **회귀 가드 +3**: default text / JSON format / InterceptHandler 통과.

---

## 10. 참고

- `docs/[PRD]라운드_다운그레이드_차단.md` (PR #13 — loguru 첫 도입)
- `app/user/service.py` (loguru 호출 위치)
- `app/main.py` (lifespan / FastAPI app)
- `app/core/config.py` (Settings 패턴)
- loguru docs: https://loguru.readthedocs.io/
- loguru + stdlib logging intercept: https://loguru.readthedocs.io/en/stable/overview.html#entirely-compatible-with-standard-logging
- `docs/RUNBOOK.md` (환경 변수 단락 — 후속 갱신)
