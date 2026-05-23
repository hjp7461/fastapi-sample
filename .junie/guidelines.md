# Project Guidelines

## 프로젝트 구조
이 프로젝트는 FastAPI를 기반으로 한 웹 애플리케이션입니다. SQLAlchemy ORM, Alembic, 그리고 SQLModel을 사용하여 데이터베이스와 상호작용하며, Pydantic을 사용하여 데이터 검증 및 스키마 관리를 수행합니다.

* **`app` 디렉토리**
  - `core` : 설정 및 로깅 관련 모듈
  - `di` : 의존성 주입 관련 모듈
  - `api` : FastAPI 라우터 및 의존성 관리
  - `product`, `user` 등 하위 도메인 디렉토리 : 각 도메인의 비즈니스 로직, 스키마, 서비스, 라우터 등을 포함
  - `main.py` : 애플리케이션 진입점

* **`alembic` 디렉토리**
  - Alembic을 활용한 마이그레이션 파일 관리

* **그 외 파일**
  - `.env` : 애플리케이션 환경 변수 설정
  - `pyproject.toml` : 종속성 및 프로젝트 구성

---

## 테스트 수행 방법
Junie는 다음 지침에 따라 테스트를 수행합니다:

1. **테스트 프레임워크**: `pytest`를 사용합니다. 모든 테스트 파일은 `tests/`로 시작해야 하며, 네이밍은 `test_*.py`로 합니다.
2. **테스트 실행 명령어**:
   ```bash
   pytest
   ```
3. **커버리지 테스트**: 코드 커버리지를 확인하려면 다음 명령어를 사용합니다:
   ```bash
   pytest --cov=app
   ```

---

## Alembic 마이그레이션 관리
데이터베이스 마이그레이션은 Alembic을 사용하며, SQLAlchemy를 기반으로 합니다.

1. **마이그레이션 생성**:
   ```bash
   alembic revision --autogenerate -m "description of changes"
   ```

2. **마이그레이션 적용**:
   ```bash
   alembic upgrade head
   ```

3. **마이그레이션 테스트**:
   - 새 마이그레이션을 반영한 후, 데이터베이스 스키마와 상태를 확인합니다.

---

## 코딩 스타일 및 규칙
이 프로젝트는 [PEP 8](https://peps.python.org/pep-0008/)에 따라 작성됩니다.

### 추가 규칙:
1. **타입 힌트 필수**: 모든 함수 또는 메서드는 타입 힌트를 포함해야 합니다.
2. **Pydantic 모델 상속**: 모든 데이터 스키마는 `BaseModel`에서 상속받아야 하며, 적절한 `validator`를 구현해야 합니다.
3. **SQLModel**: 모델에 기본 테이블 이름을 제공해야 합니다:
   ```python
   class User(SQLModel, table=True):
       __tablename__ = "users"
       ...
   ```

---

## 환경 설정
`.env` 파일을 설정하여 애플리케이션이 올바른 환경 변수에 접근할 수 있도록 만듭니다. 일반적으로 아래와 같은 변수가 필요합니다:

- **DATABASE_URL**: 데이터베이스 연결 문자열
- **SECRET_KEY**: JWT 토큰 서명에 사용할 비밀 키
- **ENVIRONMENT**: 실행 환경 (`development`, `production`)

예제:
```env
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
SECRET_KEY=your_secret_key
ENVIRONMENT=development
```

---

## 코드 빌드 및 실행
1. **개발 서버**:
   ```bash
   uvicorn app.main:app --reload
   ```

2. **운영 서버**:
   * `gunicorn` 또는 `uvicorn` 사용
   * 예:
     ```bash
     gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
     ```

---

## Junie에게 요청 시 지침
1. **코드 리뷰**: 해결해야 할 문제에 대한 정확한 설명을 추가하세요.
2. **테스트**: 특수한 방법이 필요할 경우 명시적으로 알려주세요.
3. **구조 변경 요청**: 프로젝트의 전반적인 흐름을 준수해야 합니다.
