# deep_builder_agent

자연어 요구를 받아 AI 에이전트를 **생성·실행·평가**하는 빌더.
LangChain deepagents 하네스 위에서 Pydantic 스펙(`AgentSpec`)이 도구 화이트리스트와 가드레일을 강제한다.

> **상태**: Phase 1~4 완료 · 테스트 235건 통과 · 전 경로 실호출 검증 완료
> **문서**: [REPORT.md](REPORT.md) 개발 보고서 · [BUILD_SPEC.md](BUILD_SPEC.md) 설계 결정·실측 원장 · [CLAUDE.md](CLAUDE.md) 작업 규칙

---

## 빠른 시작

Anthropic API 키 하나만 있으면 5분 안에 돌아간다.

```bash
# 1. 설치
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # macOS/Linux

# 2. 키 설정 — .env 를 열어 ANTHROPIC_API_KEY= 뒤에 붙여넣는다
cp .env.example .env

# 3. 바로 실행 (Anthropic 키만 필요)
python cli.py --spec templates/data_analysis_team.json
```

```
you> 1부터 200까지 3의 배수이면서 5의 배수가 아닌 수의 합 구해줘
```

- analyst가 계산하고 → reviewer가 **다른 방법으로** 검산하고 → 리더가 일치를 확인한 뒤 보고한다
- 위임이 3단계라 답이 나오기까지 30초~1분 걸린다

> `templates/`는 저장소에 포함돼 있어 clone 직후 바로 쓸 수 있다.
> `specs/`는 생성물이라 gitignore 대상이므로 처음에는 비어 있다.

---

## 동작 방식

```
자연어 요구
   ↓  builder/    LLM 호출 → JSON 파싱 → 가드레일 문장 주입 (리더 + 팀원 전원)
   ↓  runtime/    AgentSpec 검증 (도구 화이트리스트 / 팀 구성 검증)
   ↓  registry/   커스텀 도구 + MCP 서버 도구 해석
   ↓  runtime/    deepagents 인스턴스화 (리더·팀원 각각 요청한 도구만 노출)
대화 / 평가
```

핵심은 **LLM의 준수를 신뢰하지 않는 것**이다.

- 도구 화이트리스트는 프롬프트 요청이 아니라 Pydantic 밸리데이터가 **거부**한다
- 가드레일 문장은 LLM이 빠뜨리면 `ensure_guardrail()`이 **코드로 삽입**한다.
  `--spec`으로 넣는 손으로 쓴 스펙과 UI 템플릿 로드도 같은 보장을 받는다(`load_spec_file()`)
- deepagents가 자동 주입하는 셸 실행 도구(`execute`)는 `FilesystemMiddleware` 재정의로 차단한다
  — 단, `python_repl`을 허용한 스펙은 사실상 셸을 허용한 것이다 (아래 「알려진 한계」)
- **서브에이전트에도 같은 차단을 따로 건다** — 메인의 제한은 팀원에게 전파되지 않아서,
  빠뜨리면 위임 한 번으로 셸이 열린다 (실측 근거: [BUILD_SPEC.md](BUILD_SPEC.md) 5-3)
- 검증에 실패하면 에러 메시지를 Builder에게 되돌려 **최대 3회까지 시도**한다

---

## 환경변수

| 변수 | 필수 | 용도 |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Builder와 생성된 에이전트 |
| `TAVILY_API_KEY` | — | `web_search` 도구. 없으면 결과를 지어내지 않고 명확한 에러를 반환한다 |
| `DEEP_BUILDER_MODEL` | — | Builder 모델 (기본 `claude-sonnet-4-6`) |
| `DEEP_BUILDER_JUDGE_MODEL` | — | 평가 심판 모델 (기본 `claude-haiku-4-5`) — Builder와 **다른 모델이 기본값**이라 자기 채점 편향이 없다 |
| `DEEP_BUILDER_WORKSPACE` | — | 에이전트가 파일을 읽고 쓰는 디렉터리 (기본 `workspace`) |
| `LANGSMITH_TRACING` | — | `true`면 트레이싱. 키 없이 켜면 **실행 전에** 막는다 |
| `LANGSMITH_API_KEY` | — | 트레이싱을 켤 때 필수 |

> ⚠️ 키는 **`.env`에만** 넣는다. `.env.example`은 git 추적 대상이라
> (`.gitignore`가 막는 것은 `.env`뿐) 키를 적으면 그대로 커밋된다.
> 선택 항목은 **비워 두면** 기본값이 쓰인다.

기능별로 필요한 키:

| 하려는 것 | 필요한 키 |
|---|---|
| 자연어로 에이전트 생성, `data_analysis_team`, `doc_qa_team`, 평가 | `ANTHROPIC_API_KEY` |
| `research_team` (웹 검색) | \+ `TAVILY_API_KEY` |
| 실행 추적·토큰 측정 | \+ `LANGSMITH_API_KEY` |

---

## 사용법

### CLI

