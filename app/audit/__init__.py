"""audit log — 사용자/재고/인증 사건의 영속 sink.

Single source of truth for audit events. 호출자는 `app.audit.recorder.record_audit`
를 통해 사건을 기록한다. 본 모듈은 **인프라만** — 도메인 hook (auth/user/product
service 의 record_audit 호출) 은 별도 PR 에서 추가.
"""
