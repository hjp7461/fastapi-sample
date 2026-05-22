# passlib crypt deprecation 해소 PRD

| 항목       | 내용                                                                          |
| ---------- | ----------------------------------------------------------------------------- |
| 작성일     | 2026-05-22                                                                    |
| 작성자     | conner                                                                        |
| 상태       | 제안 (Draft)                                                                  |
| 도메인     | 보안 / 인증 (User)                                                            |
| 대상 범위  | `app/core/security.py`, `pyproject.toml` 의 passlib 의존성                    |
| 관련 발견  | 테스트 아키텍처 PRD §7-#5 의 잔여 이슈                                         |

---

## 1. 배경

### 1.1 현재 구조

```python
# app/core/security.py:15
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
```

- 의존성: `passlib[bcrypt]>=1.7.4` (`pyproject.toml:45`)
- 알고리즘: bcrypt (해시 포맷 `$2b$12$...`)
- 실제로 해시 작업을 수행하는 라이브러리는 `bcrypt==4.3.0` (이미 lockfile 에 존재)

### 1.2 문제

테스트 실행 시 다음 deprecation 경고가 매번 발생.

```
DeprecationWarning: 'crypt' is deprecated and slated for removal
in a future version. Use timezone-aware objects to represent
datetimes in UTC: ...
File: passlib/utils/__init__.py:854
    from crypt import crypt as _crypt
```

원인:

- `passlib` 의 일부 내부 모듈이 Python 표준 라이브러리 `crypt` 를 import.
- **`crypt` 모듈은 Python 3.13 에서 제거** 예정 (PEP 594).
- 현재 Python 3.12 환경에서는 동작하지만, 향후 Python 업그레이드 시 **passlib import 가 실패** 한다.

### 1.3 진단 — 어떤 래퍼가 실제 일을 하나

`passlib[bcrypt]` 는 두 가지를 함께 설치한다.

1. `passlib` — 다양한 해시 알고리즘을 추상화하는 래퍼 라이브러리
2. `bcrypt` — 실제 bcrypt 알고리즘을 구현하는 C 확장 라이브러리

본 프로젝트는 **`schemes=["bcrypt"]` 단일 알고리즘** 만 사용하므로, passlib 의 다중 알고리즘/마이그레이션 기능은 활용되지 않는다. passlib 는 사실상 **얇은 래퍼** 역할만 한다.

→ `bcrypt` 라이브러리를 직접 사용하면 동일 기능을 제공하면서 `crypt` deprecation 을 회피할 수 있다.

---

## 2. 목적

- Python 3.13+ 호환성 확보 (`crypt` 모듈 제거 대응).
- 테스트 실행 시 매번 발생하는 `passlib` 관련 DeprecationWarning 제거.
- 비밀번호 해싱 API (`get_password_hash`, `verify_password`) 의 외부 시그니처를 유지하여 호출자 영향을 0 으로 한다.
- **기존 해시 (이미 DB 에 저장된 사용자 비밀번호) 의 검증 호환성을 보장** 한다.

### 비목적

- 해시 알고리즘 변경 (Argon2 / scrypt / PBKDF2 등) — bcrypt 유지.
- 해시 라운드 (cost factor) 변경 — 기본값 유지.
- 비밀번호 재해시 (해시 강도 업그레이드) 정책 — 별도 이슈.
- 인증/세션/토큰 흐름 변경.

> **비밀번호 길이 정책 변경 (포함)**: 본 PRD 의 §4.4 에 `max_length` 를 100 → 64 로 줄이는 변경이 포함된다. bcrypt 의 72 바이트 제한과 일치시키고 일반적 보안 권장 범위에 맞춘다 (사용자 결정).

---

## 3. 성공 기준

| 지표                                                              | 목표값                          |
| ----------------------------------------------------------------- | ------------------------------- |
| `passlib` 관련 DeprecationWarning                                 | 0건                             |
| `passlib` 의존성 잔존 여부                                        | 0 (`pyproject.toml` / `uv.lock`) |
| `get_password_hash` / `verify_password` 의 외부 시그니처          | 변경 없음                       |
| 기존 passlib 가 생성한 해시 (`$2b$12$...`) 의 `verify_password` 호환 | 100% PASS                        |
| 기존 회귀 테스트                                                  | 27/27 PASS 유지                 |
| 추가 회귀 가드 (해시 생성/검증/호환성)                            | 신규 3 케이스                   |

---

## 4. 설계

### 4.1 새 구현

```python
# app/core/security.py (변경 후 — 비밀번호 부분만)
import bcrypt

# 해시 강도 (passlib 의 default 와 동일하게 12 라운드)
_BCRYPT_ROUNDS = 12


def get_password_hash(password: str) -> str:
    """비밀번호를 bcrypt 로 해시.

    bcrypt 는 입력의 72 바이트를 초과하는 부분을 무시한다. 본 프로젝트는
    Pydantic 단계에서 max_length=100 (UTF-8 인코딩 시 최대 400 바이트) 을
    허용하지만, passlib 1.7.4 의 기본 bcrypt 핸들러와 동일하게 raw 동작
    (72 바이트 truncate) 을 따른다. 정책 변경이 필요하면 별도 이슈.
    """
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """입력 비밀번호가 해시와 일치하는지 검증."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        # 해시 포맷이 잘못된 경우 (예: 짧은 문자열, 알 수 없는 알고리즘)
        return False
```

