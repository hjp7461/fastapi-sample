# [PLAN] 마스킹 정책 환경 변수화 — dev 해제 옵션

> PRD: `docs/[PRD]마스킹_정책_환경변수화.md`
> 브랜치: `feature/user-admin-email-masking-toggle`
> 분류: 운영 정책 / 환경 설정

---

## 1. 사전 점검

- [ ] `git status` → `main`, clean
- [ ] `git log --oneline -3` 최상단이 PR #21 머지 (`cd33c68`)
- [ ] `uv run pytest 2>&1 | tail -1` → `60 passed`
- [ ] `gh pr list --state open` → 비어 있음
- [ ] 변경 대상 4 파일 위치 확인:
  - `app/core/config.py` (Settings)
  - `app/user/schemas.py` (build_admin_view)
  - `tests/user/test_router.py` (회귀 가드 +2)
  - `app/user/masking.py` (변경 없음 — 호출처만 토글)

---

## 2. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout -b feature/user-admin-email-masking-toggle
```

### Step 2 — `Settings` 에 토글 추가

`app/core/config.py`:

- 기존 패턴 (BCRYPT_ROUNDS, DB_ECHO) 과 동일하게 `os.getenv` 기본값으로 추가
- `# 응답 PII 정책` 주석 단락 신설 (BCRYPT 옆이 아니라 DB_ECHO 아래쪽)

```python
# 응답 PII 정책
USER_ADMIN_EMAIL_MASKING: bool = os.getenv(
    "USER_ADMIN_EMAIL_MASKING", "true"
).lower() == "true"
```

검증: `python -c "from app.core.config import settings; print(settings.USER_ADMIN_EMAIL_MASKING)"` → `True`

### Step 3 — `build_admin_view` 토글 분기

`app/user/schemas.py`:

- 파일 상단에 `from app.core.config import settings` 추가 (이미 mask_email 만 import 중)
- `build_admin_view()` 내부 email 인자 분기:
  ```python
  email=mask_email(user.email) if settings.USER_ADMIN_EMAIL_MASKING else user.email,
  ```
- `UserAdminView` docstring 갱신: "이메일은 기본 마스킹 (`USER_ADMIN_EMAIL_MASKING=false` 면 raw)"
- `build_admin_view` docstring 갱신: "마스킹 토글은 settings 참조"

### Step 4 — 회귀 가드 테스트 +1

`tests/user/test_router.py`:

- 기존 `test_get_other_user_as_admin_returns_masked_view` 가 default 마스킹 케이스를 완전 커버 (`assert "***" in data["email"]`) → 중복 추가 회피.
- 신규 1건만 추가: `test_admin_view_email_raw_when_masking_disabled`
  - `monkeypatch.setattr(settings, "USER_ADMIN_EMAIL_MASKING", False)` 후 `GET /users/{타인}` → 응답 email 이 raw 검증
  - 기존 `test_get_other_user_as_admin_returns_masked_view` 옆에 배치.

### Step 5 — 회귀 (`uv run pytest`)

```bash
/usr/local/bin/mise exec -- uv run pytest 2>&1 | tail -5
```

기대: **61 passed** (60 + 1 신규), warning 0건.

### Step 6 — ruff check / format --check 통과

```bash
/usr/local/bin/mise exec -- uv run ruff check . 2>&1 | tail -2
/usr/local/bin/mise exec -- uv run ruff format --check . 2>&1 | tail -2
```

