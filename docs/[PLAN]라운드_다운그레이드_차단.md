# [PLAN] bcrypt 라운드 다운그레이드 차단 + 재해시 로깅

| 항목 | 내용 |
| --- | --- |
| 연관 PRD | `docs/[PRD]라운드_다운그레이드_차단.md` |
| 브랜치 | `feature/rehash-policy-logging` |
| 추정 작업량 | 소~중 (≤ 1 시간) |
| 채택 전략 | security 헬퍼 추출 + service lazy-rehash 블록 재구성 + loguru 첫 사용처 정착 |

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 최신 상태 (`317015a..9dd62be` 머지 반영됨)
- [ ] `uv run pytest` 41/41 PASS, warning 0 기준선 확인
- [ ] `from loguru import logger` 가 import 가능한지 (`loguru>=0.7.0` 의존성 존재 확인됨)
- [ ] 새 브랜치 `feature/rehash-policy-logging` 생성

---

## 1. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout -b feature/rehash-policy-logging
```

### Step 2 — `app/core/security.py` 변경

1. `Optional` import 추가 (이미 있음 — 확인만)
2. `_extract_bcrypt_rounds(hashed) -> Optional[int]` 추가
3. `needs_rehash` 의 본문을 `_extract_bcrypt_rounds` 사용 + `<` 비교로 변경
4. docstring 갱신 (업그레이드만 허용, 다운그레이드 차단 명시)

**검증**

```bash
uv run pytest tests/core/test_security.py -v
# 기존 케이스 중 stored=4, configured=12 (legacy) 는 그대로 True 유지.
# 새 케이스가 없는 상태에서 일단 회귀 확인.
```

### Step 3 — `tests/core/test_security.py` 갱신

1. `test_needs_rehash_detects_different_rounds` → `test_needs_rehash_detects_lower_rounds` 이름 변경 + docstring 보강
2. 신규 케이스 `test_needs_rehash_does_not_downgrade`:

```python
def test_needs_rehash_does_not_downgrade():
    """현재 settings 보다 높은 라운드의 해시는 재해시 대상이 아니다 (다운그레이드 차단)."""
    plain = "test_password"
    high_round = bcrypt.hashpw(
        plain.encode("utf-8"),
        bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS + 2),
    ).decode("utf-8")

    assert needs_rehash(high_round) is False
```

**검증**

```bash
uv run pytest tests/core/test_security.py -v
# 기대: 9 PASS (기존 8 → +1)
```

### Step 4 — `app/user/service.py` 변경

1. `from loguru import logger` 추가
2. `from app.core.security import (...)` 에 `_extract_bcrypt_rounds` 추가
3. `authenticate_user::40-51` 의 lazy-rehash 블록을 §5.2 디자인대로 재구성:
   - `stored_rounds = _extract_bcrypt_rounds(user.hashed_password)`
   - `stored < configured` → 재해시 시도, except 에서 `logger.exception(...)`
   - `stored > configured` → `logger.warning(...)`
   - 그 외 (None, 일치) → 무처리

**검증**

```bash
uv run pytest tests/user/ -v
# 기존 케이스 (인증/권한/lazy upgrade) 모두 유지
```

### Step 5 — service 레벨 신규 테스트

기존 user 라우터 테스트가 `lazy upgrade` 케이스를 다루므로 동일 패턴으로 추가. 별도 service 테스트 파일을 새로 만드는 것보다 기존 `tests/user/test_router.py` 에 추가하는 게 응집도 높음.

**케이스 후보**

1. **다운그레이드 감지 로깅** (`test_login_logs_warning_on_downgrade`)
   - settings.BCRYPT_ROUNDS 보다 높은 라운드 (예: configured+2) 로 해시된 사용자를 DB 에 직접 생성
   - `/users/token` 으로 로그인
   - `monkeypatch` 로 `app.user.service.logger.warning` 호출 캡처
   - 인증 성공 (200) + warning 호출됨 + 해시 보존 검증

2. **재해시 실패 시 로깅** (`test_login_logs_exception_on_rehash_failure`)
   - settings.BCRYPT_ROUNDS 보다 낮은 라운드 (예: 4) 로 해시된 사용자
   - `monkeypatch` 로 `repository.update` 가 예외를 던지도록 패치
   - 로그인 → 인증 성공 (200) + `logger.exception` 호출됨 + 기존 해시 보존

```python
def test_login_logs_warning_on_downgrade(monkeypatch, ...):
    warnings = []
    monkeypatch.setattr(
        "app.user.service.logger.warning",
        lambda *args, **kwargs: warnings.append(args),
    )
    # ... high-round 해시로 사용자 직접 생성 → 로그인
    assert any("downgrade detected" in str(args[0]) for args in warnings)
