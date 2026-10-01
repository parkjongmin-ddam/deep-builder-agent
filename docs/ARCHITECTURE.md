# 아키텍처 — 스키마 관계도와 데이터흐름

> 작성일: 2026-10-01 · 레이어 설명은 [CLAUDE.md](../CLAUDE.md), 결정 배경은 [BUILD_SPEC.md](../BUILD_SPEC.md)

## 1. 스키마 관계도 (ERD 대체)

**이 시스템에는 데이터베이스가 없다.** 모든 영속 데이터는 파일(JSON·JSONL·txt)이고
스키마는 Pydantic 모델·dataclass가 정의한다. 따라서 아래는 테이블 ERD가 아니라
**스키마 관계도**다 — 핵심 필드와 관계(카디널리티)만 그리고, 전체 필드는 소스로
연결한다.

| 스키마 | 소스 | 저장 위치 |
|---|---|---|
| AgentSpec · SubAgentSpec | [runtime/spec.py](../runtime/spec.py) | `specs/<name>/vN.json` (이력) + `templates/*.json` (손으로 쓴 것) |
| 도구 레지스트리 | [registry/](../registry/) | 코드 (파일 아님 — 화이트리스트의 단일 진실 원천) |
| EvalCase | [eval/dataset.py](../eval/dataset.py) | `eval/cases/*.json` |
| CaseResult · EvalReport | [eval/runner.py](../eval/runner.py) | 실행 중 메모리, 텍스트 리포트로 `eval/results/<시각>_<세트>.txt` |
| BoundaryProbe | [eval/boundary.py](../eval/boundary.py) | 코드 (측정 이력은 observed 필드) |
| Role · Principal · IamConfig | [runtime/iam.py](../runtime/iam.py) | `iam.json` (없으면 내장 기본 정책) |
| 감사 레코드 | [runtime/iam.py](../runtime/iam.py) `_write_audit` | `logs/audit.jsonl` (append-only) |
| Profile · TeamsConfig | [runtime/teams.py](../runtime/teams.py) | 프로필은 코드, 팀 매핑은 `teams.json`(없으면 `teams.example.json`) |

### 1-1. 명세와 평가

```mermaid
erDiagram
    AGENT_SPEC ||--o{ SUB_AGENT_SPEC : "subagents (0..5, 깊이 1 고정)"
    AGENT_SPEC }o--o{ TOOL : "tools (레지스트리 키 문자열 참조)"
    SUB_AGENT_SPEC }o--o{ TOOL : "tools (같은 밸리데이터)"
    EVAL_CASE |o--o| AGENT_SPEC : "revise_base (선택 — 수정 평가의 기반 스펙)"
    EVAL_REPORT ||--|{ CASE_RESULT : "results"
    CASE_RESULT }|--|| EVAL_CASE : "실행 1회당 1건"
    CASE_RESULT |o--o| AGENT_SPEC : "spec (생성 성공 시)"
    CASE_RESULT |o--o| JUDGE_VERDICT : "verdict (심판 돌았을 때만)"

    AGENT_SPEC {
        string spec_version "0.3"
        string name PK
        string system_prompt "가드레일 문장 강제"
        string model
        list tools FK "허용 키만 통과"
    }
    SUB_AGENT_SPEC {
        string name "팀 내 유일"
        string system_prompt
        list tools FK
        string model "선택 - 비우면 리더 상속"
    }
    TOOL {
        string key PK "web_search, calculate 등 + mcp 접두 키"
    }
    EVAL_CASE {
        string id PK
        string request
        string profile "common | infra | dev"
        list expect_tools
        list forbid_tools
        bool expect_team
        string rubric "심판 채점 기준"
    }
    CASE_RESULT {
        string case_id FK
        string profile "프로필별 통과율 집계용"
        list checks "기계적 검사 5종"
        string error "생성 실패도 결과다"
    }
    JUDGE_VERDICT {
        int score "통과선 4점"
        string reason
    }
    EVAL_REPORT {
        string summary "세트 리포트 파일로 저장"
    }
```

### 1-2. 설정(IAM·팀)과 감사 로그

