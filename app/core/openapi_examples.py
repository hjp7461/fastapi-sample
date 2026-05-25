"""OpenAPI examples — error envelope 의 단일 진실원 (PR #62).

PRD §5.4 매트릭스의 4종 status x code x example body 를 상수로 노출.
router 의 데코레이터에서 import 하여 `responses={401: ERROR_401_AUTHENTICATION, ...}`
로 합성한다.

PII 정책 (PRD §5.6):
- email 도메인 = `*@example.com` (RFC 6761 reserved)
- password = `dummy-secret-please-change` / `test_pw_minimum` (실 비밀번호 패턴 회피)
- full_name / username = `홍길동` / `김철수` / `이영희` (통상 가명)
- ID 는 정수 (`1`, `2`) — 본 프로젝트는 ULID 가 아닌 SQLModel int PK 사용

customizer (`app/core/openapi.py::_inject_error_responses`) 가 error response 의
schema 만 `$ref` 로 덮어쓰고 라우터가 명시한 example/headers/description 은
merge 로 보존한다 (PRD §5.3).
"""

from typing import Any

# 401 — 인증 실패 / 잘못된 자격증명 / 토큰 누락·만료
ERROR_401_AUTHENTICATION: dict[str, Any] = {
    "description": "인증 실패 (잘못된 자격증명 또는 토큰 누락/만료)",
    "content": {
        "application/json": {
            "example": {
                "detail": {
                    "message": "Could not validate credentials",
                    "code": "authentication_error",
                }
            }
        }
    },
    "headers": {
        "WWW-Authenticate": {
            "description": "OAuth2 Bearer challenge (RFC 7235)",
            "schema": {"type": "string"},
        },
    },
}

# 403 — 권한 부족 (role 검사 실패)
ERROR_403_AUTHORIZATION: dict[str, Any] = {
    "description": "권한 부족 (role / 소유자 검사 실패)",
    "content": {
        "application/json": {
            "example": {
                "detail": {
                    "message": "Not enough permissions",
                    "code": "authorization_error",
                }
            }
        }
    },
}

# 404 — 사용자 미존재
ERROR_404_NOT_FOUND_USER: dict[str, Any] = {
    "description": "사용자 미존재",
    "content": {
        "application/json": {
            "example": {
                "detail": {
                    "message": "User not found",
                    "code": "not_found",
                }
            }
        }
    },
}

# 404 — 상품 미존재
ERROR_404_NOT_FOUND_PRODUCT: dict[str, Any] = {
    "description": "상품 미존재",
    "content": {
        "application/json": {
            "example": {
                "detail": {
                    "message": "Product not found",
                    "code": "not_found",
                }
            }
        }
    },
}

# 422 — 요청 검증 실패 (Pydantic / Query 제약)
ERROR_422_VALIDATION: dict[str, Any] = {
    "description": "요청 검증 실패 (Pydantic / Query 제약)",
    "content": {
        "application/json": {
            "example": {
                "detail": {
                    "message": "Validation error",
                    "code": "request_validation_error",
                    "errors": [
                        {
                            "loc": ["body", "email"],
                            "msg": "value is not a valid email address",
                            "type": "value_error",
                        }
                    ],
                }
            }
        }
    },
}
