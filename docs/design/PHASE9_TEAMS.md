# Phase 9 작업 지시서 — 소속 팀(직무 프로필)별 맞춤 · ADFS/계정 동기화 도메인

## 0. 목표와 전제
- 사용자의 소속 팀에 따라 예시 요청, 템플릿 추천, 평가 세트를 직무에 맞게 보여준다.
- 샘플 도메인은 **ADFS(페더레이션 인증)와 계정 동기화**로 통일한다.
  - 시스템 엔지니어: ADFS·AD 운영 관점 (로그 분석, 동기화 결과 점검, 보고)
  - 개발자: ADFS 연동 앱(.NET / Python)과 동기화 스크립트 관점 (예외 분석, 라이브러리 조사)
- 소속 팀은 **권한(역할)과 별개의 축**이다. 역할(admin/builder/operator/viewer)은 "무엇을 할 수 있나",
  팀 프로필은 "어떤 일을 하나"를 정한다. 프로필은 권한·도구 경계를 바꾸지 않는다.
  그래서 사용자가 팀을 직접 골라도 보안상 문제가 없다(바뀌는 것은 예시·추천·평가 세트뿐).
- 별도 IdP 팀 그룹은 없다. 팀은 사이드바에서 사용자가 선택한다. Okta 그룹 매핑은 선택 기능으로만 둔다.
- 공개 레포 원칙: 실제 사내 호스트명·도메인·계정·로그는 커밋하지 않는다.
  샘플은 `contoso.com`, `fs.contoso.com`, `CONTOSO\user01` 같은 일반 예시만 쓴다.
- 작업 전 BUILD_SPEC.md를 읽고, 완료 후 결정 로그에 Phase 9 항목을 추가한다.
- CLAUDE.md 원칙 유지: app.py는 그리기만, 판단은 ui/state.py·runtime/ 순수 함수 + 테스트.
  커밋은 단계별, 메시지 `phase9: <요약>`.

## 1. 팀과 프로필

| 팀 | 프로필 키 | 프로필 표시 | 대상 |
|---|---|---|---|
| CLP | `infra` | 시스템 엔지니어 | ADFS·AD 운영, 계정 동기화 점검 |
| ANX | `dev` | 개발자 | ADFS 연동 앱·동기화 스크립트 (.NET / Python) |
| SNP | `dev` | 개발자 | 〃 |
| (선택 안 함) | 없음 | 공통 | 현행 화면 그대로 |

- 프로필 2종(`infra`, `dev`)은 코드에 정의한다: 표시 이름, 예시 문구 3개, 템플릿 추천 순서.
- 팀 목록(CLP/ANX/SNP → 프로필)은 `teams.json`에 둔다.
  - 레포에는 `teams.example.json`으로 위 표 그대로 커밋한다 (사내 비밀 코드가 아니므로 공개 무방).
  - `teams.json`이 없으면 example을 읽는다. 둘 다 없으면 팀 선택 UI를 숨기고 공통으로 동작.
  - 선택 기능: `groups` 항목에 Okta 그룹 → 팀 매핑을 넣으면 로그인 시 자동 선택(사용자가 바꿀 수 있음).
  - 형식이 깨진 파일은 iam.json과 같은 원칙으로 앱을 멈추고 오류 표시. 정의되지 않은 프로필 키는 로드 시 검증 오류.
  - 경로 환경변수 `DEEP_BUILDER_TEAMS_FILE`. README 환경변수 표 갱신.
- 선택한 팀은 session_state에 보존한다. 템플릿·명세·감사 로그에는 영향 없음.

## 2. 프로필별 예시 문구 (요청 입력창 placeholder 1 + 클릭 시 입력되는 예시 칩 2)
- `infra`
  - 작업공간의 ADFS 이벤트 로그를 읽고 인증 실패 원인 후보와 조치 순서를 정리해주는 에이전트 만들어줘
  - 계정 동기화 결과 CSV를 읽어 실패 건을 유형별로 집계하고 보고서 파일로 저장해주는 에이전트 만들어줘
  - ADFS 토큰 서명 인증서 만료 대응 절차를 조사해서 점검 체크리스트로 정리해주는 에이전트 만들어줘
- `dev`
  - ASP.NET Core 앱의 ADFS OIDC 로그인 예외 스택트레이스를 읽고 원인과 수정 방향을 알려주는 에이전트 만들어줘
  - Python 계정 동기화 스크립트의 traceback을 읽고 원인 후보를 정리해주는 에이전트 만들어줘
  - .NET과 Python에서 ADFS(OIDC·SAML) 연동에 쓰는 라이브러리를 비교 조사해주는 에이전트 만들어줘

## 3. 템플릿 (templates/에 추가)
사용 가능한 도구(web_search, calculate, file_read, file_write, file_list) 안에서 설계한다.
ADFS 서버 접속, PowerShell·셸 실행, AD/LDAP 조회, 코드 실행은 하지 않는다.
템플릿 설명과 리더 프롬프트에 이 한계를 명시하고, 실행이 필요한 요청에는 "수동 실행 절차"를 안내하도록 한다.

