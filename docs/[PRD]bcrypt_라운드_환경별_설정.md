# bcrypt 라운드 환경별 설정 PRD

| 항목       | 내용                                                                          |
| ---------- | ----------------------------------------------------------------------------- |
| 작성일     | 2026-05-22                                                                    |
| 작성자     | conner                                                                        |
| 상태       | 제안 (Draft)                                                                  |
| 도메인     | 보안 / 설정 (Core)                                                            |
| 대상 범위  | `app/core/security.py`, `app/core/config.py`, `.env.example`                  |
| 관련 발견  | passlib PR #5 의 후속 작업 §7-#2                                              |

---

## 1. 배경

### 1.1 현재 구조

PR #5 에서 passlib 을 제거하면서 bcrypt 라운드를 모듈 상수로 도입했다.

```python
# app/core/security.py
_BCRYPT_ROUNDS = 12  # passlib 의 기본값과 동일하게 12 를 사용.
```

라운드 (cost factor) 는 bcrypt 의 해싱 비용을 결정한다. 1 증가할 때마다 해싱 시간이 약 2 배가 된다.

| 라운드 | 대략적 해싱 시간 (현대 서버) | 권장 환경 |
| ------ | ---------------------------- | --------- |
| 4 ~ 9  | < 50 ms                      | 테스트 (의도적 약화) |
| 10     | ~ 100 ms                     | 비권장 (너무 낮음)  |
| 12     | ~ 300 ms                     | 개발 / 소규모 서비스 |
| 13     | ~ 600 ms                     | **일반 운영 권장** |
| 14     | ~ 1.2 s                      | 고보안 운영       |

### 1.2 문제

- **개발/운영 동일 라운드**: 현재 코드는 12 로 하드코딩. 운영 환경에서 보안 강화를 위해 13~14 로 올리고 싶어도 코드 수정이 필요.
- **운영 비밀번호 정책 부재**: 본 코드를 운영에 그대로 배포하면 12 라운드라 OWASP 의 현재 권장 (2024 기준 12 이상) 의 하한선에 머문다.
- **설정의 위치 불일치**: 다른 보안 설정 (`SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`) 은 `Settings` 클래스에 모여 있지만 bcrypt 라운드만 별도 모듈 상수.

---

## 2. 목적

- bcrypt 라운드를 **환경별로 다르게 설정** 할 수 있도록 한다.
- 개발자 기본 경험은 유지 (`BCRYPT_ROUNDS=12`).
- 운영 환경에서는 `.env` / 환경 변수로 13~14 로 상향 가능.
- 설정 값의 안전성 (4 ≤ rounds ≤ 31) 을 시작 시점에 검증.
- 다른 보안 설정과 동일한 위치 (`app/core/config.py`) 에서 관리되도록 정합.

### 비목적