### 4.2 해시 포맷 호환성

- passlib + bcrypt 가 생성한 해시: `$2b$12$<22-char-salt><31-char-hash>`
- bcrypt 라이브러리 직접 사용 시 생성: 동일 포맷
- bcrypt 라이브러리는 `$2a$`, `$2b$`, `$2y$` 모두 검증 가능

→ **기존 사용자 비밀번호 마이그레이션 불필요.** verify 가 호환됨.

### 4.3 의존성 변경

```toml
# pyproject.toml 변경 전
dependencies = [
    ...
    "passlib[bcrypt]>=1.7.4",
    ...
]

[[tool.mypy.overrides]]
module = ["sqlalchemy.*", "sqlmodel.*", "alembic.*", "dependency_injector.*", "jose.*", "passlib.*", "loguru.*"]
ignore_missing_imports = true

# 변경 후
dependencies = [
    ...
    "bcrypt>=4.0",
    ...
]

[[tool.mypy.overrides]]
module = ["sqlalchemy.*", "sqlmodel.*", "alembic.*", "dependency_injector.*", "jose.*", "loguru.*"]
ignore_missing_imports = true
```

> `bcrypt` 자체에는 타입 스텁이 포함되어 있어 mypy override 불요.

### 4.4 비밀번호 길이 정책 변경

bcrypt 의 72 바이트 제한과 일치시키기 위해 Pydantic 스키마의 `max_length` 를 100 → **64** 로 변경.

```python
# app/user/schemas.py (변경 전)
class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=100)
    password_confirm: str

class UserUpdate(BaseModel):
    ...
    password: Optional[str] = Field(None, min_length=8, max_length=100)

# 변경 후
class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=64)
    password_confirm: str

class UserUpdate(BaseModel):
    ...
    password: Optional[str] = Field(None, min_length=8, max_length=64)
```

**근거**

- bcrypt 의 72 바이트 truncate 동작과 명확히 정렬 (실효 입력 한도가 곧 검증 한도)
- 64 자는 일반적 보안 권장 범위 (예: NIST SP 800-63B 가 64자 이상 허용을 권장)
- 기존 시드 데이터 (`"testpassword"` 12자 등) 영향 없음 — 회귀 0

### 4.5 호출자 (변경 없음)

`app/user/service.py`, `tests/conftest.py` 의 import 와 호출은 **그대로 유지**.

```python
from app.core.security import get_password_hash, verify_password
```

---

## 5. 호환성 회귀 가드 (신규 테스트)

가장 중요한 검증: **기존 DB 의 해시가 새 구현으로 verify 되는가.**

### 5.1 핵심 케이스

```python
# tests/core/test_security.py (신규)
"""암호화 유틸리티 회귀 가드.

특히 passlib 시절에 생성된 해시의 호환성을 보장한다.
"""
import bcrypt
import pytest

from app.core.security import get_password_hash, verify_password


def test_hash_then_verify_roundtrip():
    """새 구현 자체의 hash → verify 라운드트립."""
    plain = "MySecurePassword123!"
    hashed = get_password_hash(plain)
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_verify_legacy_passlib_hash():
    """passlib 가 생성한 형식의 해시도 검증 가능해야 한다.

    호환성 보장: 기존 DB 의 사용자 비밀번호 (passlib 시절 생성) 가
    새 구현으로도 그대로 verify 되어야 한다.

    이 해시는 passlib 1.7.4 + bcrypt 로 'TestPassword123' 을 hash 한 결과를
    하드코딩한 것이다 (테스트 실행 시점에 재생성하면 의미가 없으므로 고정값).
    """
    legacy_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewKyXJ7p5wAFHGZS"
    # 위 해시는 'TestPassword123' 을 passlib + bcrypt 1.7.4 로 해시한 값
    # (실제 마이그레이션 시 prod DB 에서 표본 해시를 가져와 검증 권장)
    assert verify_password("TestPassword123", legacy_hash) is True
    assert verify_password("wrong_password", legacy_hash) is False


def test_verify_handles_malformed_hash():
    """잘못된 형식의 해시는 False 를 반환 (예외 X)."""
    assert verify_password("password", "not-a-bcrypt-hash") is False
    assert verify_password("password", "") is False
```

> **`test_verify_legacy_passlib_hash` 의 해시값**: 본 PRD 구현 단계에서 **현재 시점의 passlib 으로 해시를 생성해 박제** 한다. 그래야 변경 전후 동일 해시가 검증 가능함을 증명할 수 있다.

