# passlib crypt deprecation 해소 구현 Plan

| 항목         | 내용                                                                             |
| ------------ | -------------------------------------------------------------------------------- |
| 작성일       | 2026-05-22                                                                       |
| 연관 PRD     | [`[PRD]passlib_crypt_deprecation_해소.md`](./[PRD]passlib_crypt_deprecation_해소.md) |
| 상태         | 제안 (Draft)                                                                     |
| 추정 작업량  | 약 1.5시간 (구현 + 호환성 검증 + 의존성 동기화)                                   |
| 채택 알고리즘 | bcrypt (직접 사용, 라운드 12)                                                     |
| 호환성       | passlib 시절 해시 (`$2b$...`) 검증 보장                                          |
| 부수 변경    | 비밀번호 `max_length`: 100 → 64                                                  |

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 기준 최신 상태에서 `feature/passlib-removal` 브랜치 생성
- [ ] `uv run pytest` 현재 27/27 PASS 확인
- [ ] PRD §4.1 의 bcrypt 라운드 (12) 확인
- [ ] PRD §4.4 의 max_length 변경 (64) 확인
- [ ] PRD §5.1 의 호환성 회귀 가드 (legacy 해시 박제) 확인

---

## 1. 작업 분해

### Step 1. 레거시 해시 박제값 생성

**목적**: 현재 (passlib 사용 중) 상태에서 알려진 평문 → 해시 매핑을 박제하여, 변경 후에도 동일한 해시를 verify 할 수 있는지 검증한다.

**방법**

브랜치 생성 직후, **passlib 코드가 살아있는 상태에서** 다음 명령으로 해시를 생성하여 노트해둔다.

```bash
/usr/local/bin/mise exec -- uv run python -c "
from passlib.context import CryptContext
ctx = CryptContext(schemes=['bcrypt'], deprecated='auto')
# 결정된 평문으로 해시 생성
print('TestPassword123 →', ctx.hash('TestPassword123'))
print('admin12345 →', ctx.hash('admin12345'))
"
```

출력된 해시 2개를 `tests/core/test_security.py` 의 fixture 로 박제.

> **중요**: bcrypt 는 매번 다른 salt 를 쓰므로 해시값이 매번 다르다. 박제 시점의 해시를 그대로 코드에 하드코딩한다 (실행 시 재생성 X).

---

### Step 2. `app/core/security.py` 재작성

**대상**: `app/core/security.py:10-29`

**변경 내용**

1. `from passlib.context import CryptContext` 제거
2. `import bcrypt` 추가
3. `pwd_context` 전역 변수 제거
4. `_BCRYPT_ROUNDS = 12` 상수 도입
5. `get_password_hash`, `verify_password` 본문 교체

```python
# app/core/security.py (변경 후 — 비밀번호 부분만)
import bcrypt

_BCRYPT_ROUNDS = 12  # passlib 기본값과 동일


def get_password_hash(password: str) -> str:
    """비밀번호를 bcrypt 로 해시 (UTF-8 인코딩, 12 라운드)."""
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """입력 비밀번호가 해시와 일치하는지 검증.

    해시 포맷이 잘못되면 ValueError 가 발생할 수 있어 안전하게 False 로 변환.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        return False
```

> JWT 관련 함수 (`create_access_token`, `decode_access_token`) 는 변경 없음.

**검증**

```bash
/usr/local/bin/mise exec -- uv run python -c "
from app.core.security import get_password_hash, verify_password
h = get_password_hash('hello123')
assert verify_password('hello123', h) is True
assert verify_password('wrong', h) is False
print('OK')
"
```

---

### Step 3. 비밀번호 `max_length` 변경

**대상**: `app/user/schemas.py`

**변경 내용**

```python
# UserCreate (변경 전)
password: str = Field(..., min_length=8, max_length=100)

# (변경 후)
password: str = Field(..., min_length=8, max_length=64)
```

```python
# UserUpdate (변경 전)
password: Optional[str] = Field(None, min_length=8, max_length=100)

# (변경 후)
password: Optional[str] = Field(None, min_length=8, max_length=64)
```

**검증**

```bash
uv run pytest tests/user/test_router.py::test_create_user -x --tb=short
```

기존 시드 (`"newpassword123"` 14자) 가 새 max 안에 들어가므로 PASS.

---

### Step 4. 의존성 변경

**대상**: `pyproject.toml`

**변경 내용**

1. `dependencies` 의 `"passlib[bcrypt]>=1.7.4"` 를 `"bcrypt>=4.0"` 로 교체
2. `[[tool.mypy.overrides]]` 의 `module` 리스트에서 `"passlib.*"` 제거