```bash
# 자연어로 에이전트를 만들고 바로 대화
python cli.py "웹 검색으로 최신 IT 뉴스를 찾아 3줄로 요약해주는 에이전트 만들어줘"

# 팀 템플릿으로 실행
python cli.py --spec templates/research_team.json

# 생성한 스펙을 다시 사용 (specs/ 에 저장된다)
python cli.py --spec specs/it_news_summarizer.json

# 생성·검증만 하고 종료 (대화 없음)
python cli.py "..." --no-chat
```

### Streamlit UI

```bash
streamlit run ui/app.py
```

- **사이드바** — 환경 점검(키·트레이싱·MCP). 비밀값은 **존재 여부만** 표시한다
- **빌더 탭** — 왼쪽에서 자연어로 만들거나 템플릿을 불러오고, 오른쪽에서 바로 대화
- **평가 탭** — 케이스를 돌려 Builder 회귀 확인. 심판은 기본 꺼짐(비용 발생)

### 평가

```bash
python -m eval.runner          # 기계적 검사 + LLM 심판
```

무엇을 재는가: **Builder가 자연어 요구를 옳은 AgentSpec으로 옮기는가.**
생성된 에이전트의 답변 품질이 아니다 — 그건 도구·모델·프롬프트가 뒤섞인 결과라 회귀 신호로 쓰기 어렵다.

| 단계 | 방법 | 대상 |
|---|---|---|
| 기계적 검사 | 코드로 확정 판정 | 도구 선택, 과잉 선택, 팀 구성, 가드레일 |
| LLM 심판 | 5점 척도 + 이유 | `system_prompt`가 요구를 담았는가 |

- 기계적 검사가 깨지면 심판을 부르지 않는다 — 이미 실패한 명세의 문장력을 채점할 이유가 없다
- 심판 판별력은 실측으로 확인했다: 부실 스펙 1/5, 무관 스펙 1/5, 좋은 스펙 5/5
- 케이스는 `eval/cases/*.json`에 있다
- **비용 주의**: 1회 실행 = Builder 호출 21회(케이스 수) + 심판 호출. 프롬프트·도구 레지스트리를 바꿨을 때만 돌린다.
  Builder 시스템 프롬프트에는 프롬프트 캐시를 걸어 두 번째 호출부터 정가의 10%로 읽는다(실측 확인)

---

## AgentSpec v0.3

```json
{
  "spec_version": "0.3",
  "name": "research_team",
  "description": "주제를 조사해 근거가 붙은 브리핑을 만드는 팀",
  "system_prompt": "너는 리서치 팀의 리더다. ...",
  "model": "claude-sonnet-4-6",
  "tools": [],
  "subagents": [
    {
      "name": "researcher",
      "description": "웹 검색으로 사실을 조사해 출처와 함께 돌려준다",
      "system_prompt": "너는 조사 담당이다. ...",
      "tools": ["web_search"],
      "model": "claude-haiku-4-5"
    }
  ]
}
```

- `tools` 허용값: `web_search`, `python_repl`, `file_read`, `file_write`, `file_list` (그 외는 거부)
  - **팀원의 `tools`도 같은 검증을 받는다** — 위임이 화이트리스트 우회 경로가 되지 않는다
- `mcp:<server>`는 `mcp_servers.json`에 **설정된 서버명일 때만** 통과한다 (오타가 런타임까지 흘러가지 않는다)
- `subagents`는 최대 5개, 이름 중복 금지, 계층 깊이 1 (팀원은 다시 팀을 거느릴 수 없다)
- 팀원의 `model`은 **선택**이다. 비우면 리더 모델을 상속하므로 v0.2 스펙 파일이 그대로 돌아간다

### 팀원 모델을 언제 내리는가 (v0.3)

값싼 모델(`claude-haiku-4-5`)은 **기계적인 일**에만 쓴다 — 검색 결과 수집, 원문 발췌,
형식 변환, 단순 계산. 종합·집필·**검증**은 리더 모델 그대로 둔다
(검산 담당을 값싼 모델로 돌리면 검산이 의미를 잃는다).

> ⚠️ **절감폭은 생각보다 작다.** `doc_qa_team`의 발췌 담당만 내려 실측한 결과
> **11.1%**($0.091 → $0.081)였다. 값싼 모델을 붙였는지가 아니라
> **그 팀원이 전체 작업의 몇 %를 하는지**가 절감폭을 정한다 —
> 이 팀에서는 7회 호출 중 2회뿐이었다.

> ⚠️ **모델 ID는 검증되지 않는다.** 도구 키·MCP 서버명과 달리 자유 문자열이라
> 오타를 적으면 명세는 통과하고 **실행할 때** 죽는다.

허용 도구 목록은 하드코딩이 아니라 `registry`에서 파생된다.
도구를 등록하면 Builder 프롬프트에도 자동으로 반영되므로,
**프롬프트가 광고하는 도구와 밸리데이터가 허용하는 도구가 어긋날 수 없다.**

---

## 팀 템플릿

| 템플릿 | 구성 | 쓰임 | 필요한 키 |
|---|---|---|---|
| `research_team` | researcher(`web_search`) + writer | 주제 조사 → 출처 붙은 브리핑 | Anthropic + Tavily |
| `data_analysis_team` | analyst(`python_repl`) + reviewer(`python_repl`) | 계산 후 **독립 검산** | Anthropic |
| `doc_qa_team` | extractor(`file_read`, **haiku**) + summarizer | 문서 근거를 인용한 질의응답 | Anthropic |

