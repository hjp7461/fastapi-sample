# [PLAN] `docs/RUNBOOK.md` — 운영 마이그레이션 가이드

| 항목 | 내용 |
| --- | --- |
| 연관 PRD | `docs/[PRD]RUNBOOK_운영_마이그레이션_가이드.md` |
| 브랜치 | `feature/runbook-docs` |
| 추정 작업량 | 소~중 (1~1.5 시간) |
| 채택 전략 | RUNBOOK.md 신규 + HANDOFF §10 한 줄 + 모든 명령 실증 |

---

## 0. 사전 점검 (Pre-flight)

- [ ] `main` 최신, 55 PASS 기준선 확인
- [ ] `alembic.ini`, `app/core/config.py`, `app/main.py` 의 현재 상태가 PRD §5.2 매트릭스와 일치하는지 재확인
- [ ] 새 브랜치 `feature/runbook-docs` 생성

---

## 1. 작업 분해 (Step)

### Step 1 — 브랜치 생성

```bash
git checkout -b feature/runbook-docs
```

### Step 2 — RUNBOOK.md 신규 작성

PRD §5.1 의 9개 섹션 구조 그대로 작성. 각 명령은 복사-붙여넣기 가능한 형태.

### Step 3 — 모든 명령 실증

```bash
# §3 초기 배포 흐름 검증
rm -f app.db
uv run alembic upgrade head
uv run alembic current  # → ab265552a4a2 (head)
sqlite3 app.db ".tables"  # users, products, alembic_version

# §5 일상 명령 매트릭스 검증 (downgrade/upgrade)
uv run alembic downgrade -1  # NOTE: 단일 리비전이라 base 로 떨어짐
uv run alembic upgrade head
uv run alembic history --verbose
uv run alembic heads

# 정리
rm -f app.db
```

### Step 4 — 회귀 확인

```bash
uv run pytest 2>&1 | tail -3
# 기대: 55 PASS 그대로 (코드 변경 0)
```

### Step 5 — HANDOFF §10 갱신

`docs/[HANDOFF]세션_이어가기.md` §10 참고 파일 섹션에 `docs/RUNBOOK.md` 한 줄 추가.

### Step 6 — 커밋 + 푸시 + PR

```bash
git add -f docs/'[PRD]RUNBOOK_운영_마이그레이션_가이드.md' docs/'[PLAN]RUNBOOK_운영_마이그레이션_가이드.md' docs/RUNBOOK.md
# HANDOFF 는 로컬 전용이라 add 하지 않음
git commit ...
git push -u origin feature/runbook-docs
gh pr create ...
```

---

## 2. 산출물 체크리스트

| 산출물 | 위치 | 상태 |
| --- | --- | --- |
| PRD | `docs/[PRD]RUNBOOK_운영_마이그레이션_가이드.md` | ✅ |
| PLAN | `docs/[PLAN]RUNBOOK_운영_마이그레이션_가이드.md` | ✅ |
| RUNBOOK | `docs/RUNBOOK.md` | ⬜ |
| HANDOFF §10 한 줄 | `docs/[HANDOFF]세션_이어가기.md` | ⬜ (로컬 전용, 커밋 X) |

---

## 3. 회귀 방지

| 회귀 시나리오 | 가드 |
| --- | --- |
| 코드 변경에 따라 RUNBOOK stale | 각 섹션에 참조 PR/파일 명시. 후속 PR 에서 갱신 책임 |
| 명령이 실제 환경에서 동작 안 함 | Step 3 의 실증 단계 |
| 회귀 영향 (코드 변경 0 인데 깨짐) | 기존 55 PASS 가드 |

---

## 4. 롤백

`docs/RUNBOOK.md` 파일 삭제 또는 단일 커밋 revert. 코드 영향 0.

---

## 5. 후속 작업 후보

- CI/CD pipeline 구축 시 RUNBOOK 의 §3, §4 명령을 자동화
- Postgres 환경 실증 후 §7 체크리스트를 실증된 결과로 보강
- SECURITY.md (보안 정책 핸드북) 신설 검토

---

## 6. 참고

- PRD: `docs/[PRD]RUNBOOK_운영_마이그레이션_가이드.md`
- `docs/[PRD]Alembic_첫_마이그레이션.md`
- `alembic.ini`, `alembic/env.py`
