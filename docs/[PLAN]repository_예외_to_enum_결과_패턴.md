# [PLAN] repository 예외 → enum 결과 패턴 (update_inventory)

| 항목 | 내용 |
| --- | --- |
| 연관 PRD | `docs/[PRD]repository_예외_to_enum_결과_패턴.md` |
| 브랜치 | `feature/repository-result-enum` |
| 추정 작업량 | 중 (1.5~2 시간) |
| 채택 전략 | InventoryUpdateOutcome enum + InventoryUpdateResult dataclass + service match 분기 + repository 단위 테스트 신규 |

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 최신, 52 PASS 기준선 확인
- [ ] `tests/conftest.py` 의 `db_session` fixture 가 repository 직접 사용에도 적합한지 확인 (기존 user 테스트가 db_session 사용 → OK)
- [ ] `update_inventory` 호출처 grep 으로 확인 — service.py 하나만일 것

---

## 1. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout -b feature/repository-result-enum
```

### Step 2 — `app/product/repository.py` — enum + dataclass 추가

- `InventoryUpdateOutcome` enum
- `InventoryUpdateResult` frozen dataclass

### Step 3 — `update_inventory` 시그니처 재작성

- 반환 타입: `InventoryUpdateResult`
- `BusinessLogicException` import 제거 + raise 제거
- 모든 분기를 `InventoryUpdateResult(...)` 반환으로

### Step 4 — `app/product/service.py::update_inventory` 분기 재구성

```python
match result.outcome:
    case InventoryUpdateOutcome.OK:
        assert result.product is not None
        return result.product
    case InventoryUpdateOutcome.NOT_FOUND:
        raise NotFoundException(...)
    case InventoryUpdateOutcome.INSUFFICIENT:
        raise BusinessLogicException(...)
```

### Step 5 — repository 단위 테스트 신규 (`tests/product/test_repository.py`)

PRD §5.5 의 3 케이스 그대로.

**검증**

```bash
uv run pytest tests/product/test_repository.py -v
# 기대: 3 PASS
```

### Step 6 — 기존 라우터 테스트 회귀 확인

```bash
uv run pytest tests/product/test_router.py -v
# 기대: 13 PASS (외부 API 동일)
```

### Step 7 — 전체 회귀

```bash
uv run pytest
# 기대: 52 + 3 = 55 PASS, warning 0
```

### Step 8 — 커밋 + 푸시 + PR

```bash
git add -f docs/'[PRD]repository_예외_to_enum_결과_패턴.md' docs/'[PLAN]repository_예외_to_enum_결과_패턴.md'
git add app/product/repository.py app/product/service.py tests/product/test_repository.py
git commit ...
git push -u origin feature/repository-result-enum
gh pr create ...
```

---

## 2. 산출물 체크리스트

| 산출물 | 위치 | 상태 |
| --- | --- | --- |
| PRD | `docs/[PRD]repository_예외_to_enum_결과_패턴.md` | ✅ |
| PLAN | `docs/[PLAN]repository_예외_to_enum_결과_패턴.md` | ✅ |
| enum + dataclass + update_inventory | `app/product/repository.py` | ⬜ |
| service match 분기 | `app/product/service.py` | ⬜ |
| repository 단위 테스트 +3 | `tests/product/test_repository.py` | ⬜ |

---

## 3. 신규 테스트 케이스

| # | 위치 | 케이스 |
| --- | --- | --- |
| 1 | `tests/product/test_repository.py::test_update_inventory_returns_ok_on_success` | 정상 갱신 → outcome.OK + product 반영 |
| 2 | `tests/product/test_repository.py::test_update_inventory_returns_not_found_for_missing_id` | 없는 id → outcome.NOT_FOUND + product None |
| 3 | `tests/product/test_repository.py::test_update_inventory_returns_insufficient_when_negative` | 음수 발생 → outcome.INSUFFICIENT + 재고 보존 |

---

## 4. 회귀 방지

| 회귀 시나리오 | 가드 |
| --- | --- |
| service 가 outcome 분기를 누락 → 라우터에 None 전파 | 신규 케이스 + 기존 라우터 통합 (200/404/400 응답 검증) |
| repository 가 다시 도메인 예외에 의존 | grep으로 BusinessLogicException import 부재 확인 + 라우터 통합 테스트 |
| 동시성 케이스 (재고 0 까지 차감) 회귀 | 기존 `tests/product/test_router.py` 동시 차감 케이스 |
| dataclass 가 None product 인데 service 가 사용 시도 | `assert result.product is not None` + match 의 OK 분기에만 사용 |

---

## 5. 롤백

단일 머지 revert. 외부 API 불변이므로 안전.

---

## 6. 후속 작업 후보

- user 도메인 repository 메서드들의 결과 패턴 적용 검토 (`update`, `delete` 등 — 현재는 `Optional[T]` 로 명시적이라 우선순위 낮음)
- 도메인 예외 패키지 재설계 — exception 계층 정리

---

## 7. 참고

- PRD: `docs/[PRD]repository_예외_to_enum_결과_패턴.md`
- `app/product/repository.py`, `app/product/service.py`
- `tests/conftest.py` (db_session fixture)
