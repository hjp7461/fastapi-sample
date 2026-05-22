# Pydantic `.dict()` → `.model_dump()` 마이그레이션 구현 Plan

| 항목         | 내용                                                                                   |
| ------------ | -------------------------------------------------------------------------------------- |
| 작성일       | 2026-05-22                                                                             |
| 연관 PRD     | [`[PRD]Pydantic_model_dump_마이그레이션.md`](./[PRD]Pydantic_model_dump_마이그레이션.md) |
| 상태         | 제안 (Draft)                                                                           |
| 추정 작업량  | 약 20 분 (구현 + 검증)                                                                  |
| 변경 규모    | 4 줄 (라우터 2 파일)                                                                   |

> 본 작업은 1:1 메서드 대체라 단계가 매우 짧다.

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 기준 최신 상태에서 `feature/pydantic-model-dump` 브랜치 생성
- [ ] `uv run pytest` 현재 30/30 PASS 확인
- [ ] 변경 전 `PydanticDeprecatedSince20` 경고 발생 카운트 측정 (기준선)

```bash
uv run pytest 2>&1 | grep -c "PydanticDeprecatedSince20"
# 기준선 기록
```

---

## 1. 작업 분해

### Step 1. `app/user/router.py` — 2 곳 변경

```python
# Line 28 (create_user 내부)
# Before
user = await user_service.create_user(user_in.dict())
# After
user = await user_service.create_user(user_in.model_dump())

# Line 53 (update_current_user 내부)
# Before
user = await user_service.update_user(current_user.id, user_in.dict(exclude_unset=True))
# After
user = await user_service.update_user(current_user.id, user_in.model_dump(exclude_unset=True))
```

**검증**

```bash
uv run pytest tests/user/test_router.py::test_create_user tests/user/test_router.py::test_update_current_user -v --tb=short
```

2 케이스 PASS.

---

### Step 2. `app/product/router.py` — 2 곳 변경

```python
# Line 30 (create_product 내부)
# Before
product = await product_service.create_product(product_in.dict())
# After
product = await product_service.create_product(product_in.model_dump())

# Line 65 (update_product 내부)
# Before
return await product_service.update_product(
    product_id,
    product_in.dict(exclude_unset=True)
)
# After
return await product_service.update_product(
    product_id,
    product_in.model_dump(exclude_unset=True)
)
```

**검증**

```bash
uv run pytest tests/product/test_router.py::test_create_product_as_admin tests/product/test_router.py::test_update_product_as_admin -v --tb=short
```

2 케이스 PASS.

---

### Step 3. 전체 회귀 검증 + 경고 0 확인

```bash
uv run pytest -v
```

30/30 PASS 확인.

```bash
uv run pytest 2>&1 | grep -c "PydanticDeprecatedSince20"
# → 0 (이전 카운트보다 감소)
```

```bash
grep -rn "\.dict(" app/ --include="*.py"
# → 출력 없음 (라우터에서 .dict 호출 0건)
```

---

## 2. 산출물 체크리스트

- [ ] `app/user/router.py` — `.dict()` 2건 → `.model_dump()`
- [ ] `app/product/router.py` — `.dict()` 2건 → `.model_dump()`
- [ ] `uv run pytest` 30/30 PASS 유지
- [ ] `grep -c "PydanticDeprecatedSince20"` 결과 0
- [ ] `grep -rn "\.dict("` 결과 0건 (app/ 하위)

---

## 3. 테스트 케이스 (완료 판정 기준)

본 PR 은 신규 테스트를 추가하지 않는다 (PRD §6). 다음 기존 테스트가 변경된 라우터 경로를 자동으로 커버.

| #   | 테스트                              | 검증 경로                                  |
| --- | ----------------------------------- | ------------------------------------------ |
| 1   | `test_create_user`                  | `user_in.model_dump()`                     |
| 2   | `test_update_current_user`          | `user_in.model_dump(exclude_unset=True)`   |
| 3   | `test_create_product_as_admin`      | `product_in.model_dump()`                  |
| 4   | `test_update_product_as_admin`      | `product_in.model_dump(exclude_unset=True)` |
| -   | 기타 26 케이스                      | 통합 회귀                                  |

---

## 4. 회귀 방지 체크리스트

PR 머지 전 모두 확인.

- [ ] `uv run pytest` **30/30 PASS**
- [ ] 변경 전 발생하던 `PydanticDeprecatedSince20` 경고가 **0 건** 으로 감소
- [ ] `grep -rn "\.dict(" app/` 결과 없음 (Pydantic 모델 호출 0건)
- [ ] `git diff main` 결과가 4 줄 변경만 보임 (다른 사이드이펙트 없음)
- [ ] 인증 흐름 회귀 없음 (`POST /users/`, `POST /users/token`, `GET /users/me`)
- [ ] 상품 관리 흐름 회귀 없음 (`POST /products/`, `PUT /products/{id}`)

---

## 5. 롤백 전략

- 본 작업은 라우터 2 파일 × 2 줄 = 4 줄 변경.
- 별도 브랜치 (`feature/pydantic-model-dump`) 에서 작업. 문제 시 `git checkout main` 으로 원복.
- 단일 파일 단독 revert 가능 — 두 라우터 사이에 의존성 없음.

---

## 6. 후속 작업 (별도 이슈 권장)

| #   | 항목                                                                          | 권장 처리                                                   |
| --- | ----------------------------------------------------------------------------- | ----------------------------------------------------------- |
| 1   | Pydantic v3 으로 업그레이드 (v3 출시 후)                                       | 별도 PR — 다른 변경점 (Validator 시그니처, BaseModel 동작 등) |
| 2   | `model_dump(mode="json")` 활용 (datetime/Decimal 직렬화 일관성)               | 필요해질 때 도입                                            |
| 3   | 다른 deprecation warning 정리 (`datetime.utcnow()`, `pytest.ini verbosity`)   | 별도 PR — 본 PR 의 후속 청소 작업                            |

---

## 7. 참고

- 관련 PRD: [`[PRD]Pydantic_model_dump_마이그레이션.md`](./[PRD]Pydantic_model_dump_마이그레이션.md)
- 핵심 코드:
  - `app/user/router.py:28, 53` — 수정 대상
  - `app/product/router.py:30, 65` — 수정 대상
- Pydantic V2 Migration Guide: https://docs.pydantic.dev/latest/migration/
