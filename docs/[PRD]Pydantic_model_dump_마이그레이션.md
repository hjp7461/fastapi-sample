# Pydantic `.dict()` → `.model_dump()` 마이그레이션 PRD

| 항목       | 내용                                                                                   |
| ---------- | -------------------------------------------------------------------------------------- |
| 작성일     | 2026-05-22                                                                             |
| 작성자     | conner                                                                                 |
| 상태       | 제안 (Draft)                                                                           |
| 도메인     | API 계층 (User / Product router)                                                        |
| 대상 범위  | `app/user/router.py`, `app/product/router.py` 의 `.dict()` 호출 4곳                    |
| 관련 발견  | PR #1 ~ #5 마다 누적되어 보이던 `PydanticDeprecatedSince20` 경고                       |

---

## 1. 배경

### 1.1 Pydantic v1 → v2 메서드 변경

Pydantic v2 부터 모델 직렬화/검증 메서드의 이름이 변경되었다. 본 프로젝트는 이미 `pydantic>=2.0.0` 을 사용 중이지만, v1 시절의 `.dict()` 호출이 그대로 남아있다. v2 는 호환을 위해 `.dict()` 를 alias 로 유지하지만 **Pydantic v3 에서 제거 예정** 이다.

| v1 메서드          | v2 메서드            | 본 프로젝트 사용 |
| ------------------ | -------------------- | ---------------- |
| `Model.dict()`     | `Model.model_dump()` | **4곳**          |
| `Model.json()`     | `Model.model_dump_json()` | 0건         |
| `Model.parse_obj()` | `Model.model_validate()` | 0건         |
| `Model.parse_raw()` | `Model.model_validate_json()` | 0건     |
| `Model.copy()`     | `Model.model_copy()` | 0건              |
| `class Config:`    | `model_config = {...}` | 이미 v2 스타일 사용 중 (`UserResponse`) |

### 1.2 사용 위치 (정확히 4곳)

```python
# app/user/router.py:28 (create_user)
user = await user_service.create_user(user_in.dict())

# app/user/router.py:53 (update_current_user)
user = await user_service.update_user(current_user.id, user_in.dict(exclude_unset=True))

# app/product/router.py:30 (create_product)
product = await product_service.create_product(product_in.dict())

# app/product/router.py:65 (update_product)
return await product_service.update_product(
    product_id,
    product_in.dict(exclude_unset=True)
)
```

### 1.3 현재 발생 중인 경고

테스트 실행 시 다음 경고가 매번 발생.

```
PydanticDeprecatedSince20: The `dict` method is deprecated; use `model_dump`
instead. Deprecated in Pydantic V2.0 to be removed in V3.0.
```

위 4 위치에서 1회씩 발생 → 라우터 호출되는 모든 테스트에서 누적되어 출력.

---

## 2. 목적

- Pydantic v3 호환성 사전 확보 (`.dict()` 가 제거되어도 동작).
- 테스트 실행 시 매번 누적되는 `PydanticDeprecatedSince20` 경고를 제거.
- 코드 일관성 — 이미 일부는 v2 스타일 (`model_config`) 을 쓰고 있는데, 직렬화만 v1 스타일이 남아있는 불일치 해소.

### 비목적

- 다른 Pydantic v1 → v2 메서드 마이그레이션 — 본 프로젝트에는 해당 사용처가 없음.
- 스키마 자체 (`UserCreate`, `ProductCreate` 등) 의 구조/필드 변경.
- `exclude_unset` 외 다른 직렬화 옵션 (`exclude_none`, `by_alias` 등) 적용 검토.
- `model_dump` 의 동작 변경에 따른 새 기능 활용 (예: `mode="json"`).
- 서비스/리포지토리/도메인 계층 변경 — 라우터 → 서비스 인터페이스 (`dict[str, Any]`) 유지.

---

## 3. 성공 기준

| 지표                                                              | 목표값       |
| ----------------------------------------------------------------- | ------------ |
| `grep -r "\.dict(" app/` (Pydantic 모델 호출)                     | 0건          |
| 라우터 4 곳의 `.dict()` → `.model_dump()` 대체                    | 4건          |
| `PydanticDeprecatedSince20` 경고                                  | 0건          |
| 기존 회귀 테스트                                                  | 30/30 PASS 유지 |
| `model_dump` 의 반환 동작 동일성 (key/value 매핑)                 | 확인 필요    |