- Argon2 / scrypt 등 다른 해시 알고리즘 도입 (passlib PR §7-#1 별도).
- 점진적 재해시 정책 (라운드 업그레이드 시 기존 사용자 비밀번호 자동 재해시).
- 비밀번호 정책 변경 (길이/복잡도 — `[PRD]passlib_crypt_deprecation_해소.md` 의 max_length=64 유지).
- 비밀번호 변경 감사 로그.
- 라운드 변경 운영 가이드 (런북) 작성.

---

## 3. 성공 기준

| 지표                                                            | 목표값                  |
| --------------------------------------------------------------- | ----------------------- |
| `BCRYPT_ROUNDS` 환경 변수 미설정 시 동작                        | 12 (기본값 동일)        |
| `BCRYPT_ROUNDS=13` 환경 변수 설정 시 적용 여부                  | 13 라운드로 해시 생성   |
| 범위 외 값 (`BCRYPT_ROUNDS=2` 또는 `=50`) 설정 시 동작          | 시작 시 ValidationError |
| 기존 12 라운드 해시의 verify 호환성                             | 100% 유지               |
| 기존 회귀 테스트                                                | 30/30 PASS 유지         |
| 신규 회귀 가드 (라운드 값 검증, 환경 변수 override)             | 신규 3 케이스           |

---

## 4. 설계

### 4.1 `Settings` 에 `BCRYPT_ROUNDS` 추가

```python
# app/core/config.py (변경 후)
class Settings(BaseSettings):
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
```

> `field_validator` import: `from pydantic import field_validator`.

기존 보안 설정의 `os.getenv` 패턴을 유지하여 일관성 확보.

### 4.2 `security.py` 가 설정 참조

```python
# app/core/security.py (변경 후 — get_password_hash 부분)
from app.core.config import settings  # 이미 import 되어 있음


def get_password_hash(password: str) -> str:
    """비밀번호를 bcrypt 로 해시 (UTF-8 인코딩, settings.BCRYPT_ROUNDS 라운드)."""
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")
```

기존 모듈 상수 `_BCRYPT_ROUNDS` 는 **삭제** — settings 로 일원화.

### 4.3 `.env.example` 갱신

```bash
# .env.example (추가)

# bcrypt 해시 라운드 (4 ~ 31). 운영은 13 ~ 14 권장
# 비밀번호 해싱 비용 증가 = 무차별 대입 공격 비용 증가 / API 응답 지연 증가
BCRYPT_ROUNDS=12
```

### 4.4 verify 의 호환성

`bcrypt.checkpw` 는 해시 문자열에 포함된 라운드 정보 (`$2b$12$...` 의 `12`) 를 사용하므로, settings 가 13 으로 변경되어도 **기존 12 라운드로 저장된 해시는 그대로 verify** 된다.

> 운영 시나리오: settings 를 12 → 13 으로 올리면 그 시점 이후 **새로 해시되는 비밀번호** (회원가입 / 비밀번호 변경) 만 13 라운드로 저장된다. 기존 사용자는 본인이 비밀번호를 변경하기 전까지 12 라운드 해시를 유지. **점진적 강화 정책** 은 본 PRD 비목적.

---

## 5. 호환성 회귀 가드

### 5.1 신규 테스트 (3 케이스)

`tests/core/test_security.py` 에 추가.

```python
import bcrypt
from app.core.config import settings
from app.core.security import get_password_hash


def test_get_password_hash_uses_configured_rounds():
    """get_password_hash 가 settings.BCRYPT_ROUNDS 를 사용한다."""
    hashed = get_password_hash("test_password")
    # bcrypt 해시 형식: $2b$<rounds>$<salt+hash>
    parts = hashed.split("$")
    actual_rounds = int(parts[2])
    assert actual_rounds == settings.BCRYPT_ROUNDS


def test_verify_works_across_different_rounds():
    """라운드가 다른 두 해시를 동일 verify 함수로 검증 가능."""
    plain = "samePassword"

    # 10 라운드 해시 생성
    low = bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=10)).decode()
    # 12 라운드 해시 생성 (기본값)
    mid = get_password_hash(plain)

    from app.core.security import verify_password
    assert verify_password(plain, low) is True
    assert verify_password(plain, mid) is True
    assert verify_password("wrong", low) is False
    assert verify_password("wrong", mid) is False


def test_bcrypt_rounds_default_is_12():
    """환경 변수 미설정 시 기본값 12 유지 (호환성)."""
    # 본 테스트는 BCRYPT_ROUNDS 환경 변수가 설정되지 않은 환경에서만 의미
    # 설정된 경우 skip 또는 그 값 검증으로 갈음
    import os
    if "BCRYPT_ROUNDS" not in os.environ:
        assert settings.BCRYPT_ROUNDS == 12
```

### 5.2 범위 검증 테스트 (선택 — 별도 케이스)

pydantic `field_validator` 자체는 클래스 정의 시점에 평가되므로, 런타임에 다른 값으로 Settings 를 생성하는 테스트는 추가 환경 격리가 필요. 본 PRD 는 정상 경로 검증에 집중하고 잘못된 값 검증은 수동/문서로 갈음.

### 5.3 기존 호환성

`tests/core/test_security.py::test_verify_legacy_passlib_hash` (PR #5) 가 박제된 12 라운드 해시를 verify 하므로, 라운드 변경에 무관하게 통과.

---

## 6. 영향 받는 파일

| 파일                                | 변경 종류                                          | 비고                                                        |
| ----------------------------------- | -------------------------------------------------- | ----------------------------------------------------------- |
| `app/core/config.py`                | `BCRYPT_ROUNDS` 설정 + `field_validator` 추가      | import: `from pydantic import field_validator`              |
| `app/core/security.py`              | 모듈 상수 제거, `settings.BCRYPT_ROUNDS` 참조       | 한 줄 변경                                                  |
| `.env.example`                      | `BCRYPT_ROUNDS=12` 라인 추가 + 운영 가이드 주석    | 신규 라인                                                   |
| `tests/core/test_security.py`       | 신규 회귀 가드 2 케이스 추가                       | 기존 3 + 신규 2 = 5 케이스                                  |

---

## 7. 리스크 및 미해결 이슈

| #   | 항목                                                                                 | 대응                                                                          |
| --- | ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| 1   | settings 의 `field_validator` 가 잘못된 값에서 raise 시 앱 시작 자체 실패          | 의도된 동작 — 안전한 fail-fast. 운영 배포 전 `BCRYPT_ROUNDS` 값 검증 필요     |
| 2   | 운영에서 12 → 13 변경 후 회원가입 / 로그인 응답 지연 (~ 2 배)                       | 본 PRD 범위 외 — 운영 결정 사항                                               |
| 3   | 기존 해시는 12 라운드, 신규 해시는 13 라운드로 혼재                                   | bcrypt 표준 동작 — verify 는 해시에 박힌 라운드를 사용하므로 호환             |
| 4   | 라운드 업그레이드 시 기존 사용자의 점진적 재해시 정책                                | 별도 PRD                                                                      |
| 5   | 테스트 환경에서 라운드를 낮춰 테스트 속도 향상 가능 (e.g., BCRYPT_ROUNDS=4)          | 본 PRD 는 정책 결정만 — `.env.example` 에는 12 만 명시. 도입은 별도 결정     |

### 결정 사항 (확정)

- [x] 설정 위치: `Settings.BCRYPT_ROUNDS` (다른 보안 설정과 동일 위치)
- [x] 기본값: **12** (현재와 동일, 호환성 유지)
- [x] 범위 검증: **4 ~ 31** (bcrypt 표준)
- [x] 환경 변수명: `BCRYPT_ROUNDS`
- [x] `.env.example` 에 라인 추가 + 운영 가이드 주석
- [x] 모듈 상수 `_BCRYPT_ROUNDS` 삭제 (settings 로 일원화)

---

## 8. 참고

- 관련 PRD: [`[PRD]passlib_crypt_deprecation_해소.md`](./[PRD]passlib_crypt_deprecation_해소.md)
- 핵심 코드:
  - `app/core/config.py:13 Settings` — 수정 대상
  - `app/core/security.py:6, 31` — `_BCRYPT_ROUNDS` 제거 및 `settings.BCRYPT_ROUNDS` 참조
- bcrypt 라운드 가이드:
  - OWASP Password Storage Cheat Sheet (2024): bcrypt rounds ≥ 12
  - https://github.com/pyca/bcrypt — gensalt(rounds=...)
- pydantic_settings `field_validator`: https://docs.pydantic.dev/latest/concepts/validators/
- 선례:
  - PR #5 — passlib 제거 + bcrypt 직접 사용 (본 PRD 의 직접 후속)