```bash
python cli.py --spec templates/data_analysis_team.json
```

템플릿은 Builder를 거치지 않으므로 가드레일 문장이 파일에 직접 적혀 있다
(`tests/test_templates.py`가 리더·팀원 전원에 대해 강제한다).

---

## 작업공간 (`workspace/`)

`file_read` / `file_write` / `file_list`는 **`workspace/` 안만** 볼 수 있다.

- `..`, `~`, 바깥 절대경로는 차단된다 (`FilesystemBackend(virtual_mode=True)`)
- 가상 루트가 `/`이므로 `workspace/report.md`는 에이전트에게 `/report.md`로 보인다
- `.env`는 이 디렉터리 **밖**(프로젝트 루트)에 있어 접근되지 않는다

```bash
cp ~/some-report.md workspace/
python cli.py --spec templates/doc_qa_team.json
```

> ⚠️ **`workspace/`에 비밀값을 두지 않는다.** 경로 탈출은 막히지만 그 안의 파일은
> 에이전트가 전부 읽는다 — **프로세스 격리가 아니라 경로 제한**이다.
> 웹 검색 도구를 함께 켠 에이전트에게는 여기 있는 내용이 외부로 나갈 경로가 생긴다.

`workspace/`의 사용자 문서는 gitignore 대상이라 실수로 커밋되지 않는다.

---

## MCP 연동 (선택)

외부 MCP 서버의 도구를 에이전트에 붙일 수 있다.

```bash
cp mcp_servers.example.json mcp_servers.json   # 접속 정보를 채운다
```

- 비밀값은 파일에 직접 쓰지 않고 `${ENV_VAR}` 참조로 적으면 로드 시 치환된다
- 스펙에서는 `"mcp:<서버명>"`으로 참조하며, **설정에 없는 서버명은 검증 단계에서 거부**된다
- 연결 확인용 로컬 서버가 포함돼 있다 (`examples/echo_mcp_server.py`)

---

## 개발

```bash
./.venv/Scripts/python.exe -m pytest tests/ -q                    # 전체 235건
./.venv/Scripts/python.exe -m pytest tests/ -q -m "not integration"  # 빠른 피드백
```

- `integration` 마커는 실제 프로세스·Streamlit 앱을 띄우는 느린 검증이다
- 작업 규칙은 [CLAUDE.md](CLAUDE.md) 참조

---

## 알려진 한계

- **제거 불가 도구** — `read_file`과 `task`는 deepagents가 필수 미들웨어로 강제하므로 스펙이 요청하지 않아도 항상 노출된다.
  다만 `task`가 띄우는 general-purpose 서브에이전트는 리더의 제한된 도구를 그대로 물려받으므로 화이트리스트 구멍은 아니다(실측 확인).
- **`python_repl`은 임의 코드 실행이다 — 샌드박스가 아니다.**
  임시 디렉터리에서 실행하고 비밀값 환경변수를 넘기지 않으며 30초에 끊지만,
  `os.system`·`subprocess`·절대경로 파일 접근·네트워크는 여전히 가능하다.
  **`execute`(deepagents 셸 도구)를 차단해도 `python_repl`을 허용한 스펙은 사실상 셸을 허용한 것**이다.
  스펙에 이 도구를 넣는 것은 그 권한을 주는 것과 같다.
- **`workspace/`는 샌드박스가 아니다** — 경로 제한일 뿐 프로세스 격리가 없다. 위 경고 참조.
- **MCP는 호출당 프로세스를 재기동한다** — 어댑터가 연결을 유지하지 않아 stdio 서버는 호출마다 기동 비용을 낸다.
- **MCP 검증 대상은 커넥터이지 임의의 서버가 아니다** — `stdio`·`streamable_http`·`sse` 세 transport를
  실서버로 왕복시켰지만, 상대는 우리가 만든 `examples/echo_mcp_server.py` 하나다.
  다른 구현체의 인증 방식(OAuth 등)·세션 정책·스키마 방언과의 상호운용성은 미검증이다.
- **평가 케이스가 현재 전부 통과한다** — 지금 이 스위트는 이미 고친 결함의 재발만 감지한다.
- **Builder는 결정적이지 않다** — 같은 요구에 한 번은 단일 에이전트, 한 번은 4인 팀이 나온 적이 있다.
  평가는 케이스당 1회만 돌리므로 **"21/21"은 단일 표본**이다.
  안정성을 봐야 할 때는 `run_evaluation(repeats=N)`으로 올린다(그만큼 비용이 는다).
- **팀은 비싸다** — 실측상 2인 팀은 같은 답에 **LLM 호출 3배, 출력 토큰 10배 이상, 지연 5배**를 쓴다.
  Builder가 근거 없이 팀을 만들지 않도록 프롬프트에 이 수치를 넣었지만, 강제가 아니라 지침이다.

전체 목록과 실측 근거는 [BUILD_SPEC.md](BUILD_SPEC.md) 6절에 있다.
