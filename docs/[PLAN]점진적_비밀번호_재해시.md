# 점진적 비밀번호 재해시 구현 Plan

| 항목         | 내용                                                                  |
| ------------ | --------------------------------------------------------------------- |
| 작성일       | 2026-05-23                                                            |
| 연관 PRD     | [`[PRD]점진적_비밀번호_재해시.md`](./[PRD]점진적_비밀번호_재해시.md) |
| 상태         | 제안 (Draft)                                                          |
| 추정 작업량  | 약 1 시간 (구현 + 단위/통합 테스트 + 검증)                             |
| 핵심 헬퍼    | `app/core/security.py::needs_rehash`                                  |

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 기준 최신 상태에서 `feature/lazy-rehash` 브랜치 생성
- [ ] `uv run pytest` 현재 35/35 PASS 확인
- [ ] PRD §4.1 / §4.2 / §5 의 결정 사항 확인

---

## 1. 작업 분해

### Step 1. `app/core/security.py` — `needs_rehash` 추가

**변경 내용**

기존 `verify_password`, `get_password_hash` 다음에 헬퍼 추가.

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

**검증**

```bash
/usr/local/bin/mise exec -- uv run python -c "
from app.core.security import needs_rehash, get_password_hash
# 현재 라운드 해시 → False
h = get_password_hash('test')
assert needs_rehash(h) is False, 'current-round hash should not need rehash'
# malformed → False
assert needs_rehash('not-a-hash') is False
assert needs_rehash('') is False
print('OK')
"
```

---

### Step 2. `app/user/service.py` — `authenticate_user` 자동 업그레이드

**변경 내용**

1. import 에 `needs_rehash` 추가
2. `authenticate_user` 본문에 lazy upgrade 분기 추가

```python
# app/user/service.py 상단
from app.core.security import (
    create_access_token,
    get_password_hash,
    needs_rehash,
    verify_password,
)

# authenticate_user 본문 (변경 후)
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
            user.hashed_password = new_hash
        except Exception:
            # 재해시 실패는 인증 자체를 막지 않음 (백그라운드 작업).
            # 운영 환경에서는 logger.exception(...) 등으로 모니터링 권장.
            pass

    return user
```

**검증**

```bash
uv run pytest tests/user/test_router.py::test_login -v --tb=short
```

기존 로그인 케이스 PASS (시드 해시 = 현재 라운드 → 재해시 분기 미발생).

---

### Step 3. 단위 테스트 추가 (3 케이스)

**대상**: `tests/core/test_security.py` (기존 파일 확장)

```python
# 기존 import 옆에 추가 (이미 settings, bcrypt import 되어 있음)
from app.core.security import needs_rehash  # 신규 함수 추가


def test_needs_rehash_detects_different_rounds():
    """현재 settings 와 다른 라운드의 해시는 재해시 대상."""
    plain = "test_password"
    # 의도적으로 다른 라운드로 해시 (settings 가 12 이면 4 와 다름)
    low_round = bcrypt.hashpw(
        plain.encode("utf-8"), bcrypt.gensalt(rounds=4)
    ).decode("utf-8")

    assert needs_rehash(low_round) is True


def test_needs_rehash_returns_false_for_current_rounds():
    """현재 settings 라운드와 동일한 해시는 재해시 대상이 아님."""
    hashed = get_password_hash("test_password")
    assert needs_rehash(hashed) is False


def test_needs_rehash_returns_false_for_malformed_hash():
    """잘못된 형식의 해시는 보수적으로 False (재해시 안 함)."""
    assert needs_rehash("not-a-bcrypt-hash") is False
    assert needs_rehash("") is False
    # parts[2] 가 정수로 변환 불가
    assert needs_rehash("$2b$abc$xxx") is False
```

**검증**

```bash
uv run pytest tests/core/test_security.py -v --tb=short
```

기존 5 + 신규 3 = 8 케이스 PASS.

