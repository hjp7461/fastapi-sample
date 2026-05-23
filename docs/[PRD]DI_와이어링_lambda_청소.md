# [PRD] DI 와이어링 lambda 청소 (Provide + @inject 표준 패턴)

| 항목 | 내용 |
| --- | --- |
| 상태 | 제안 (Draft) |
| 작성일 | 2026-05-23 |
| 출처 | PR #12 §6 후속, [HANDOFF] §6 마스터 목록 |
| 분류 | 구조 (DI 와이어링 표준화) |
| 추정 작업량 | 소~중 (1~1.5 시간, 12곳 패턴 교체 + import + 회귀) |

---

## 1. 배경

### 1.1 현재 패턴

라우터/의존성 함수에서 서비스를 주입할 때 다음 lambda 패턴이 12곳 반복된다.

```python
user_service: UserService = Depends(lambda: Container.user_service())
product_service: ProductService = Depends(lambda: Container.product_service())
```

- `app/user/router.py` — 5곳
- `app/product/router.py` — 6곳
- `app/api/dependencies.py` — 1곳

### 1.2 문제

1. **dependency-injector 의 표준 패턴이 아님** — 라이브러리는 `Provide[Container.xxx]` + `@inject` 데코레이터 패턴을 제공한다. 현재는 lambda 로 우회.
2. **반복 보일러플레이트** — 같은 lambda 가 12번 반복. 새 라우터 추가 시 패턴이 누적.
3. **wiring 미활용** — `containers.py` 에 이미 `WiringConfiguration(packages=["app.api", "app.user", "app.product"])` 가 선언되어 있어 모든 준비가 끝났는데도 정작 wiring 의 핵심 기능 (`Provide[...]`) 을 사용하지 않음.
4. **타입 추론 실패** — `Depends(lambda: ...)` 는 IDE/타입체커가 반환 타입을 추론하기 어려움. `Provide[Container.user_service]` 는 컨테이너 정의를 따라가 타입을 알 수 있음.

### 1.3 본 PR 의 위치

[HANDOFF] §6: "DI 와이어링 lambda 청소 — PR #12 §6 후속, 구조, 소". 작업량은 작지만 코드베이스 전반에 분포된 패턴이므로 일관 청소 가치가 있다.

---

## 2. 목적

1. lambda DI 패턴 12곳을 모두 **named helper 함수** 로 교체 — `app/di/providers.py` 에 `get_user_service()`, `get_product_service()` 등 헬퍼 정의 후 `Depends(get_user_service)` 형태로 사용.
2. 매 호출 시 `Container.xxx()` 를 평가하는 lambda 의 의미는 그대로 유지하되, 명명된 함수로 가독성/타입 추론 개선.
3. 새 라우터/의존성 추가 시 일관된 패턴이 보이도록 한다.
4. 외부 동작 / 응답 / DB 모두 불변.

### 2.1 표준 `Provide + @inject` 패턴 폐기 사유

초기 PRD 안에서는 dependency-injector 의 `@inject + Provide[Container.xxx]` 표준 패턴을 채택할 계획이었으나, 구현 시도 결과 다음 호환성 문제가 확인되어 폐기한다.

- dependency-injector **4.46.0** 의 `@inject` 데코레이터는 함수 객체를 수정하지 않음 (4.x 의 디자인).
- `Provide[Container.xxx]` marker 는 callable 이지만 호출 시 자기 자신을 반환 (실제 값 변환은 wiring 된 함수가 직접 호출될 때만 적용).
- FastAPI 의 `Depends(callable)` 은 매 요청마다 callable 을 호출하므로, `Depends(Provide[...])` 는 `Provide` object 가 user_service 자리에 주입되어 의존성 주입이 깨진다.
- 격리 환경에서 18 케이스 중 12 케이스 실패 (sqlalchemy.exc.OperationalError: no such table: users — production engine 사용으로 추정) 로 확인.

이는 라이브러리/프레임워크 조합의 본질적 한계로, 본 PR 의 시간 예산 안에서 우회가 어려움. 따라서 동등 의미를 유지하는 헬퍼 함수 패턴으로 전환한다.

---

## 3. 비목적

- Container 자체의 구조 변경 (Provider 종류 변경 등) — 본 PR 범위 외.
- wiring 범위 (`packages=...`) 변경 — 그대로 유지.
- `engine`, `session_factory`, `db`, `repository` 등의 와이어링 — 라우터에서 직접 노출되지 않으므로 영향 없음. 본 PR 은 라우터/의존성 함수에서 보이는 lambda 만.
- 테스트의 `Container.engine.override(...)` 패턴 변경 — `Provide` 는 override 와 호환되므로 영향 없음.
- 다른 의존성 (예: `get_current_user` 의 OAuth2 스키마) 변경.

---

## 4. 성공 기준

- [ ] `app/di/providers.py` 신규 — `get_user_service()`, `get_product_service()` 헬퍼.
- [ ] `Depends(lambda: Container.xxx())` 패턴 → `Depends(get_xxx_service)` 12곳 모두 교체.
- [ ] `grep -rn "Depends(lambda" app/` 결과 0건.
- [ ] 기존 55 PASS 유지 (외부 API 동작/응답 불변).
- [ ] 신규 회귀 가드는 불필요 — 기존 라우터 통합 테스트가 의존성 주입 깨짐을 즉시 검출.

---

## 5. 설계

### 5.1 헬퍼 모듈 (`app/di/providers.py` 신규)

