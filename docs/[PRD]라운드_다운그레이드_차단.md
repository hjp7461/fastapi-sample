# [PRD] bcrypt 라운드 다운그레이드 차단 + 재해시 로깅

| 항목 | 내용 |
| --- | --- |
| 상태 | 제안 (Draft) |
| 작성일 | 2026-05-23 |
| 출처 | PR #11 §4.1 / §리스크 #2 후속 + [HANDOFF] §6 "재해시 실패 로깅" 합본 |
| 분류 | 운영 보안 정책 + 운영 모니터링 |
| 추정 작업량 | 소~중 (≤ 1 시간, security 헬퍼 + service 분기 + loguru 통합 + 테스트) |

---

## 1. 배경

### 1.1 PR #11 의 두 가지 미해결 후속

PR #11 (lazy rehash) 에서 명시적으로 두 가지 후속을 남겨두었다.

1. **다운그레이드 시 자동 약화 (§리스크 #2)**
   - 현재 `needs_rehash` 는 `stored_rounds != settings.BCRYPT_ROUNDS` 로 대칭 비교.
   - 운영자가 실수/의도적으로 라운드를 낮추면 모든 로그인이 약한 라운드로 재해시되어 보안 약화.
2. **재해시 실패가 조용히 무시 (§리스크 #1, [HANDOFF] §6)**
   - `app/user/service.py::authenticate_user::42-51` 의 `except Exception: pass`.
   - 코멘트에 "운영 환경에서는 logger.exception(...) 등으로 모니터링 권장" 라고 명시.

본 PRD 는 두 후속을 하나의 PR 로 묶어 처리한다 — 둘 다 `authenticate_user` 의 lazy-rehash 분기에서 발생하는 정책/관측 이슈이며 같은 흐름에서 함께 다루는 게 응집도가 높다.

### 1.2 손볼 코드 위치

| 파일 | 현재 상태 | 본 PR 변경 |
| --- | --- | --- |
| `app/core/security.py::needs_rehash` | `stored != configured` 대칭 비교 | `stored < configured` 단방향 |
| `app/core/security.py` (헬퍼) | 라운드 추출 로직이 `needs_rehash` 내부에 인라인 | `_extract_bcrypt_rounds(hashed) -> Optional[int]` 로 추출 |
| `app/user/service.py::authenticate_user` | `except Exception: pass` (조용히 통과) | `logger.exception("rehash failed for user_id=...")` |
| `app/user/service.py::authenticate_user` | 다운그레이드 케이스 무처리 | `logger.warning("rehash skipped: downgrade ...")` |
| `pyproject.toml` | `loguru>=0.7.0` 의존성 존재, **사용처 0건** | 의존성은 그대로, `service.py` 에서 첫 사용 |

---

## 2. 목적

1. 운영자가 `BCRYPT_ROUNDS` 를 낮춰도 이미 저장된 강한 해시를 자동 약화시키지 않는다 (**업그레이드만 허용, 다운그레이드 차단**).
2. 다운그레이드 케이스를 **조용히 무시하지 않고** 운영자가 인지할 수 있도록 `logger.warning` 으로 가시화한다.
3. 재해시 실패 (`get_password_hash` 또는 `repository.update` 예외) 시 **인증 흐름은 보호하되**, `logger.exception` 으로 실패 이벤트를 기록해 운영 모니터링 기반을 마련한다.
4. 프로젝트 첫 loguru 사용처를 정착시켜 향후 다른 모듈도 동일 패턴을 따를 수 있게 한다 (`from loguru import logger`).

---

## 3. 비목적

- loguru sink/포맷 설정 변경 (별도 setup 모듈, JSON 출력 등) — 본 PR 은 기본 stderr sink 그대로.
- 환경별 라운드 분리 (개발 4 / 운영 13) — 별도 마스터 목록 항목.
- 해시 라운드 강제 일괄 업그레이드 admin 도구 — 별도 PRD.
- audit log (DB/외부 시스템 기록) — 본 PR 은 stdout/stderr 로깅만.
- 알고리즘 변경 (bcrypt → Argon2) — 별도 PRD.

---

## 4. 성공 기준

- [ ] `app/core/security.py::needs_rehash` 가 `<` 비교를 사용한다.
- [ ] `app/core/security.py::_extract_bcrypt_rounds(hashed) -> Optional[int]` 헬퍼 신설, `needs_rehash` 가 이를 사용.
- [ ] `app/user/service.py::authenticate_user` 가:
  - 업그레이드 (stored < configured) 시 재해시 시도
  - 재해시 실패 시 `logger.exception("rehash failed: user_id=%s", user.id)` 기록 후 인증은 성공
  - 다운그레이드 (stored > configured) 감지 시 `logger.warning("rehash skipped: downgrade detected (stored=%s, configured=%s)", stored, configured)`
- [ ] 기존 41 PASS 유지.
- [ ] 신규 회귀 가드:
  - `needs_rehash` 다운그레이드 케이스 False 반환 검증
  - service 의 다운그레이드 감지 시 logger.warning 호출 검증 (caplog/loguru-pytest 통합)
  - service 의 재해시 실패 시 logger.exception 호출 + 인증은 정상 성공 검증
- [ ] 기존 `test_needs_rehash_detects_different_rounds` → `test_needs_rehash_detects_lower_rounds` 로 이름 정정.

---

## 5. 설계

### 5.1 `app/core/security.py` 변경

```python
from typing import Optional


def _extract_bcrypt_rounds(hashed_password: str) -> Optional[int]:
    """bcrypt 해시 (`$2b$<rounds>$<salt+hash>`) 에서 라운드 수를 추출.

    파싱 실패 시 None — 호출자가 보수적 처리.
    """
    try:
        return int(hashed_password.split("$")[2])
    except (IndexError, ValueError):
        return None


def needs_rehash(hashed_password: str) -> bool:
    """저장된 해시의 라운드가 현재 settings.BCRYPT_ROUNDS 보다 낮은지 확인.

    "낮은 경우에만" True — 업그레이드 (12 → 13) 만 재해시 대상이고, 다운그레이드
    (13 → 12) 는 보안 약화이므로 차단. 운영자가 BCRYPT_ROUNDS 를 낮춰도 이미
    저장된 강한 해시를 약화시키지 않는다.

    파싱 실패 시 보수적으로 False (재해시 안 함).
    """
    stored = _extract_bcrypt_rounds(hashed_password)
    if stored is None:
        return False
    return stored < settings.BCRYPT_ROUNDS
```

내부 헬퍼는 `_` 접두어를 유지하되 같은 패키지 내 (`app.user.service`) 에서 import 해 다운그레이드 감지에 재사용한다 — Python 관례상 `_` 는 "외부 API 아님" 의 신호일 뿐 import 자체를 막지 않는다.

### 5.2 `app/user/service.py` 변경

```python
from loguru import logger  # 신규 import (프로젝트 첫 사용처)

from app.core.security import (
    _extract_bcrypt_rounds,
    create_access_token,
    get_password_hash,
    needs_rehash,
    verify_password,
)


async def authenticate_user(self, email: str, password: str) -> Optional[User]:
    user = await self.user_repository.get_by_email(email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None

    stored_rounds = _extract_bcrypt_rounds(user.hashed_password)
    configured = settings.BCRYPT_ROUNDS

    if stored_rounds is not None and stored_rounds < configured:
        try:
            new_hash = get_password_hash(password)
            await self.user_repository.update(
                user.id, {"hashed_password": new_hash}
            )
            user.hashed_password = new_hash
        except Exception:
            # 재해시 실패는 인증 자체를 막지 않는다.
            logger.exception(
                "rehash failed (user_id={}, stored={}, configured={})",
                user.id, stored_rounds, configured,
            )
    elif stored_rounds is not None and stored_rounds > configured:
        logger.warning(
            "rehash skipped: downgrade detected (user_id={}, stored={}, configured={})",
            user.id, stored_rounds, configured,
        )

    return user
```

핵심 차이:
- `needs_rehash` 호출 대신 `stored_rounds` 를 직접 비교 — 업그레이드/다운그레이드 분기를 명시적으로 분리.
- `needs_rehash` 자체는 외부 API 로 유지 (다른 호출처에서 쓸 수 있도록).
- loguru 의 `{}` placeholder 스타일 사용 (logger 의 lazy formatting).

### 5.3 로그 메시지 컨벤션

| 시나리오 | 레벨 | 메시지 (예시) |
| --- | --- | --- |
| 재해시 시도 → 실패 | `exception` | `rehash failed (user_id=42, stored=12, configured=13)` + traceback |
| 다운그레이드 감지 → 스킵 | `warning` | `rehash skipped: downgrade detected (user_id=42, stored=13, configured=12)` |

`logger.exception` 은 자동으로 traceback 을 포함한다 (loguru 의 표준 동작).

### 5.4 테스트 전략

| # | 케이스 | 위치 |
| --- | --- | --- |
| 1 | `needs_rehash` 가 stored > configured 인 해시에 False 반환 (다운그레이드 차단) | `tests/core/test_security.py::test_needs_rehash_does_not_downgrade` |
| 2 | 기존 `test_needs_rehash_detects_different_rounds` 를 `test_needs_rehash_detects_lower_rounds` 로 이름 정정 | 동일 파일 |
| 3 | 다운그레이드 케이스에서 `authenticate_user` 가 logger.warning 호출 + 인증 성공 + 해시 보존 | `tests/user/test_router.py` 또는 `tests/user/test_service.py` 신규 |
| 4 | 재해시 중 예외 발생 시 `authenticate_user` 가 logger.exception 호출 + 인증 성공 + 기존 해시 보존 | 동일 |

loguru 의 테스트 캡처는 `caplog` 가 기본 stdlib logging 만 잡으므로 **loguru 의 `propagate` 패턴** 또는 **monkeypatching `logger` 자체** 를 사용한다. 후자가 단순:

```python
def test_authenticate_logs_downgrade(monkeypatch, ...):
    warnings = []
    monkeypatch.setattr(
        "app.user.service.logger.warning",
        lambda *args, **kwargs: warnings.append((args, kwargs)),
    )
    # ... authenticate
    assert any("downgrade detected" in str(a) for a, _ in warnings)
```

### 5.5 `_extract_bcrypt_rounds` 의 export 정책

`_` 접두어를 유지하되 `service.py` 에서 import 가능. 외부 API 로 승격할지는 다른 호출처가 생길 때 (`get_user`, audit log, admin 도구 등) 다시 평가. 본 PR 은 의도된 내부 노출 1 곳.

---

## 6. 영향

| 영역 | 영향 |
| --- | --- |
| `app/core/security.py` | 헬퍼 추출 + `<` 비교로 변경 + docstring 갱신 |
| `app/user/service.py` | loguru import + authenticate_user 의 lazy-rehash 블록 재구성 |
| 운영 일치/업그레이드 케이스 | **동작 변화 없음** (재해시 정상 수행) |
| 운영 다운그레이드 케이스 | 보안 약화 차단 + logger.warning 기록 |
| 재해시 실패 케이스 | 동작은 동일 (인증 성공), 실패 이벤트 logger.exception 가시화 |
| 외부 API / DB 스키마 | 변화 없음 |
| 로그 출력 | 기본 stderr 에 warning/exception 메시지 추가 (정상 운영에서는 0 건) |

---

## 7. 리스크

| 리스크 | 가능성 | 대응 |
| --- | --- | --- |
| loguru 가 sink 미설정 상태로 stderr 에 출력 → 테스트 출력 노이즈 | 낮음 | pytest 의 `-s` 안 쓰면 캡처됨. CI 영향 없음 |
| `_extract_bcrypt_rounds` 의 `_` 접두어 import 가 컨벤션 위반 | 낮음 | 명시적 결정 (§5.5). 후속 PR 에서 외부 API 로 승격 검토 |
| 다운그레이드 감지 로그가 **모든 로그인**마다 출력 → 양 폭증 | 낮음 | 운영자가 다운그레이드를 의도적으로 한 경우에만 발생. 빈도가 너무 높으면 별도 후속 (샘플링/dedup) |
| 테스트에서 logger 모킹이 다른 테스트로 누수 | 낮음 | `monkeypatch` fixture 가 자동 teardown |

---

## 8. 결정 사항 (확정)

- [x] `needs_rehash` 의 비교 연산자: `!=` → `<`
- [x] `_extract_bcrypt_rounds` 내부 헬퍼 추출 — `needs_rehash` 와 `service.py` 양쪽에서 재사용
- [x] 다운그레이드 감지 시 `logger.warning` — `user_id`, stored, configured 포함
- [x] 재해시 실패 시 `logger.exception` — traceback 자동 포함, `user_id`, stored, configured 포함
- [x] loguru 의 첫 프로젝트 사용처 — `from loguru import logger` 가 패턴이 됨
- [x] sink/포맷 커스터마이징은 본 PR 비목적 (별도 운영 인프라 작업)
- [x] 기존 케이스 `test_needs_rehash_detects_different_rounds` → `test_needs_rehash_detects_lower_rounds` 로 이름 정정
- [x] 신규 테스트: needs_rehash 다운그레이드 False 1건 + service 다운그레이드 logger.warning 1건 + service 재해시 실패 logger.exception 1건 → 총 +3

---

## 9. 참고

- `docs/[PRD]점진적_비밀번호_재해시.md` §4.1, §리스크 #1, §리스크 #2
- `docs/[PRD]bcrypt_라운드_환경별_설정.md`
- `app/core/security.py::needs_rehash`
- `app/user/service.py::authenticate_user::42-51`
- `pyproject.toml` (loguru 의존성)
- loguru docs: https://loguru.readthedocs.io