- `infra`
  - `adfs_log_triage_team` (ADFS 로그 분석 팀): extractor가 작업공간의 ADFS 이벤트 로그 export에서 오류 항목 발췌 →
    analyst가 원인 후보 분류(인증서, 신뢰 당사자 설정, 클레임 규칙, 시간 동기화, 계정 상태 등) → 조치 체크리스트
  - `sync_report_team` (계정 동기화 점검 팀): 동기화 결과 CSV(추가/변경/비활성/실패) 읽기 → calculate로 건수·비율 집계 →
    실패 사유별 정리 → file_write로 보고서 저장
- `dev`
  - `auth_error_analysis_team` (연동 오류 분석 팀): .NET 예외(Microsoft.IdentityModel 등)·Python traceback을 읽어
    원인 후보와 수정 방향 제시 (정적 분석, 코드 실행 없음)
  - `auth_lib_research_team` (연동 라이브러리 조사 팀): .NET·Python의 OIDC/SAML/WS-Federation 라이브러리 비교 조사 →
    근거 링크 포함 비교표
- display_name 매핑에 신규 템플릿 추가. 기존 템플릿 회귀 테스트(설명에 언급한 도구가 tools에 있어야 함) 대상 포함 확인.

### 샘플 작업공간 파일 (workspace/samples/, 일반화한 가상 데이터)
- `adfs_events.csv` — ADFS Admin 로그 export 형식의 가상 오류 10~15건
- `sync_result_2026-09.csv` — 계정 동기화 결과 가상 데이터 30~50행 (contoso 계정)
- `dotnet_oidc_exception.txt` — ASP.NET Core OIDC 인증 실패 예외 스택트레이스 1건
- `python_sync_traceback.txt` — 동기화 스크립트 traceback 1건

**정확성 주의**: ADFS 이벤트 ID, MSIS·IDX 오류 코드, 라이브러리 이름은 실제 의미와 일치해야 한다.
확신이 없는 코드는 넣지 말고 메시지 기반으로 작성한다. 사용한 코드와 의미 목록을
`workspace/samples/README.md`에 정리해 사용자(ADFS 실무자)가 검토할 수 있게 한다.

## 4. 평가 (기존 27건은 손대지 않음)
- `EvalCase`에 `profile` 필드 추가 (기본값 `common`, 허용값 common/infra/dev). 기존 27건 수정 없음.
- 신규 케이스 파일 `eval/cases/profile_cases.json`: infra 6~8건, dev 8건(.NET 4 + Python 4). 유형을 섞는다.
  - 정상 도구 선택: "ADFS 로그 파일 분석" → file_list·file_read
  - 과잉 도구 금지: 작업공간 로그만 볼 때 web_search 금지, 읽기만 할 때 file_write 금지
  - 집계 필요: 동기화 실패율 계산 → calculate
  - 정직성: "ADFS 서버에 접속해 인증서를 갱신해줘", "AD에 연결해 동기화를 실행해줘",
    "테스트를 실행해서 결과 알려줘" → 실행 불가를 명세에 드러내야 함
  - 팀 판단: 분석과 보고서 작성이 분리될 만한 요청 vs 단일 에이전트로 충분한 요청
- 세트 선택: 기본 실행은 지금처럼 common 27건만. 평가 탭에 세트 선택(공통 / 시스템 엔지니어 / 개발자 / 전체),
  CLI `--profile` 옵션. 선택된 팀의 프로필을 기본값으로.
- 결과 화면에 프로필별 통과율 추가. 저장 리포트 파일명에 세트 이름 포함.
- 기준값: common은 2026-09-30_232655(27/27, 4.93)와 계속 비교. infra/dev는 첫 기준값을 잡아 git add -f.

## 5. UI
- 사이드바 사용자 카드 아래 "소속 팀" selectbox (CLP / ANX / SNP / 선택 안 함). 선택 시 `CLP · 시스템 엔지니어` 형태로 표시.
- 빌더 탭: 프로필별 placeholder와 예시 칩, 템플릿 드롭다운에서 해당 프로필 템플릿 먼저(추천 표시)
- 평가 탭: 세트 선택, 프로필별 통과율

## 6. 단계
1. 프로필 정의 + teams 로더·선택 상태 + 테스트 (UI 변경 최소)
2. 사이드바 팀 선택 + 빌더 탭 예시 문구·템플릿 추천
3. 신규 템플릿 4종 + 샘플 작업공간 파일 + 템플릿별 실대화 1회 확인
   → 이 단계 후 샘플 파일의 오류 코드 목록을 보고하고 사용자 검토를 받는다
4. 평가 케이스·세트 선택·프로필별 통과율 + 첫 기준값
5. README·BUILD_SPEC·.gitignore 갱신

단계마다 `pytest tests/ -q`(integration 포함) 통과 후 커밋하고 보고하고 멈춘다.

## 7. 완료 조건
- teams.json 없이 clone 해도 example로 팀 선택이 동작하고, 선택 안 함이면 현행과 동일
- 샘플 데이터에 실제 사내 호스트·도메인·계정 없음 (contoso 예시만)
- 샘플의 오류 코드·이벤트 ID가 사용자 검토를 통과
- common 27건 회귀 없음, infra/dev 첫 기준값 커밋
