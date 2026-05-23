# [PRD] RUNBOOK 환경 변수 단락 보강 (+ .env.example 동기화)

> 출처: PR #22 §7 후속 + PR #23 §7 후속 ("RUNBOOK §환경 변수 단락 보강")
> 분류: 문서 (운영 핸드북)
> 작업량: 소

---

## 1. 배경

PR #22 에서 `USER_ADMIN_EMAIL_MASKING`, PR #23 에서 `LOG_LEVEL`/`LOG_FORMAT`/`LOG_FILE`/`LOG_FILE_ROTATION`/`LOG_FILE_RETENTION` 총 6개 환경 변수가 신규 도입됐다. 둘 다 §7 후속에 "RUNBOOK 갱신" 으로 명시했지만 실제 RUNBOOK 은 갱신 안 됐다.

추가 점검 중 `.env.example` 도 다음 빚 발견:
- `AUTO_CREATE_TABLES=true` 가 남아있음 (PR #14 에서 폐기, RUNBOOK §2 참고에 "AUTO_CREATE_TABLES 는 PR #14 에서 폐기됨" 명시)
- 신규 변수 6개 누락 (RUNBOOK 과 동일 누락)
- `GOOGLE_CLIENT_*` 3개는 코드 사용처 없음 (OAuth 미구현 상태로 보이지만 별도 검증 필요)

운영자가 `.env` 를 세팅할 때 RUNBOOK §2 와 `.env.example` 둘 다 보는 게 자연스러운 흐름인데, 두 곳 모두 진실원 (`app/core/config.py::Settings`) 과 어긋난 상태. 본 PR 로 정합성 복원.

---

## 2. 목적

- RUNBOOK §2 환경 변수 매트릭스에 6개 행 추가 (PR #22/#23 신규 변수)
- `.env.example` 에서 폐기 변수 (`AUTO_CREATE_TABLES`) 제거 + 6개 변수 추가 + 가시성 보강 (default / 운영 권장값 / 짧은 주석)
- RUNBOOK §2 끝에 "수집 파이프라인 연결 예시" 짧은 참고 단락 (LOG_FORMAT=json + LOG_FILE 조합)

---

## 3. 비목적

- **GOOGLE_CLIENT_* 변수 제거 안 함** — 코드 사용처는 없지만 향후 OAuth 도입 의도일 수 있음. 별도 검증 후 후속.
- **RUNBOOK §3-9 (배포/스키마/롤백/Postgres/트러블슈팅) 갱신 안 함** — 본 PR 은 §2 + .env.example 정합성에 한정.
- **README.md §로깅 단락 갱신 안 함** — `from app.core.logging import get_logger` 같이 outdated 내용이 보이지만 본 PR 범위 밖. 별도 후속 (handoff §6 신규 항목).
- **README.md §프로젝트 구조 트리 갱신 안 함** — datetime.py / permissions.py / providers.py / masking.py / logging.py 등 신규 모듈 누락. 별도 후속.
- **Settings 코드 변경 안 함** — 본 PR 은 문서만.

---

## 4. 성공 기준

1. `docs/RUNBOOK.md` §2 매트릭스에 6개 행 추가:
   - `USER_ADMIN_EMAIL_MASKING`, `LOG_LEVEL`, `LOG_FORMAT`, `LOG_FILE`, `LOG_FILE_ROTATION`, `LOG_FILE_RETENTION`
2. §2 끝에 "수집 파이프라인 연결 예시" 단락 (LOG_FORMAT=json + LOG_FILE) — 최대 5줄
3. `.env.example`:
   - `AUTO_CREATE_TABLES` 제거
   - PR #22 / #23 신규 변수 6개 추가 (default 그대로, 주석으로 의도 명시)
4. RUNBOOK §2 "AUTO_CREATE_TABLES 는 PR #14 에서 폐기" 참고 문구 보강 (`.env.example` 도 같이 정리됐다는 사실 명시)
5. 코드/테스트 무변경 → pytest 64 PASS / ruff 양쪽 종료 코드 0 유지
6. pre-commit run --all-files 모든 hook Passed

---

## 5. 설계

### 5.1 RUNBOOK §2 추가 행 (예시)

| 변수 | 기본값 | 운영 권장값 | 설명 |
| --- | --- | --- | --- |
| `USER_ADMIN_EMAIL_MASKING` | `true` | `true` | UserAdminView 응답의 email 마스킹. dev 디버깅 시 `false` 명시 (PR #22) |
| `LOG_LEVEL` | `INFO` | `INFO` (운영), `DEBUG` (디버깅) | loguru 레벨. 허용값: `DEBUG/INFO/WARNING/ERROR/CRITICAL` (PR #23) |
| `LOG_FORMAT` | `text` | `json` | text: 사람 친화 colorized, json: 수집 파이프라인 (PR #23) |
| `LOG_FILE` | `(빈 값)` | `/var/log/app.log` 등 | 미설정 시 stderr 만. 설정 시 file sink 추가 (PR #23) |
| `LOG_FILE_ROTATION` | `10 MB` | `100 MB` 등 | LOG_FILE 설정 시 rotation 정책 (loguru 문법, e.g. "1 day") |
| `LOG_FILE_RETENTION` | `7 days` | `30 days` 등 | LOG_FILE 설정 시 retention 정책 (loguru 문법) |

### 5.2 RUNBOOK §2 끝 "수집 파이프라인 연결 예시"

```markdown
**수집 파이프라인 연결 (운영)**: `.env` 에 다음 두 줄만 추가하면 JSON 라인 형식으로 stderr/파일 출력 → Datadog/CloudWatch/ELK 등 즉시 연결 가능.

\`\`\`
LOG_FORMAT=json
LOG_FILE=/var/log/app.log
\`\`\`
```

### 5.3 `.env.example` 갱신 (예상 형태)

```bash
# 환경 분기 (정보용)
ENVIRONMENT=development

# 데이터베이스
DATABASE_URL=sqlite+aiosqlite:///./app.db
# DB_ECHO: true 면 SQL 로그 출력 (디버깅용)
DB_ECHO=false

# JWT
SECRET_KEY=your-secret-key
# 토큰 만료 (분)
ACCESS_TOKEN_EXPIRE_MINUTES=30

# bcrypt 라운드 (4 ~ 31). 운영은 12 ~ 13 권장. 다운그레이드는 자동 차단 (PR #13)
BCRYPT_ROUNDS=12

# 응답 PII 정책 — UserAdminView email 마스킹 (PR #22)
# false 명시 시 raw email (dev 디버깅 전용)
USER_ADMIN_EMAIL_MASKING=true

# 로깅 (PR #23) — app/core/logging.py::setup_logging 가 참조
LOG_LEVEL=INFO          # DEBUG / INFO / WARNING / ERROR / CRITICAL
LOG_FORMAT=text         # text (사람 친화 colorized) / json (수집 파이프라인)
# LOG_FILE=/var/log/app.log    # 설정 시 file sink 추가
# LOG_FILE_ROTATION=10 MB      # loguru rotation 문법
# LOG_FILE_RETENTION=7 days    # loguru retention 문법

# OAuth (현재 코드 미사용 — 향후 도입 후보)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
```

- `AUTO_CREATE_TABLES` 제거
- `ACCESS_TOKEN_EXPIRE_MINUTES` 는 RUNBOOK §2 에 있으니 example 에도 보강 (옵션). 기본값 그대로면 생략 가능.
- LOG_FILE 류 3개는 주석 처리 (default 가 미설정/None 이므로 활성화는 의도적 선택)
- GOOGLE_* 는 "현재 코드 미사용 — 향후 도입 후보" 명시 → 운영자 혼동 차단

---

## 6. 영향

- **운영 환경**: 무영향 (문서/예시만 갱신, Settings/코드 무변동).
- **개발 환경**: `.env.example` 가 진실원과 일치 → 새 컨트리뷰터의 `.env` 세팅 혼동 감소.
- **회귀**: 코드 무변경 → pytest 64 PASS / ruff 양쪽 / pre-commit 모두 유지.

---

## 7. 후속 작업 (이번 PR 범위 밖)

- README.md §로깅 단락 갱신 (PR #23 setup_logging 반영, 거짓 `get_logger` 제거)
- README.md §프로젝트 구조 트리 갱신 (신규 모듈 5종 반영)
- GOOGLE_CLIENT_* 변수 정리 (코드 사용처 도입 또는 제거 결정)
- RUNBOOK §3-9 점검 (배포/스키마/롤백/Postgres/트러블슈팅 최신성)
- CI 도입 시 RUNBOOK §운영 점검 단락에 CI 가드 추가 (handoff §6)

---

## 8. 리스크

| 리스크 | 가능성 | 대응 |
| --- | --- | --- |
| `.env.example` 갱신이 다른 PR 의 in-flight 변경과 충돌 | 낮음 | 현재 open PR 없음. main 만. |
| 매트릭스 행 추가로 행 너비 변형 → 표 정렬 깨짐 | 낮음 | ruff 가 markdown 검사 안 함. 수동 점검. pre-commit 의 trailing-whitespace 만 가드. |
| LOG_FILE 의 "빈 값" 표기 혼동 (None vs 빈 문자열) | 낮음 | RUNBOOK 본문에 명시 ("미설정 시 stderr 만"). 코드: `os.getenv("LOG_FILE") or None` 이라 빈 문자열도 None 으로 처리. |

---

## 9. 결정 사항 (확정)

- [x] **본 PR 에 `.env.example` 갱신 포함** — RUNBOOK 과 `.env.example` 가 운영자 시점에 한 짝. 분리하면 다음 컨트리뷰터가 또 한 곳만 보게 됨.
- [x] **GOOGLE_CLIENT_* 제거 안 함, 주석으로 의도 명시** — 향후 도입 후보 가능성. 별도 후속에서 정리.
- [x] **AUTO_CREATE_TABLES 제거 + RUNBOOK 참고 문구 보강** — PR #14 결정 사항 일관성.
- [x] **README.md 갱신 비범위** — 별도 후속 (작업 범위가 다름 — 운영자 핸드북 vs 개발자 가이드).
- [x] **LOG_FILE 류 3개는 주석 처리** — default 가 미설정이라 활성화는 의도적 선택.

---

## 10. 참고

- `app/core/config.py::Settings` (단일 진실원)
- `docs/RUNBOOK.md` (보강 대상)
- `.env.example` (보강 대상)
- `docs/[PRD]마스킹_정책_환경변수화.md` (PR #22)
- `docs/[PRD]loguru_sink_포맷_설정.md` (PR #23)
- `docs/[PRD]Alembic_첫_마이그레이션_AUTO_CREATE_TABLES_청소.md` (PR #14 — AUTO_CREATE_TABLES 폐기 컨텍스트)
