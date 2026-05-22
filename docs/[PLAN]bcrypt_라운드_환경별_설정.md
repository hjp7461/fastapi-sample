# bcrypt 라운드 환경별 설정 구현 Plan

| 항목         | 내용                                                                       |
| ------------ | -------------------------------------------------------------------------- |
| 작성일       | 2026-05-22                                                                 |
| 연관 PRD     | [`[PRD]bcrypt_라운드_환경별_설정.md`](./[PRD]bcrypt_라운드_환경별_설정.md) |
| 상태         | 제안 (Draft)                                                               |
| 추정 작업량  | 약 45 분 (구현 + 테스트 + 검증)                                             |
| 환경 변수    | `BCRYPT_ROUNDS=12` (기본값)                                                |
| 범위 검증    | 4 ~ 31 (bcrypt 표준)                                                       |

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 기준 최신 상태에서 `feature/bcrypt-rounds-config` 브랜치 생성
- [ ] `uv run pytest` 현재 30/30 PASS 확인
- [ ] PRD §4.1 의 `field_validator` 도입 확인
- [ ] PRD §4.4 의 호환성 보장 (기존 12 라운드 해시 → 새 settings 영향 없음)

---

## 1. 작업 분해

### Step 1. `app/core/config.py` — `BCRYPT_ROUNDS` 추가

**변경 내용**

1. `from pydantic import field_validator` 추가
2. `Settings` 클래스 보안 설정 섹션에 `BCRYPT_ROUNDS` 필드 추가
3. `field_validator` 로 범위 검증 (4 ≤ rounds ≤ 31)

```python
# app/core/config.py
import os
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """
    애플리케이션 설정 클래스.
    환경 변수에서 값을 로드합니다.
    """
    # 기본 설정
    PROJECT_NAME: str = "FastAPI Clean Architecture"
    ...

    # 보안 설정
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-for-jwt")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    BCRYPT_ROUNDS: int = int(os.getenv("BCRYPT_ROUNDS", "12"))

    ...

    @field_validator("BCRYPT_ROUNDS")
    @classmethod
    def validate_bcrypt_rounds(cls, v: int) -> int:
        """bcrypt 표준 범위 검증 (4 ≤ rounds ≤ 31)."""
        if not (4 <= v <= 31):
            raise ValueError(
                f"BCRYPT_ROUNDS must be between 4 and 31, got {v}"
            )
        return v

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
    }
```

**검증**

```bash
/usr/local/bin/mise exec -- uv run python -c "
from app.core.config import settings
print('BCRYPT_ROUNDS:', settings.BCRYPT_ROUNDS)
assert settings.BCRYPT_ROUNDS == 12
print('OK')
"
```

---

### Step 2. `app/core/security.py` — settings 참조로 변경

**변경 내용**

1. 모듈 상수 `_BCRYPT_ROUNDS = 12` **삭제** (settings 로 일원화)
2. `get_password_hash` 의 `bcrypt.gensalt(rounds=...)` 가 `settings.BCRYPT_ROUNDS` 참조

```python
# app/core/security.py (변경 후)
import bcrypt
import jwt

from app.core.config import settings  # 이미 import 되어 있음


def verify_password(plain_password: str, hashed_password: str) -> bool:
    ...  # 변경 없음


def get_password_hash(password: str) -> str:
    """비밀번호를 bcrypt 로 해시 (UTF-8 인코딩, settings.BCRYPT_ROUNDS 라운드)."""
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")
```

> `_BCRYPT_ROUNDS = 12` 라인 + 위 주석 라인 한 줄 삭제.

**검증**

```bash
/usr/local/bin/mise exec -- uv run python -c "
from app.core.security import get_password_hash
from app.core.config import settings
h = get_password_hash('test123')
# 해시 형식: \$2b\$<rounds>\$<salt+hash>
actual_rounds = int(h.split('\$')[2])
assert actual_rounds == settings.BCRYPT_ROUNDS, f'expected {settings.BCRYPT_ROUNDS}, got {actual_rounds}'
print(f'OK — rounds in hash: {actual_rounds}')
"
```

---

### Step 3. `.env.example` 갱신

**변경 내용**

운영 가이드와 함께 `BCRYPT_ROUNDS=12` 라인 추가.