```toml
# 변경 전
dependencies = [
    ...
    "passlib[bcrypt]>=1.7.4",
    ...
]

[[tool.mypy.overrides]]
module = ["sqlalchemy.*", "sqlmodel.*", "alembic.*", "dependency_injector.*", "jose.*", "passlib.*", "loguru.*"]

# 변경 후
dependencies = [
    ...
    "bcrypt>=4.0",
    ...
]

[[tool.mypy.overrides]]
module = ["sqlalchemy.*", "sqlmodel.*", "alembic.*", "dependency_injector.*", "jose.*", "loguru.*"]
```

### Step 4.1 lockfile 동기화

```bash
/usr/local/bin/mise exec -- uv sync --all-extras
```

확인:

```bash
grep -c '^name = "passlib"' uv.lock  # → 0 이어야 함
grep -c '^name = "bcrypt"' uv.lock   # → 1
```

---

### Step 5. 호환성 회귀 가드 테스트 추가

**대상**: `tests/core/test_security.py` (신규), 필요시 `tests/core/__init__.py` 도 신규

```python
# tests/core/test_security.py
"""암호화 유틸리티 회귀 가드.

특히 passlib 시절에 생성된 해시의 호환성을 보장한다.
"""
from app.core.security import get_password_hash, verify_password


# Step 1 에서 박제한 값 — passlib + bcrypt 가 생성한 실제 해시
LEGACY_HASH_TEST = "<Step 1 출력값 1>"     # 평문: 'TestPassword123'
LEGACY_HASH_ADMIN = "<Step 1 출력값 2>"    # 평문: 'admin12345'


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
    """
    assert verify_password("TestPassword123", LEGACY_HASH_TEST) is True
    assert verify_password("wrong_password", LEGACY_HASH_TEST) is False
    assert verify_password("admin12345", LEGACY_HASH_ADMIN) is True
    assert verify_password("admin54321", LEGACY_HASH_ADMIN) is False


def test_verify_handles_malformed_hash():
    """잘못된 형식의 해시는 False 를 반환 (예외 X)."""
    assert verify_password("password", "not-a-bcrypt-hash") is False
    assert verify_password("password", "") is False
    assert verify_password("password", "$2b$short") is False
```

> 도메인 객체 검증 (`test_role.py`) 처럼 동기 테스트로 작성. pytest-asyncio `auto` 모드와 충돌 없음.

**검증**

```bash
uv run pytest tests/core/test_security.py -v --tb=short
```

3 케이스 PASS 확인.

---

### Step 6. 전체 회귀 검증

```bash
uv run pytest -v
uv run pytest --cov=app/core/security --cov-report=term-missing
```

- 기존 27 + 신규 3 = **30 PASS** 확인
- `app/core/security.py` 커버리지: `get_password_hash`, `verify_password` (정상 케이스 + malformed 분기)
- DeprecationWarning 카운트 확인: `passlib` / `crypt` 관련 warning 0 건

```bash
uv run pytest 2>&1 | grep -i "passlib\|crypt" | grep -v "fastcrypto\|cryptography"
```

→ 출력 없어야 함.

---

## 2. 산출물 체크리스트

- [ ] `app/core/security.py` — passlib 제거, bcrypt 직접 사용
- [ ] `app/user/schemas.py` — `password` max_length 100 → 64 (UserCreate, UserUpdate)
- [ ] `pyproject.toml` — `passlib[bcrypt]` → `bcrypt`, mypy override 정리
- [ ] `uv.lock` — `uv sync` 로 갱신, passlib 제거 확인
- [ ] `tests/core/test_security.py` (신규) — 3 케이스
- [ ] `tests/core/__init__.py` (필요 시 신규)
- [ ] `uv run pytest -v` **30/30 PASS**
- [ ] `passlib`/`crypt` 관련 DeprecationWarning 0 건 확인

---

## 3. 테스트 케이스 (완료 판정 기준)

다음 30 케이스가 모두 PASS 해야 한다.

### 3.1 신규 회귀 가드 (3 케이스)

| #   | 테스트                                | 검증 포인트                                                          |
| --- | ------------------------------------- | -------------------------------------------------------------------- |
| 1   | `test_hash_then_verify_roundtrip`     | 새 구현의 hash → verify 라운드트립 + wrong password 거부             |
| 2   | `test_verify_legacy_passlib_hash`     | passlib 시절 해시 (`$2b$...`) 의 verify 호환성 — **호환성 핵심 가드** |
| 3   | `test_verify_handles_malformed_hash`  | 잘못된 해시 입력 시 예외 X, False 반환 (방어적 코드 검증)            |

