# 점진적 비밀번호 재해시 PRD

| 항목       | 내용                                                                          |
| ---------- | ----------------------------------------------------------------------------- |
| 작성일     | 2026-05-23                                                                    |
| 작성자     | conner                                                                        |
| 상태       | 제안 (Draft)                                                                  |
| 도메인     | 보안 / 인증                                                                   |
| 대상 범위  | `app/core/security.py`, `app/user/service.py`                                 |
| 관련 발견  | bcrypt 라운드 PR #7 §7-#1 의 잔여 후속                                         |

---

## 1. 배경

### 1.1 PR #7 의 한계

PR #7 에서 bcrypt 라운드를 환경 변수 (`BCRYPT_ROUNDS`) 로 분리했다. 운영자가 12 → 13 으로 상향할 수 있게 되었지만:

> "settings 를 12 → 13 으로 올리면 그 시점 이후 **새로 해시되는 비밀번호** 만 13 라운드로 저장된다. 기존 사용자는 본인이 비밀번호를 변경하기 전까지 12 라운드 해시를 유지."

→ **이미 가입한 사용자의 보안 강화가 안 됨.** 사용자에게 "보안 강화를 위해 비밀번호를 재설정해주세요" 라고 강제하는 건 UX 손해.

### 1.2 업계 표준 패턴 — Lazy Rehash

이를 해결하는 표준 패턴이 **점진적 (lazy) 재해시** 다.

- 로그인 → `verify_password(input, stored_hash)` 성공
- 저장된 해시의 라운드 (`$2b$<rounds>$...`) 와 `settings.BCRYPT_ROUNDS` 비교
- 다르면 입력받은 평문으로 새 해시 생성 → DB 업데이트
- 다음 로그인부터는 새 라운드로 verify

passlib 의 `CryptContext` 의 `deprecated="auto"` 옵션이 정확히 이 패턴을 제공했었다. bcrypt 라이브러리 직접 사용 시에는 직접 구현 필요.

### 1.3 현재 인증 흐름

```python
# app/user/service.py:23-30
async def authenticate_user(self, email: str, password: str) -> Optional[User]:
    user = await self.user_repository.get_by_email(email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
```

→ verify 성공 후 곧바로 사용자 반환. 재해시 단계 없음.

---

## 2. 목적

- 운영자가 `BCRYPT_ROUNDS` 를 상향한 후, 기존 사용자의 비밀번호 해시가 **로그인 시점에 자동으로** 새 라운드로 업그레이드되도록 한다.
- 사용자에게 비밀번호 재설정을 요구하지 않고 보안 강화를 점진적으로 달성.
- 인증 응답에는 영향 없음 (백그라운드 업그레이드).

### 비목적

- 라운드 다운그레이드 (`13 → 12`) 시 재해시 — 비-운영 패턴이라 비목적.
- 대량 일괄 재해시 (모든 사용자의 해시를 즉시 재해시) — 별도 admin 도구.
- 알고리즘 변경 (bcrypt → Argon2) 의 점진적 마이그레이션 — 별도 PRD.
- 재해시 실패 시 사용자에게 에러 응답 — 인증은 무조건 성공시킴.
- 재해시 이벤트 audit log — 별도 PRD.

---

## 3. 성공 기준

| 지표                                                                          | 목표값                |
| ----------------------------------------------------------------------------- | --------------------- |
| `needs_rehash(stored_hash) -> bool` 헬퍼 함수 신규 추가                       | 1 개                  |
| `authenticate_user` 가 verify 후 needs_rehash 면 재해시                       | 1 흐름                |
| 재해시 실패 시 인증 응답에 영향                                               | 0 (인증은 무조건 성공) |
| 기존 회귀 테스트                                                              | 35/35 PASS 유지       |
| 신규 회귀 가드 (needs_rehash 판정 + 자동 업그레이드)                          | 신규 3 케이스         |

---

## 4. 설계

### 4.1 `needs_rehash` 헬퍼 추가

```python
# app/core/security.py (추가)
def needs_rehash(hashed_password: str) -> bool:
    """저장된 해시의 라운드가 현재 settings.BCRYPT_ROUNDS 와 다른지 확인.

    저장된 해시: $2b$<rounds>$<22-char-salt><31-char-hash>
    파싱 실패 시 보수적으로 False (재해시 안 함) 반환 — 인증 흐름 깨지지 않도록.
    """
    try:
        parts = hashed_password.split("$")
        # 형식: ['', '2b', '<rounds>', '<salt+hash>']
        stored_rounds = int(parts[2])
    except (IndexError, ValueError):
        return False
    return stored_rounds != settings.BCRYPT_ROUNDS
```

