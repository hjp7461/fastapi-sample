"""사용자 PII 마스킹 유틸리티.

다중방어 정책의 응답 layer 구현. 권한 가드가 1차 차단을 담당하고, 본 헬퍼는
응답 본문의 PII 면적을 줄여 우연한 노출 (로그/캐시/디버그 도구) 을 차단한다.
"""


def mask_email(email: str) -> str:
    """이메일을 `a***@e***.com` 형태로 마스킹한다.

    - 로컬 파트: 첫 글자만 노출, 나머지 ***
    - 도메인의 호스트: 첫 글자만 노출, 나머지 ***
    - 도메인의 TLD: 그대로 유지

    정상 입력 외 (빈 문자열, '@' 0개, TLD 없음) 은 보수적으로 ``"***"`` 반환.
    """
    if not email or "@" not in email:
        return "***"

    local, _, domain = email.partition("@")
    if "." not in domain:
        return "***"

    host, _, tld = domain.partition(".")
    masked_local = f"{local[0]}***" if local else "***"
    masked_host = f"{host[0]}***" if host else "***"
    return f"{masked_local}@{masked_host}.{tld}"