---

### Step 4. 통합 자동 업그레이드 테스트 추가

**대상**: `tests/user/test_router.py` (기존 파일 확장)

기존 `test_login` 다음에 추가.

```python
@pytest.mark.asyncio
async def test_login_upgrades_old_bcrypt_hash(
        client: AsyncClient,
        db_session,
):
    """저장된 비밀번호 해시가 낮은 라운드면, 로그인 직후 자동 업그레이드된다.

    PR #7 (bcrypt 라운드 환경별 설정) + 본 PR (lazy rehash) 의 시너지를 검증.
    운영자가 BCRYPT_ROUNDS 를 상향한 후, 기존 사용자의 해시가 로그인 시
    자동으로 새 라운드로 업그레이드되는 것이 핵심.
    """
    import bcrypt as _bcrypt
    from app.core.config import settings
    from app.user.models import UserModel

    plain = "passwd1234"
    # 의도적으로 낮은 라운드 (4) 로 시드 — settings 가 12 이면 자동 업그레이드 대상
    old_hash = _bcrypt.hashpw(
        plain.encode("utf-8"), _bcrypt.gensalt(rounds=4)
    ).decode("utf-8")

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
    assert new_rounds == settings.BCRYPT_ROUNDS, (
        f"expected {settings.BCRYPT_ROUNDS} rounds, got {new_rounds}"
    )
    assert user.hashed_password != old_hash
```

**검증**

```bash
uv run pytest tests/user/test_router.py::test_login_upgrades_old_bcrypt_hash -v --tb=short
```

1 케이스 PASS.

---

### Step 5. 전체 회귀 검증

```bash
uv run pytest -v
```

기존 35 + 신규 4 = **39 PASS** 확인.

```bash
# 정합성 점검 — needs_rehash 와 authenticate_user 의 lazy upgrade 가 함께 동작
grep -n "needs_rehash" app/ tests/ -r
# 기대 출력:
# - app/core/security.py 의 함수 정의
# - app/user/service.py 의 호출
# - tests/core/test_security.py 의 import + 호출
```

---

## 2. 산출물 체크리스트

- [ ] `app/core/security.py` — `needs_rehash` 함수 신규 추가
- [ ] `app/user/service.py` — import + `authenticate_user` 의 lazy upgrade 분기
- [ ] `tests/core/test_security.py` — needs_rehash 단위 테스트 3 케이스
- [ ] `tests/user/test_router.py` — 통합 자동 업그레이드 1 케이스
- [ ] `uv run pytest -v` **39/39 PASS**

---

## 3. 테스트 케이스 (완료 판정 기준)

### 3.1 신규 4 케이스

| #   | 테스트                                              | 검증 포인트                                              |
| --- | --------------------------------------------------- | -------------------------------------------------------- |
| 1   | `test_needs_rehash_detects_different_rounds`        | 다른 라운드 (4) 해시 → True                              |
| 2   | `test_needs_rehash_returns_false_for_current_rounds` | 현재 라운드 해시 → False                                 |
| 3   | `test_needs_rehash_returns_false_for_malformed_hash` | 잘못된 형식 → False (예외 X)                             |
| 4   | `test_login_upgrades_old_bcrypt_hash`               | 4 라운드 시드 → 로그인 → DB 해시가 settings 라운드로 갱신 |

### 3.2 기존 (PASS 유지)

| 그룹                        | 케이스 수 | 핵심 보장                                                    |
| --------------------------- | --------- | ------------------------------------------------------------ |
| 사용자 라우터 (인증/조회)   | 9         | `test_login` 등 — 시드가 현재 라운드라 재해시 미발생          |
| 상품 라우터                 | 12        | 인증에 의존하는 admin 흐름 — PASS 유지                        |
| 보안 (test_security)        | 5         | 기존 가드 + neue needs_rehash 가드는 §3.1 에서 별도            |
| datetime / 권한 / 의존성    | 9         |                                                              |
| **합계**                    | **35**    | + 신규 4 = **39**                                            |