```

**검증**

```bash
uv run pytest tests/user/test_router.py -v
# 기대: 13 → 15 PASS
```

### Step 6 — 전체 회귀

```bash
uv run pytest
# 기대: 41 + 3 = 44 PASS, warning 0
```

### Step 7 — 커밋 + 푸시 + PR

```bash
git add -f docs/'[PRD]라운드_다운그레이드_차단.md' docs/'[PLAN]라운드_다운그레이드_차단.md'
git add app/core/security.py app/user/service.py tests/core/test_security.py tests/user/test_router.py
git commit -m "$(cat <<'EOF'
feat(security): bcrypt 라운드 다운그레이드 차단 + 재해시 운영 로깅

PR #11 의 두 후속을 합쳐서 진행. lazy rehash 정책을 다듬고 운영 가시성을 확보.

- needs_rehash: `!=` → `<` 비교 (업그레이드만 허용, 다운그레이드 차단)
- `_extract_bcrypt_rounds` 내부 헬퍼 추출 (security/service 공용)
- authenticate_user 의 lazy-rehash 블록을 명시 분기로 재구성
  - 재해시 실패 → logger.exception (traceback 포함, 인증은 성공)
  - 다운그레이드 감지 → logger.warning (스킵 사유 기록)
- loguru 첫 프로젝트 사용처 정착 (`from loguru import logger`)
- 테스트 +3: needs_rehash 다운그레이드 차단, service 로깅 두 케이스

외부 API/DB 스키마 불변. 정상 운영 (일치 또는 업그레이드) 케이스는 동작 변화 없음.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push -u origin feature/rehash-policy-logging
gh pr create --title "feat(security): bcrypt 라운드 다운그레이드 차단 + 재해시 운영 로깅" --body "..."
```

---

## 2. 산출물 체크리스트

| 산출물 | 위치 | 상태 |
| --- | --- | --- |
| PRD | `docs/[PRD]라운드_다운그레이드_차단.md` | ✅ |
| PLAN | `docs/[PLAN]라운드_다운그레이드_차단.md` | ✅ (본 파일) |
| security 헬퍼 + needs_rehash 변경 | `app/core/security.py` | ⬜ |
| service lazy-rehash 분기 재구성 + loguru | `app/user/service.py` | ⬜ |
| needs_rehash 회귀 가드 (+1) | `tests/core/test_security.py` | ⬜ |
| service 로깅 회귀 가드 (+2) | `tests/user/test_router.py` | ⬜ |

---

## 3. 신규 테스트 케이스 매트릭스

| # | 위치 | 케이스 | 검증 |
| --- | --- | --- | --- |
| 1 | `tests/core/test_security.py::test_needs_rehash_does_not_downgrade` | stored=configured+2 인 해시 | `needs_rehash → False` |
| 2 | `tests/user/test_router.py::test_login_logs_warning_on_downgrade` | high-round 해시 사용자 로그인 | 인증 성공 + `logger.warning` 호출 + 해시 보존 |
| 3 | `tests/user/test_router.py::test_login_logs_exception_on_rehash_failure` | low-round 해시 + repository.update 예외 패치 | 인증 성공 + `logger.exception` 호출 + 기존 해시 보존 |

추가로 기존 `test_needs_rehash_detects_different_rounds` → `test_needs_rehash_detects_lower_rounds` 이름 정정 (의미 명확화).

---

## 4. 회귀 방지

| 회귀 시나리오 | 가드 |
| --- | --- |
| 다운그레이드 시 재해시 발생 | 신규 케이스 #1, #2 |
| 재해시 실패가 조용히 무시됨 | 신규 케이스 #3 |
| 인증 흐름 자체가 깨짐 (재해시 실패가 401 유발) | 신규 케이스 #3 가 200 검증 |
| `_extract_bcrypt_rounds` 파싱 실패 시 예외 전파 | 기존 `test_needs_rehash_returns_false_for_malformed_hash` |
| loguru import 실패 (의존성 누락) | `from loguru import logger` 자체가 collection 단계에서 실패하므로 collect 시 즉시 잡힘 |

---

## 5. 롤백

- `app/core/security.py`: `_extract_bcrypt_rounds` 제거, `needs_rehash` 의 `<` → `!=` 복원
- `app/user/service.py`: lazy-rehash 블록을 PR #11 형태로 복원, loguru import 제거
- 또는 단일 머지 커밋 revert

```bash
git revert <merge-commit-sha>
```

---

## 6. 후속 작업 후보

- loguru sink/포맷 (JSON, file, Sentry 등) 설정 — 별도 운영 인프라
- audit log (DB 기록) — 추적성 마스터 목록 항목과 합쳐서
- 다운그레이드 감지 시 시작 시 한 번만 알리기 (per-process 디듑) — 양 폭증 시 검토
- `_extract_bcrypt_rounds` 외부 API 승격 (호출처가 늘어나면)

---

## 7. 참고

- `docs/[PRD]라운드_다운그레이드_차단.md`
- `docs/[PRD]점진적_비밀번호_재해시.md`
- `app/core/security.py`, `app/user/service.py`
- loguru docs