### 5.2 검증 시나리오 (구현 단계 추가 검증)

구현 후 PR 머지 전 수동 확인:

1. `conftest.py` 의 `test_user`, `admin_user` 시드가 정상 생성됨 (해시 라운드 동작)
2. `POST /users/token` (로그인) 이 정상 동작
3. `POST /users/` (회원가입 → 해시 → 즉시 로그인) 정상 동작

---

## 6. 영향 받는 파일

| 파일                                       | 변경 종류                                          | 비고                                                              |
| ------------------------------------------ | -------------------------------------------------- | ----------------------------------------------------------------- |
| `app/core/security.py`                     | passlib → bcrypt 직접 사용으로 재작성              | `pwd_context` 제거, `_BCRYPT_ROUNDS` 상수 도입                    |
| `app/user/schemas.py`                      | 비밀번호 `max_length` 100 → 64                     | `UserCreate.password`, `UserUpdate.password`                      |
| `pyproject.toml`                           | `passlib[bcrypt]` → `bcrypt>=4.0`                  | mypy override 의 `passlib.*` 도 제거                              |
| `uv.lock`                                  | passlib 관련 항목 제거 + bcrypt 메타데이터 갱신    | `uv sync` 자동 수행                                               |
| `tests/core/test_security.py` (신규)       | 호환성 회귀 가드 3 케이스                          | 새 디렉토리 — `tests/core/__init__.py` 도 신규 필요할 수 있음     |

> 호출자 (`app/user/service.py`, `tests/conftest.py`) 는 변경 없음. 기존 시드 비밀번호 (12~15자) 도 새 `max_length=64` 범위 안에 들어가므로 영향 없음.

---

## 7. 테스트 영향

| 기존 테스트                                                  | 영향                                |
| ------------------------------------------------------------ | ----------------------------------- |
| `test_create_user`, `test_login`, `test_get_current_user` 등 | 동일 동작 — PASS 유지               |
| 모든 admin 시드 의존 테스트                                  | 동일 동작 — PASS 유지               |
| 신규: `tests/core/test_security.py` (3 케이스)               | 호환성 / 라운드트립 / malformed 검증 |

DeprecationWarning 카운트 비교:

- 변경 전: `'crypt' is deprecated` warning 이 매 테스트 실행 시 발생
- 변경 후: 해당 warning 0건

---

## 8. 리스크 및 미해결 이슈

| #   | 항목                                                                                  | 대응                                                                       |
| --- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| 1   | bcrypt 의 72 바이트 제한 동작                                                          | passlib 의 기본 bcrypt 핸들러도 동일하게 truncate. 호환 보장               |
| 2   | passlib 1.7.4 가 생성한 해시 ↔ bcrypt 4.x 의 verify 호환성                            | 동일 포맷 (`$2b$`) — `bcrypt.checkpw` 가 검증 가능. §5 의 회귀 가드로 자동화 |
| 3   | passlib 의 `deprecated="auto"` 기능 (해시 알고리즘 마이그레이션) 손실                 | 본 프로젝트는 bcrypt 단일 사용 → 실효 없음                                  |
| 4   | bcrypt 라이브러리 자체의 보안 취약점 발생 시                                          | passlib 보다 직접 모니터링이 단순. CVE 발생 시 `bcrypt` 패키지만 업그레이드 |
| 5   | Python 3.14+ 에서 bcrypt 라이브러리의 호환성                                          | bcrypt 는 C 확장이라 Python 표준 라이브러리 의존도 낮음. 별도 모니터링     |
| 6   | 비밀번호 `max_length=64` 변경 시 UTF-8 다바이트 문자에서는 자수 한도가 더 짧아짐 (한글 21자) | 본 프로젝트는 영문 비밀번호 가정. 다국어 사용 시 정책 별도 검토             |

### 결정 사항

- [x] 알고리즘: **bcrypt 유지** (Argon2 마이그레이션은 별도 이슈)
- [x] 라운드: **12** (passlib 기본값과 동일)
- [x] API 시그니처: **변경 없음** (호출자 영향 0)
- [x] 호환성: **legacy 해시 verify 보장** (회귀 테스트로 가드)
- [x] 비밀번호 길이: **max_length 100 → 64** (bcrypt 72바이트 한계와 정렬, 사용자 결정)

---

## 9. 참고

- Python 3.13 release notes — `crypt` 모듈 제거: https://docs.python.org/3.13/whatsnew/3.13.html
- PEP 594: Removing dead batteries from the standard library
- `bcrypt` 라이브러리 문서: https://github.com/pyca/bcrypt
- passlib 의 `crypt` 의존 위치: `passlib/utils/__init__.py:854`
- 현재 코드:
  - `app/core/security.py:10-29`
  - `pyproject.toml:45, 104`
- 호출자 (변경 불요):
  - `app/user/service.py:28, 40, 67`
  - `tests/conftest.py:115, 143`
- 선례:
  - PR #1 ~ #4 (deprecation warning 관련은 모두 후속으로 분리)