---

## 4. 설계

### 4.1 1:1 메서드 대체

`Model.dict()` ↔ `Model.model_dump()` 는 **인자/반환값이 동일**.

```python
# Before
user_in.dict()
user_in.dict(exclude_unset=True)

# After
user_in.model_dump()
user_in.model_dump(exclude_unset=True)
```

> Pydantic 공식 문서: `model_dump` 는 v1 의 `.dict()` 와 같은 시그니처를 가지며, 추가로 `mode` 옵션 (기본 `"python"`) 이 있다. 본 PR 은 기본 동작만 사용하므로 의미 변화 없음.

### 4.2 호출자 인터페이스

서비스 메서드 (`UserService.create_user`, `ProductService.create_product` 등) 는 `dict[str, Any]` 를 받는다. `model_dump()` 의 반환 타입도 동일한 `dict[str, Any]` 라서 인터페이스 호환.

```python
# UserService (변경 없음)
async def create_user(self, user_data: Dict[str, Any]) -> User:
    ...
```

### 4.3 행동 차이의 부재

`model_dump()` 와 `dict()` 는 본 프로젝트에서 사용 중인 옵션 (`exclude_unset`) 에 대해 **완전히 동일한 결과** 를 반환한다. Pydantic v2 의 [공식 마이그레이션 가이드](https://errors.pydantic.dev/2.11/migration/) 에서 명시.

따라서:

- 기존 테스트의 응답 검증 (`data["email"] == ...`) 모두 통과해야 함
- repository 가 받는 dict 의 key/value 구조 동일

---

## 5. 영향 받는 파일

| 파일                        | 변경 종류 | 변경량 |
| --------------------------- | --------- | ------ |
| `app/user/router.py`        | 직접 변경 | 2 줄   |
| `app/product/router.py`     | 직접 변경 | 2 줄   |

> 호출자 (`service`/`repository`) 와 테스트 시드는 변경 없음.

---

## 6. 테스트 영향

본 변경은 **외부 동작이 동일** 하므로 신규 테스트가 불요. 기존 회귀 테스트가 자동 검증.

| 기존 테스트                       | 검증 경로                                    |
| --------------------------------- | -------------------------------------------- |
| `test_create_user`                | `user_in.dict()` → `model_dump()`            |
| `test_update_current_user`        | `user_in.dict(exclude_unset=True)`           |
| `test_create_product_as_admin`    | `product_in.dict()`                          |
| `test_update_product_as_admin`    | `product_in.dict(exclude_unset=True)`        |

추가 검증 (선택):

```bash
# 경고 출력이 0건임을 자동 검증
uv run pytest 2>&1 | grep -c "PydanticDeprecatedSince20"
# → 0
```

---

## 7. 리스크 및 미해결 이슈

| #   | 항목                                                                            | 대응                                                                       |
| --- | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| 1   | `model_dump` 와 `dict` 의 미묘한 동작 차이 (특히 `Enum` 필드, `datetime` 필드)   | 본 PR 의 라우터 호출은 `exclude_unset` 외 옵션 없음. 기본 동작 (`mode="python"`) 은 v1 과 동일 |
| 2   | Pydantic v3 으로 업그레이드 시 또 다른 변경                                     | 본 PR 은 v3 으로의 사전 호환. 추가 마이그레이션은 v3 출시 후 별도 이슈        |
| 3   | 다른 v1 잔존 패턴 발견 시                                                       | 본 PRD §1.1 매트릭스에 따르면 본 프로젝트에는 없음. PR 머지 후 재확인 권장   |

### 결정 사항 (확정)

- [x] 메서드 대체: `.dict()` → `.model_dump()` (1:1)
- [x] 옵션 유지: `exclude_unset=True` 그대로
- [x] 신규 테스트: **불요** (기존 회귀가 충분)
- [x] 다른 v1 메서드 마이그레이션은 사용처 없음 — 본 PR 범위 외

---

## 8. 참고

- Pydantic V2 Migration Guide: https://docs.pydantic.dev/latest/migration/
- `BaseModel.model_dump` 문서: https://docs.pydantic.dev/latest/api/base_model/#pydantic.BaseModel.model_dump
- 코드 위치:
  - `app/user/router.py:28, 53`
  - `app/product/router.py:30, 65`
- 선례: PR #1 ~ #5 (warning 정리는 모두 후속으로 분리되어 누적)