```bash
# .env.example (추가)

# bcrypt 해시 라운드 (4 ~ 31). 운영은 13 ~ 14 권장
# 비밀번호 해싱 비용 증가 = 무차별 대입 공격 비용 증가 / API 응답 지연 증가
BCRYPT_ROUNDS=12
```

기존 `SECRET_KEY` 라인 근처에 추가하는 것이 자연스럽다.

---

### Step 4. 신규 회귀 가드 테스트 추가

**대상**: `tests/core/test_security.py` (기존 파일 확장)

```python
# 기존 import 옆에 추가
import bcrypt

from app.core.config import settings


def test_get_password_hash_uses_configured_rounds():
    """get_password_hash 가 settings.BCRYPT_ROUNDS 를 사용한다."""
    hashed = get_password_hash("test_password")
    # bcrypt 해시 형식: $2b$<rounds>$<salt+hash>
    parts = hashed.split("$")
    actual_rounds = int(parts[2])
    assert actual_rounds == settings.BCRYPT_ROUNDS


def test_verify_works_across_different_rounds():
    """라운드가 다른 두 해시를 동일 verify 함수로 검증 가능 (호환성)."""
    plain = "samePassword"

    # 명시적으로 다른 라운드로 해시
    low_round_hash = bcrypt.hashpw(
        plain.encode("utf-8"), bcrypt.gensalt(rounds=10)
    ).decode("utf-8")
    default_round_hash = get_password_hash(plain)

    assert verify_password(plain, low_round_hash) is True
    assert verify_password(plain, default_round_hash) is True
    assert verify_password("wrong", low_round_hash) is False
    assert verify_password("wrong", default_round_hash) is False
```

> PRD §5.1 의 3번째 케이스 (`test_bcrypt_rounds_default_is_12`) 는 환경 변수가 설정된 환경에서 의미가 달라지므로 본 Plan 에서는 위 2 케이스로 압축. 기본값 검증은 Step 1 의 수동 검증에서 다룸.

**검증**

```bash
uv run pytest tests/core/test_security.py -v --tb=short
```

기존 3 + 신규 2 = 5 케이스 PASS.

---

### Step 5. 전체 회귀 검증

```bash
uv run pytest -v
```

기존 30 + 신규 2 = **32 PASS** 확인.

```bash
# settings 가 정상 import 되는지 (validator 가 시작 시점에 평가)
uv run python -c "from app.core.config import settings; print(settings.BCRYPT_ROUNDS)"
# → 12

# 환경 변수 override 동작 확인
BCRYPT_ROUNDS=13 uv run python -c "from app.core.config import settings; print(settings.BCRYPT_ROUNDS)"
# → 13

# 범위 외 값 fail-fast 동작 확인
BCRYPT_ROUNDS=2 uv run python -c "from app.core.config import settings" 2>&1 | grep -q "between 4 and 31" && echo "validator OK"
```

---

## 2. 산출물 체크리스트

- [ ] `app/core/config.py` — `BCRYPT_ROUNDS` 필드 + `field_validator` 추가
- [ ] `app/core/security.py` — 모듈 상수 `_BCRYPT_ROUNDS` 제거, `settings.BCRYPT_ROUNDS` 참조
- [ ] `.env.example` — `BCRYPT_ROUNDS=12` 라인 + 운영 가이드 주석 추가
- [ ] `tests/core/test_security.py` — 신규 2 케이스 추가
- [ ] `uv run pytest -v` **32/32 PASS**
- [ ] 환경 변수 `BCRYPT_ROUNDS=13` override 동작 확인
- [ ] 범위 외 값 (`BCRYPT_ROUNDS=2`) fail-fast 동작 확인

---

## 3. 테스트 케이스 (완료 판정 기준)

### 3.1 기존 (PASS 유지)

| 테스트                                | 검증 포인트                                                          |
| ------------------------------------- | -------------------------------------------------------------------- |
| `test_hash_then_verify_roundtrip`     | 새 구현의 hash → verify 라운드트립                                    |
| `test_verify_legacy_passlib_hash`     | 박제된 passlib 해시 (12 라운드) 검증 — settings 변경에 무관           |
| `test_verify_handles_malformed_hash`  | 잘못된 해시 입력 시 False                                            |
| 인증 흐름 (`test_create_user` 등)     | 통합 회귀 통과                                                       |

