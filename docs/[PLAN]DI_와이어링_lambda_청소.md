# [PLAN] DI 와이어링 lambda 청소 (Provide + @inject 표준 패턴)

| 항목 | 내용 |
| --- | --- |
| 연관 PRD | `docs/[PRD]DI_와이어링_lambda_청소.md` |
| 브랜치 | `feature/di-wiring-cleanup` |
| 추정 작업량 | 소~중 (1~1.5 시간) |
| 채택 전략 | 12곳 lambda → `Depends(get_xxx_service)` named helper, 기존 통합 테스트가 회귀 가드 |
| 패턴 폐기 | `Provide + @inject` 는 dependency-injector 4.46.0 + FastAPI 호환성 한계로 폐기 (PRD §2.1) |

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 최신, 55 PASS 기준선 확인
- [ ] `Container.wiring_config.packages` 가 `app.api`, `app.user`, `app.product` 포함 확인 (이미 OK)
- [ ] 새 브랜치 `feature/di-wiring-cleanup` 생성

---

## 1. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout -b feature/di-wiring-cleanup
```

### Step 2 — `app/api/dependencies.py` 1곳 교체

```python
from dependency_injector.wiring import inject, Provide

@inject
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_service: UserService = Depends(Provide[Container.user_service]),
) -> User:
    ...
```

**검증**

```bash
uv run pytest tests/user/test_router.py -v
# 기존 인증 케이스가 PASS 유지하는지 확인
```

### Step 3 — `app/user/router.py` 5곳 교체

각 라우터 함수에 `@inject` 데코레이터 + `Provide[Container.user_service]` 적용.
함수: `create_user`, `update_current_user`, `login_for_access_token`, `get_user_by_id`, `list_users`.

`get_current_user_info` 는 user_service 를 사용하지 않으므로 `@inject` 불요.

**검증**

```bash
uv run pytest tests/user/test_router.py -v
# 기대: 18 PASS 유지
```

### Step 4 — `app/product/router.py` 6곳 교체

각 라우터 함수에 `@inject` + `Provide[Container.product_service]` 적용.
함수: `create_product`, `get_product_by_id`, `update_product`, `delete_product`, `list_products`, `update_inventory`.

**검증**

```bash
uv run pytest tests/product/test_router.py -v
# 기대: 13 PASS 유지
```

### Step 5 — grep 가드 + 전체 회귀

```bash
grep -rn "Depends(lambda" app/
# 기대: 출력 0건

uv run pytest
# 기대: 55 PASS (변화 없음 — 신규 케이스 0)
```

### Step 6 — 커밋 + 푸시 + PR

```bash
git add -f docs/'[PRD]DI_와이어링_lambda_청소.md' docs/'[PLAN]DI_와이어링_lambda_청소.md'
git add app/api/dependencies.py app/user/router.py app/product/router.py
git commit ...
git push -u origin feature/di-wiring-cleanup
gh pr create ...
```

---

## 2. 산출물 체크리스트

| 산출물 | 위치 | 상태 |
| --- | --- | --- |
| PRD | `docs/[PRD]DI_와이어링_lambda_청소.md` | ✅ |
| PLAN | `docs/[PLAN]DI_와이어링_lambda_청소.md` | ✅ |
| dependencies.py 1곳 | `app/api/dependencies.py` | ⬜ |
| user router 5곳 | `app/user/router.py` | ⬜ |
| product router 6곳 | `app/product/router.py` | ⬜ |

---

## 3. 회귀 방지

| 회귀 시나리오 | 가드 |
| --- | --- |
| `@inject` 미적용으로 Provide marker 가 그대로 전달 → 라우터 500 | 통합 테스트 55건이 즉시 검출 |
| 데코레이터 순서 오류로 FastAPI 가 잘못된 시그니처 분석 → 401/422 | 인증/CRUD 통합 케이스가 즉시 검출 |
| 테스트 override 가 wiring 과 충돌 | conftest 의 `container_override` 가 모든 케이스 setup 에서 적용되므로 첫 케이스부터 검출 |
| `Provide[Container.xxx]` 의 xxx 이름 오타 | wiring 단계에서 `AttributeError` — 첫 케이스 collect 단계에서 즉시 실패 |
| 새 라우터 추가 시 lambda 패턴 재유입 | PR description / 후속 관행 — 자동 가드는 없음 (별도 lint rule 후속 가능) |

---

## 4. 롤백

단일 머지 revert. 동작 변경 없으므로 안전.

---

## 5. 후속 작업 후보

- lambda 패턴 재유입 방지용 lint/CI 검사 (선택)
- Container 의 Provider 타입 명시 (`providers.Factory[UserService]` 같은 generic 타입) — Python typing 한계로 우선순위 낮음
- 다른 의존성 함수 (`get_current_active_admin`, `get_self_or_admin`) 검토 — 현재는 user 객체만 다루어 직접 의존성 없음. 별도 후속 불요.

---

## 6. 참고

- PRD: `docs/[PRD]DI_와이어링_lambda_청소.md`
- `app/di/containers.py` (wiring_config)
- dependency-injector wiring docs