> **라운드가 다르기만 하면 True** — 12 → 13 (강화) 도, 13 → 12 (약화) 도 재해시. 운영에서는 약화 케이스가 없다고 가정하지만 코드는 대칭적으로 처리. 약화 차단이 필요하면 `stored_rounds < settings.BCRYPT_ROUNDS` 로 변경 가능 (별도 결정).

### 4.2 `authenticate_user` 의 자동 업그레이드 추가

```python
# app/user/service.py
async def authenticate_user(self, email: str, password: str) -> Optional[User]:
    """사용자 인증을 처리합니다.

    verify 성공 후 저장된 해시의 라운드가 settings.BCRYPT_ROUNDS 와 다르면
    백그라운드로 새 라운드로 재해시한다 (lazy upgrade).
    """
    user = await self.user_repository.get_by_email(email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None

    # 점진적 재해시: 라운드 불일치 시 백그라운드 업그레이드
    if needs_rehash(user.hashed_password):
        try:
            new_hash = get_password_hash(password)
            await self.user_repository.update(
                user.id, {"hashed_password": new_hash}
            )
            # 반환할 user 객체에도 새 해시 반영 (선택 — 같은 요청 내 다른 곳에서 참조 가능)
            user.hashed_password = new_hash
        except Exception:
            # 재해시 실패는 인증 자체를 막지 않음 (백그라운드 작업)
            # 운영 환경에서 logger.exception(...) 등으로 모니터링 권장
            pass

    return user
```

**핵심 결정**

- 재해시 실패 시 **인증은 성공** (try/except 로 격리). 다음 로그인 시 다시 시도.
- `user.hashed_password` 를 새 해시로 갱신 (선택 — 같은 요청 컨텍스트 내 정합성).
- 예외는 광범위하게 잡되 (DB 일시 장애, race 등), 운영 환경에서는 logger 로 기록 권장.

### 4.3 import 변경

```python
# app/user/service.py 상단
from app.core.security import (
    create_access_token,
    get_password_hash,
    needs_rehash,        # 신규
    verify_password,
)
```

### 4.4 라우터 / repository 영향

- **라우터**: 변경 없음. `authenticate_user` 의 외부 시그니처 동일.
- **repository.update**: 이미 `hashed_password` key 를 dict 로 받을 수 있음 (line 68: `update_data = {k:v for k,v in user_data.items() if v is not None}`).

---

## 5. 회귀 가드 (신규 3 케이스)

### 5.1 `tests/core/test_security.py` 확장

```python
def test_needs_rehash_detects_different_rounds():
    """현재 settings 와 다른 라운드의 해시는 재해시 대상."""
    import bcrypt as _bcrypt
    from app.core.security import needs_rehash

    plain = "test"
    # 의도적으로 다른 라운드로 해시
    low_round = _bcrypt.hashpw(
        plain.encode(), _bcrypt.gensalt(rounds=10)
    ).decode()

    assert needs_rehash(low_round) is True


def test_needs_rehash_returns_false_for_current_rounds():
    """현재 settings 라운드와 동일한 해시는 재해시 대상이 아님."""
    from app.core.security import get_password_hash, needs_rehash

    hashed = get_password_hash("test")
    assert needs_rehash(hashed) is False


def test_needs_rehash_returns_false_for_malformed_hash():
    """잘못된 형식의 해시는 보수적으로 False (재해시 안 함)."""
    from app.core.security import needs_rehash

    assert needs_rehash("not-a-bcrypt-hash") is False
    assert needs_rehash("") is False
    assert needs_rehash("$2b$abc$xxx") is False  # rounds 가 정수가 아님
```

### 5.2 통합 자동 업그레이드 테스트

`tests/user/test_router.py` 에 추가.

```python
@pytest.mark.asyncio
async def test_login_upgrades_old_bcrypt_hash(
        client: AsyncClient,
        db_session,
):
    """저장된 비밀번호 해시가 낮은 라운드면, 로그인 직후 자동 업그레이드된다."""
    import bcrypt as _bcrypt
    from app.core.config import settings
    from app.user.models import UserModel

    plain = "passwd123"
    old_hash = _bcrypt.hashpw(
        plain.encode(), _bcrypt.gensalt(rounds=4)  # 의도적으로 낮은 라운드
    ).decode()

    # 사용자 시드
    user = UserModel(
        email="legacy@example.com",
        username="legacy",
        hashed_password=old_hash,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # 로그인
    response = await client.post(
        "/api/v1/users/token",
        data={"username": "legacy@example.com", "password": plain},
    )
    assert response.status_code == 200

    # DB 의 해시가 settings.BCRYPT_ROUNDS 로 업그레이드되었는지 확인
    await db_session.refresh(user)
    new_rounds = int(user.hashed_password.split("$")[2])
    assert new_rounds == settings.BCRYPT_ROUNDS
    assert user.hashed_password != old_hash
```