### 3.2 신규 (2 케이스)

| #   | 테스트                                          | 검증 포인트                                                              |
| --- | ----------------------------------------------- | ------------------------------------------------------------------------ |
| 1   | `test_get_password_hash_uses_configured_rounds` | 새로 생성된 해시의 라운드가 `settings.BCRYPT_ROUNDS` 와 일치             |
| 2   | `test_verify_works_across_different_rounds`     | 10 라운드 해시와 기본 라운드 해시 둘 다 같은 verify 함수로 검증 가능       |

### 3.3 수동 검증

| 시나리오                                | 명령                                                                    | 기대                                |
| --------------------------------------- | ----------------------------------------------------------------------- | ----------------------------------- |
| 기본값                                  | `uv run python -c "from app.core.config import settings; print(settings.BCRYPT_ROUNDS)"` | `12`                  |
| 환경 변수 override                      | `BCRYPT_ROUNDS=13 uv run python -c ...`                                | `13`                                |
| 범위 외 값 (fail-fast)                  | `BCRYPT_ROUNDS=2 uv run python -c ...`                                  | ValidationError + "between 4 and 31" |
| 범위 외 값 (위쪽)                       | `BCRYPT_ROUNDS=50 uv run python -c ...`                                 | ValidationError                     |

---

## 4. 회귀 방지 체크리스트

PR 머지 전 모두 확인.

- [ ] `uv run pytest` **32/32 PASS**
- [ ] `grep -rn "_BCRYPT_ROUNDS" app/` 결과 없음 (모듈 상수 완전 제거)
- [ ] `grep -rn "rounds=12\|rounds = 12" app/` 결과 없음 (하드코딩 잔존 없음)
- [ ] 환경 변수 `BCRYPT_ROUNDS=13` 적용 시 새 해시가 `$2b$13$...` 로 생성되는지 확인
- [ ] 기존 해시 (`tests/core/test_security.py::LEGACY_HASH_TEST` 의 `$2b$12$...`) 가 새 settings 와 무관하게 verify 통과
- [ ] `.env.example` 에 `BCRYPT_ROUNDS=12` 와 운영 가이드 주석 포함

---

## 5. 롤백 전략

- 본 작업은 3 파일 변경 (`config.py`, `security.py`, `.env.example`) + 테스트 1.
- 별도 브랜치 (`feature/bcrypt-rounds-config`) 에서 작업. 문제 시 `git checkout main` 으로 원복.
- `config.py` 와 `security.py` 는 함께 변경되어야 일관성 유지 (둘 중 하나만 되돌리면 settings.BCRYPT_ROUNDS AttributeError).

---

## 6. 후속 작업 (별도 이슈 권장)

| #   | 항목                                                                          | 권장 처리                                                       |
| --- | ----------------------------------------------------------------------------- | --------------------------------------------------------------- |
| 1   | 라운드 업그레이드 시 기존 사용자 점진적 재해시 (verify 직후 settings 라운드로 다시 해시) | 별도 PRD — 정책 결정 필요                                       |
| 2   | 테스트 환경 라운드 다운 (e.g., `BCRYPT_ROUNDS=4`) 로 테스트 속도 향상         | conftest 에서 settings override 패턴 — 필요해질 때 도입         |
| 3   | 운영 라운드 업그레이드 런북 (12 → 13 변경 영향 / 모니터링 지표)               | docs/ 에 운영 가이드 별도 작성                                  |
| 4   | Argon2 등 더 강한 알고리즘 마이그레이션                                       | passlib PR §7-#1 의 후속                                        |

---

## 7. 참고

- 관련 PRD: [`[PRD]bcrypt_라운드_환경별_설정.md`](./[PRD]bcrypt_라운드_환경별_설정.md)
- 핵심 코드:
  - `app/core/config.py:13 Settings` — 수정 대상
  - `app/core/security.py:6, 31` — `_BCRYPT_ROUNDS` 제거 및 `settings.BCRYPT_ROUNDS` 참조
  - `tests/core/test_security.py` — 신규 케이스 추가 위치
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- pydantic field_validator: https://docs.pydantic.dev/latest/concepts/validators/
- 선례: PR #5 (passlib 제거 + bcrypt 직접 사용)