---

## 4. 동작 매트릭스

| 시나리오                              | 시드 해시 라운드 | 로그인 응답 | DB 해시 변화                        |
| ------------------------------------- | ---------------- | ----------- | ----------------------------------- |
| 현재 라운드와 일치                    | 12 (= settings)  | 200         | 변화 없음 (재해시 분기 미발생)      |
| 낮은 라운드 (legacy / 강화 시나리오)  | 4                | 200         | settings.BCRYPT_ROUNDS 로 자동 갱신 |
| 높은 라운드 (강도 약화 시나리오)      | 14               | 200         | settings.BCRYPT_ROUNDS 로 갱신 (대칭) |
| 비밀번호 불일치                       | (무관)           | 401         | 변화 없음 (verify 단계에서 실패)    |
| 사용자 없음                           | -                | 401         | 변화 없음                           |

> 강도 약화 시나리오는 운영 권장 안 됨. 코드는 대칭적으로 처리.

---

## 5. 회귀 방지 체크리스트

PR 머지 전 모두 확인.

- [ ] `uv run pytest` **39/39 PASS**
- [ ] `grep -n "def needs_rehash" app/core/security.py` 결과 1 건
- [ ] `grep -n "needs_rehash" app/user/service.py` 결과 1 건 (import + 호출)
- [ ] `test_login_upgrades_old_bcrypt_hash` 의 DB 해시 라운드 검증 통과
- [ ] 인증 응답 자체는 변경 없음 (재해시 성공/실패 무관)
- [ ] 정상 케이스에서 추가 DB 쓰기 발생하지 않음 (시드 해시가 현재 라운드와 일치)

---

## 6. 롤백 전략

- 본 작업은 `security.py` + `service.py` + 테스트 2 파일.
- 별도 브랜치 (`feature/lazy-rehash`) 에서 작업. 문제 시 `git checkout main` 으로 원복.
- 의존성 흐름이 단방향이라 (`security` → `service`) 둘 다 함께 revert 해야 일관성 유지.
- 만약 lazy upgrade 에서 race / 예외가 빈번히 발생하면 service 의 try/except 분기만 비활성화 → 헬퍼는 유지.

---

## 7. 후속 작업 (별도 이슈 권장)

| #   | 항목                                                              | 권장 처리                                                       |
| --- | ----------------------------------------------------------------- | --------------------------------------------------------------- |
| 1   | 재해시 실패 시 logger 로 기록 (운영 모니터링)                     | 별도 PR — logging 인프라 정비와 함께                            |
| 2   | 라운드 다운그레이드 차단 (`stored < settings` 만 재해시)          | 운영 정책 결정 후 별도 PR                                       |
| 3   | 대량 일괄 재해시 admin 도구 (운영자가 모든 사용자 즉시 강화)      | 별도 PRD — 작업 큐 / cron job 등 인프라 필요                    |
| 4   | bcrypt → Argon2 점진적 마이그레이션                              | 별도 PRD — 알고리즘 변경은 본 PR 의 라운드 변경과 별도 카테고리 |
| 5   | 재해시 이벤트 audit log                                          | 별도 PRD                                                        |

---

## 8. 참고

- 관련 PRD: [`[PRD]점진적_비밀번호_재해시.md`](./[PRD]점진적_비밀번호_재해시.md)
- 핵심 코드:
  - `app/core/security.py` — `needs_rehash` 추가 위치
  - `app/user/service.py:23 authenticate_user` — 수정 대상
  - `app/user/repository.py:57 update` — 재해시 시 호출
- bcrypt 해시 형식: $2b$<rounds>$<22-char-salt><31-char-hash>
- 선례:
  - PR #5 (passlib 제거)
  - PR #7 (bcrypt 라운드 환경별 설정 — 본 PR 의 직접 선행)
