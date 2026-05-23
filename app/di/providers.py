"""DI Container Provider 의 named helper 함수.

`Depends(get_xxx_service)` 형태로 라우터/의존성에서 사용한다. lambda 와
의미상 동일하며 매 요청 시 Container 의 Provider 를 평가한다. 명명된 함수라
가독성과 IDE 의 타입 추론이 개선된다.

참고: dependency-injector 4.46.0 의 `@inject + Provide[...]` 표준 패턴은
FastAPI `Depends(...)` 와 직접 호환되지 않음 (Provide marker 가 callable
이지만 호출 시 자기 자신을 반환). 그래서 본 프로젝트는 lambda 의 의미를
유지하는 named helper 패턴을 채택. 자세한 사유는
`docs/[PRD]DI_와이어링_lambda_청소.md` §2.1 참조.
"""

from app.di.containers import Container
from app.product.service import ProductService
from app.user.service import UserService


def get_user_service() -> UserService:
    return Container.user_service()


def get_product_service() -> ProductService:
    return Container.product_service()