기대: 둘 다 종료 코드 0. (PR #21 의 lint clean baseline 유지.)

### Step 7 — 커밋

단일 커밋 (4 파일만 변경되고 응집도 높음):

```
feat(user): UserAdminView 의 email 마스킹을 환경 변수로 토글 가능하게 (dev 해제 옵션)

- Settings 에 USER_ADMIN_EMAIL_MASKING 추가 (default True, 운영 안전)
- build_admin_view 가 토글 참조 — True 면 mask_email(), False 면 raw
- 회귀 가드 +1: monkeypatch 해제 시 raw email 검증 (default 마스킹은 기존 테스트 커버)

PR #15 §3 비목적 + §8 결정 사항 "별도 후속에서 옵션화 가능" 의 후속.
운영 환경 무변동 (default True). dev 에서 .env 로 명시 해제 가능.
범위는 UserAdminView 의 email 마스킹만 — first/last_name 제외 정책은
스키마 자체이므로 별도 후속.
```

### Step 8 — 푸시 + PR

```bash
git push -u origin feature/user-admin-email-masking-toggle
```

PR title 예:
```
feat(user): UserAdminView email 마스킹 환경 변수 토글 (dev 해제 옵션)
```

PR description: 배경/목적 (PRD §1-2), 변경 매트릭스 (PRD §5), 회귀 가드 결과, 비목적/후속.

---

## 3. 산출물 체크리스트

- [ ] `app/core/config.py`: `USER_ADMIN_EMAIL_MASKING: bool = True` 추가
- [ ] `app/user/schemas.py`: `build_admin_view` 분기 + docstring 갱신
- [ ] `tests/user/test_router.py`: 회귀 가드 +1 (default 마스킹은 기존 테스트 커버)
- [ ] `uv run pytest` → 61 passed (60 → 61)
- [ ] `uv run ruff check .` 종료 코드 0
- [ ] `uv run ruff format --check .` 종료 코드 0
- [ ] 커밋 (한글 메시지 + Co-Authored-By 푸터)
- [ ] PR description 에 변경 매트릭스 + 검증 결과

---

## 4. 테스트 케이스 (신규 1건)

| # | 이름 | 시나리오 | 기대 |
| --- | --- | --- | --- |
| 1 | `test_admin_view_email_raw_when_masking_disabled` | `monkeypatch.setattr(settings, "USER_ADMIN_EMAIL_MASKING", False)`, admin 이 타인 조회 | `response.json()["email"] == test_user["email"]` (raw) |

기존 회귀 가드:
- default 마스킹: `test_get_other_user_as_admin_returns_masked_view` (이미 `"***" in email` 검증)
- 본인 조회: `test_get_current_user_returns_full_pii` 등 (토글 무관, UserResponse 사용)

---

## 5. 회귀 방지

| 검증 | 명령 | 기대 |
| --- | --- | --- |
| 전체 회귀 | `uv run pytest` | 61 passed, 0 warning |
| 린트 | `uv run ruff check .` | 종료 코드 0 |
| 포맷 | `uv run ruff format --check .` | 종료 코드 0 |
| 토글 default | 신규 #1 | 마스킹된 응답 |
| 토글 해제 | 신규 #2 | raw 응답 |

---

## 6. 롤백

- 단일 PR `revert`. 4 파일만 영향, settings 신규 필드라 deprecation 없음.
- 환경 변수 미사용 환경에서는 기본값 True 라 영향 없음 (롤백 안 해도 운영 안전).

---

## 7. 후속 (PRD §7 그대로)

- 마스킹 헬퍼 `app/user/masking.py` → `app/core/masking.py` 승격 (다른 도메인 PII 마스킹 시점)
- `UserAdminView` 의 first_name / last_name 토글 (정책 검토 후 필요 시)
- RUNBOOK §환경 변수 단락 보강 (BCRYPT_ROUNDS 옆에 USER_ADMIN_EMAIL_MASKING 추가) — 본 PR 범위 안에 포함할지 별도 후속할지 진행 중 판단

---

## 8. 참고

- PRD: `docs/[PRD]마스킹_정책_환경변수화.md`
- PR #15 PRD/PLAN (도입 컨텍스트)
- `app/core/config.py` (Settings 패턴)
- `app/user/schemas.py` (build_admin_view)
- `app/user/masking.py` (mask_email)
- `tests/user/test_router.py` (기존 마스킹 매트릭스)