```python
"""DI Container Provider 의 named helper 함수.

`Depends(get_xxx_service)` 형태로 라우터/의존성에서 사용한다. lambda 와
의미상 동일하며 매 요청 시 Container 의 Provider 를 평가한다. 명명된 함수라
가독성과 IDE 의 타입 추론이 개선된다.
"""
from app.di.containers import Container
from app.product.service import ProductService
from app.user.service import UserService


def get_user_service() -> UserService:
    return Container.user_service()


def get_product_service() -> ProductService:
    return Container.product_service()
```

### 5.2 변경 패턴

**Before**:

```python
@router.get("/")
async def list_users(
    skip: int = 0,
    limit: int = 100,
    _: Any = Depends(get_current_active_admin),
    user_service: UserService = Depends(lambda: Container.user_service()),
):
    ...
```

**After**:

```python
from app.di.providers import get_user_service

@router.get("/")
async def list_users(
    skip: int = 0,
    limit: int = 100,
    _: Any = Depends(get_current_active_admin),
    user_service: UserService = Depends(get_user_service),
):
    ...
```

데코레이터 추가/제거 없음. import 만 변경.

### 5.3 영향 받는 파일

| 파일 | 위치 (lambda 라인) | 함수 수 |
| --- | --- | --- |
| `app/user/router.py` | 28, 53, 69, 90, 107 | 5 |
| `app/product/router.py` | 25, 42, 58, 77, 96, 111 | 6 |
| `app/api/dependencies.py` | 22 | 1 |

`app/api/dependencies.py` 의 `get_current_user` 는 라우터가 아닌 의존성 함수이지만 동일 패턴 적용 가능 — FastAPI 가 의존성 그래프 내부에서 호출하므로 `@inject` 가 동일하게 동작.

### 5.4 테스트 영향

테스트의 `Container.engine.override(...)` 패턴은 wiring 과 독립적으로 동작 (Provider 자체에 대한 override). `Provide[Container.user_service]` 는 user_service Provider 를 참조하므로 그 의존 그래프 (user_repository → db → session_factory → engine) 의 override 가 정상 반영된다.

회귀 가드: 기존 통합 테스트 55건이 의존성 주입 깨짐을 즉시 검출 (200/401 → 401/500 등 응답 코드 변화).

### 5.5 wiring 동작 확인

`containers.py::wiring_config` 에 명시된 packages 가 정확히 라우터/의존성 모듈을 커버한다:
- `app.api` → `dependencies.py` ✓
- `app.user` → `router.py` ✓
- `app.product` → `router.py` ✓

wiring 은 모듈 import 시 자동 적용된다 (FastAPI app 생성 단계).

---

## 6. 영향

| 영역 | 영향 |
| --- | --- |
| `app/user/router.py` | 5곳 lambda → Provide + @inject 추가 |
| `app/product/router.py` | 6곳 lambda → Provide + @inject 추가 |
| `app/api/dependencies.py` | 1곳 lambda → Provide + @inject 추가 |
| `app/di/containers.py` | **변화 없음** |
| `tests/conftest.py` | **변화 없음** (override 패턴 그대로 호환) |
| 외부 API / 응답 / DB | **변화 없음** |
| 신규 테스트 | 불요 — 기존 통합 테스트가 회귀 가드 |

---

## 7. 리스크

| 리스크 | 가능성 | 대응 |
| --- | --- | --- |
| `@inject` 적용 후 FastAPI 가 의존성 시그니처를 잘못 인식 → 라우터 404/500 | 낮음 | 통합 테스트 55건이 즉시 잡음. 데코레이터 순서가 핵심 — `@router.get` 이 바깥 |
| 의존성 함수 (`get_current_user`) 에 `@inject` 가 의존성 그래프와 충돌 | 낮음 | dependency-injector 의 wiring 은 의존성 함수도 잘 처리. 통합 테스트가 인증 흐름 검증 |
| 테스트 override 가 wiring 과 충돌 | 낮음 | wiring 은 Provider 를 참조하므로 override 가 그대로 반영. 회귀 테스트로 확인 |
| `@inject` 적용 시 함수의 `__name__` / `__doc__` 손실 | 매우 낮음 | `@inject` 는 `functools.wraps` 사용 — 메타데이터 보존 |

---

## 8. 결정 사항 (확정)

- [x] 패턴: `Depends(get_xxx_service)` (named helper 함수)
- [x] 헬퍼 위치: `app/di/providers.py` 신규 모듈
- [x] 헬퍼는 매 호출 시 `Container.xxx()` 를 평가 — lambda 의 의미 그대로
- [x] 표준 `Provide + @inject` 패턴은 4.46.0 + FastAPI 호환성 한계로 폐기 (§2.1 참조)
- [x] 적용 범위: 라우터 (user/product) + 의존성 (`get_current_user`) — 라우터에서 보이는 lambda 모두
- [x] `Container` 자체는 변경 없음
- [x] `wiring_config` 는 현재로서는 미활용 — 별도 후속에서 4.x 의 FastAPI 통합 가이드가 명확해지면 재검토
- [x] 신규 단위 테스트는 불요 — 기존 통합 테스트가 충분
- [x] 본 PR 은 청소 작업 — 의미적 변경 0, 명명/가독성 개선만

---

## 9. 참고

- `app/di/containers.py` (wiring_config 선언)
- `app/user/router.py`, `app/product/router.py`, `app/api/dependencies.py`
- dependency-injector wiring docs: https://python-dependency-injector.ets-labs.org/wiring.html