> 4 라운드의 해시를 시드로 만들고, 로그인 → 12 라운드 (기본 settings) 로 자동 업그레이드되는지 검증.

---

## 6. 영향 받는 파일

| 파일                                | 변경 종류                                  | 비고                                            |
| ----------------------------------- | ------------------------------------------ | ----------------------------------------------- |
| `app/core/security.py`              | `needs_rehash` 헬퍼 함수 신규 추가         | ~ 10 줄                                         |
| `app/user/service.py`               | `authenticate_user` 의 lazy upgrade 분기   | import 1줄 + 본문 ~ 10 줄                       |
| `tests/core/test_security.py`       | needs_rehash 단위 테스트 3 케이스          | 기존 5 → 8                                      |
| `tests/user/test_router.py`         | 통합 자동 업그레이드 1 케이스               | 기존 N → N+1                                    |

---

## 7. 테스트 영향

| 기존 테스트              | 영향                                                 |
| ------------------------ | ---------------------------------------------------- |
| `test_login`             | 시드 해시가 현재 라운드와 동일 → needs_rehash False → 재해시 미발생. 응답 동일. PASS 유지 |
| 다른 인증 의존 테스트    | 동일 — PASS 유지                                     |

기존 35 + 신규 4 = **39 PASS**.

---

## 8. 리스크 및 미해결 이슈

| #   | 항목                                                                            | 대응                                                                        |
| --- | ------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| 1   | 재해시 실패 시 보안 강화가 일어나지 않음 (조용히 통과)                          | 운영 환경에서 logger 로 모니터링 권장. 본 PR 의 try/except 는 인증 흐름 보호 |
| 2   | 라운드 다운그레이드 (13 → 12) 시 재해시는 보안 약화                              | 운영에서는 다운그레이드 안 함을 전제. 필요 시 `<` 비교로 변경                |
| 3   | 매 로그인마다 추가 UPDATE 발생 (settings 변경 직후만)                           | 라운드 일치 시 needs_rehash → False. 정상 운영에서는 영향 미미               |
| 4   | 동시 로그인 시 race condition (둘이 동시에 재해시)                              | bcrypt 가 매번 새 salt → 둘 다 유효한 해시. 마지막 UPDATE 가 이김 — 안전     |
| 5   | bcrypt 해시 외 다른 형식 (legacy passlib MD5 등) 도 점진 마이그레이션 가능?     | needs_rehash 가 라운드 추출 실패 → False → 재해시 안 함. 별도 마이그레이션 PR 필요 |

### 결정 사항 (확정)

- [x] 헬퍼 위치: `app/core/security.py::needs_rehash`
- [x] 자동 업그레이드 위치: `app/user/service.py::authenticate_user` 본문 (별도 메서드 분리 X — 단순성 우선)
- [x] 비교 방식: `stored_rounds != settings.BCRYPT_ROUNDS` (강화/약화 대칭)
- [x] 실패 시 동작: 인증 성공시킴 (try/except 로 격리)
- [x] 신규 테스트: 단위 3 + 통합 1 = 4 케이스

---

## 9. 참고

- 관련 PRD: [`[PRD]bcrypt_라운드_환경별_설정.md`](./[PRD]bcrypt_라운드_환경별_설정.md), [`[PRD]passlib_crypt_deprecation_해소.md`](./[PRD]passlib_crypt_deprecation_해소.md)
- 핵심 코드:
  - `app/core/security.py` — `needs_rehash` 추가 위치
  - `app/user/service.py:23 authenticate_user` — 수정 대상
  - `app/user/repository.py:57 update` — 재해시 시 호출
- bcrypt 해시 형식 ($2b$<rounds>$<salt+hash>): https://en.wikipedia.org/wiki/Bcrypt
- 선례:
  - PR #5 (passlib 제거, bcrypt 직접 사용)
  - PR #7 (bcrypt 라운드 환경별 설정 — 본 PR 의 직접 선행)