```mermaid
erDiagram
    ROLE ||--o{ PRINCIPAL : "principals (이름 → 역할)"
    ROLE ||--o{ IDP_GROUP : "groups (Okta 클레임 → 역할, 선언 순서 우선)"
    ROLE }o--o{ TOOL : "tools = 권한 경계 (부여 시점에만 적용)"
    PRINCIPAL ||--o{ AUDIT_RECORD : "허용·거부 모두 기록"
    PROFILE ||--o{ TEAM : "teams.json (팀 → 프로필 키)"
    TEAM ||--o{ OKTA_GROUP_MAP : "groups (선택 — 로그인 시 자동 선택)"
    PROFILE }o--o{ TEMPLATE_SPEC : "recommended_templates (이름 참조, 실존은 테스트 강제)"

    ROLE {
        string name PK "admin | builder | operator | viewer"
        list actions "create, revise, run, view"
        list tools "도구 경계"
    }
    PRINCIPAL {
        string name PK "데모 이름 또는 검증된 이메일"
        string role FK
    }
    IDP_GROUP {
        string group PK
        string role FK
    }
    AUDIT_RECORD {
        string timestamp
        string principal "검증된 신원"
        string action
        string decision "allow | deny"
        string resource
    }
    PROFILE {
        string key PK "infra | dev (코드 정의)"
        string display
        list examples "예시 칩 2"
        list recommended_templates
    }
    TEAM {
        string name PK "CLP, ANX, SNP"
        string profile FK
    }
    OKTA_GROUP_MAP {
        string group PK
        string team FK
    }
    TEMPLATE_SPEC {
        string name PK "AgentSpec 스키마의 파일 (templates/)"
    }
```

주: `PROFILE`은 파일이 아니라 코드(`runtime/teams.py`)에 정의된다 — 팀은 권한과
**별개의 축**이라 `ROLE`과 `PROFILE` 사이에는 관계선이 없다. 이것이 의도다.

## 2. 데이터흐름도

### 2-1. 메인 경로 — 자연어 요청에서 대화·감사 로그까지

```mermaid
flowchart TD
    U["자연어 요청 (CLI cli.py / UI ui/app.py)"] --> IAM{"IAM 인가 authorize_action<br/>(생성·수정이면 도구 경계도)"}
    IAM -- "거부" --> AUD[("logs/audit.jsonl<br/>허용·거부 모두 append")]
    IAM -- "허용 (기록은 동일)" --> B["Builder<br/>generate_spec / revise_spec"]
    B --> V{"AgentSpec 검증<br/>도구 화이트리스트 · 팀 상한 · 경계"}
    V -- "실패를 피드백으로 재생성 (재시도 루프)" --> B
    V -- "통과" --> G["ensure_guardrail<br/>(가드레일 문장 코드 주입)"]
    G --> S[("specs/{name}/vN.json<br/>버전 이력 + 최신본")]
    T[("templates/*.json<br/>손으로 쓴 팀 스펙")] --> L["load_spec_file<br/>(같은 검증·가드레일 보장)"]
    S --> R["Runtime factory (deepagents)<br/>서브에이전트마다 FilesystemMiddleware"]
    L --> R
    R --> W[("workspace/<br/>에이전트가 닿는 유일한 디스크")]
    R --> C["대화 — 단계 단위 스트리밍<br/>(위임·내부 도구 호출 표시)"]
    IAM --> AUD
```

### 2-2. 평가 경로 (별도)

```mermaid
flowchart TD
    CS[("eval/cases/*.json<br/>공통 27 + infra 7 + dev 8")] --> F["cases_for_set<br/>세트 선택 (기본 common)"]
    F --> RC["run_case (케이스가 죽어도 계속)"]
    RC --> B2["Builder 호출<br/>generate_spec / revise_spec"]
    B2 --> CK{"기계적 검사 5종<br/>도구·과잉·팀·팀원 도구·가드레일"}
    CK -- "실패 (심판 안 부름)" --> RES["CaseResult"]
    CK -- "통과" --> J["LLM 심판 (claude-haiku)<br/>rubric 채점, 통과선 4점"]
    J --> RES
    RES --> RP["EvalReport<br/>프로필별 통과율"]
    RP --> OUT[("eval/results/시각_세트.txt<br/>기준값만 git add -f")]
    PRB["경계 프로브 eval/boundary.py<br/>(세트 밖 — 팀 생성 빈도 측정)"] -.-> B2
```

흐름의 불변식 — 어느 진입점(CLI·UI·템플릿·평가)이든 **같은 검증·같은 가드레일**을
받는다(`load_spec_file` 공용화), 인가 판정은 **허용·거부 모두** 감사 로그에 남는다,
Builder 재시도 루프에는 검증 실패와 경계 위반이 **같은 피드백 형식**으로 들어간다.