### 3.2 인증 흐름 회귀 (기존, PASS 유지)

| 테스트                            | 핵심 검증                                |
| --------------------------------- | ---------------------------------------- |
| `test_create_user`                | 회원가입 → 해시 생성 → 응답              |
| `test_login`                      | 로그인 → 해시 verify → 토큰 발급         |
| `test_get_current_user`           | 토큰 검증 → 본인 정보 조회                |
| `test_update_current_user`        | password 포함 업데이트 시 해시 재생성     |

### 3.3 기타 회귀 (기존 23 케이스, PASS 유지)

상품 관리, admin 분기, UserRole 권한 메서드 등 모든 기존 테스트가 PASS 유지.

---

## 4. DeprecationWarning 매트릭스

| Warning 출처                               | 변경 전 | 변경 후 |
| ------------------------------------------ | ------- | ------- |
| `passlib/utils/__init__.py:854 'crypt' is deprecated` | 매 실행 시 발생 | **0 건** |
| `bcrypt` 라이브러리                        | 0 건    | 0 건    |
| 기타 (pydantic, sqlalchemy 등)             | 변동 없음 | 변동 없음 |

검증 명령:

```bash
uv run pytest 2>&1 | grep -c "crypt' is deprecated"
# 변경 전: 1 이상
# 변경 후: 0
```

---

## 5. 회귀 방지 체크리스트

PR 머지 전 모두 확인.

- [ ] `uv run pytest` **30/30 PASS**
- [ ] `grep -r passlib app/ tests/` 결과 없음
- [ ] `grep -c '^name = "passlib"' uv.lock` 결과 `0`
- [ ] `pyproject.toml` 의 `dependencies` 에 `passlib` 없음
- [ ] `pyproject.toml` 의 `tool.mypy.overrides` 의 module 리스트에 `passlib.*` 없음
- [ ] 새 비밀번호 `max_length=64` 가 `UserCreate`, `UserUpdate` 양쪽에 적용됨
- [ ] DeprecationWarning 카운트가 변경 전 대비 감소 확인 (passlib 관련만 추적)
- [ ] 수동 검증: `POST /users/` → `POST /users/token` → `GET /users/me` 전체 흐름 (`pytest` 가 자동으로 검증)

---

## 6. 롤백 전략

- 본 작업은 4 파일 변경 (`security.py`, `schemas.py`, `pyproject.toml`, `uv.lock`) + 신규 1.
- 별도 브랜치 (`feature/passlib-removal`) 에서 작업. 문제 시 `git checkout main` 으로 원복.
- 단일 파일 단독 revert 시 주의: `pyproject.toml` 과 `security.py` 는 함께 변경되어야 일관성 유지. 둘 중 하나만 되돌리면 의존성/import 불일치 발생.

---

## 7. 후속 작업 (별도 이슈 권장)

| #   | 항목                                                                              | 권장 처리                                                        |
| --- | --------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| 1   | Argon2 / scrypt 등 더 강한 해시 알고리즘으로 마이그레이션                         | 별도 PRD — 점진적 재해시 정책 필요                               |
| 2   | bcrypt 라운드 (cost factor) 환경별 설정 (개발/운영 분리)                          | 별도 이슈 — 운영에서 13~14 권장                                  |
| 3   | 비밀번호 정책 강화 (복잡도, 사전 단어 차단, breach 검사)                          | 별도 PRD                                                         |
| 4   | 비밀번호 변경 감사 로그 (audit)                                                    | 별도 PRD (UserRole PR §7-#5 와 통합 가능)                        |
| 5   | 다국어 비밀번호 지원 (현재 UTF-8 64자 입력 시 한글은 21자가 한계)                | 정책 결정 필요 — 본 PRD 는 영문 비밀번호 가정                    |

---

## 8. 참고

- 관련 PRD: [`[PRD]passlib_crypt_deprecation_해소.md`](./[PRD]passlib_crypt_deprecation_해소.md)
- 핵심 코드:
  - `app/core/security.py:10-29` — 수정 대상
  - `app/user/schemas.py:23, 41` — max_length 변경 위치
  - `app/user/service.py:28, 40, 67` — 호출자 (변경 불요)
  - `tests/conftest.py:115, 143` — 시드 (변경 불요)
- `bcrypt` 문서: https://github.com/pyca/bcrypt
- PEP 594 (crypt 모듈 제거): https://peps.python.org/pep-0594/
- NIST SP 800-63B 비밀번호 길이 가이드라인
