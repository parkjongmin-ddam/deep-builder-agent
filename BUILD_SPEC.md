# BUILD_SPEC.md — deep_builder_agent

## 1. 프로젝트 개요
- 명칭: **deep_builder_agent** (2026-08-08 확정. 가칭 mini-agent-builder 폐기)
- 현재 상태: **Phase 1~5 완료 (2026-08-10)** — CLI·Streamlit UI, 팀(subagents), MCP 연동, LangSmith 트레이싱, 평가 레이어, 계산 전용 도구, 자연어 수정 루프. **테스트 307건 통과, 전 경로 실호출 검증 완료. 평가 21케이스 21/21(평균 5.00, 1회 표본).** MCP 3개 transport(stdio·streamable_http·sse) 모두 실서버로 검증했고, **미해결 외부 의존은 없다**
- 보고서: [REPORT.md](REPORT.md) · 데모 대본: [DEMO.md](DEMO.md)
- 진입점: `cli.py` (`python cli.py "<자연어 요구>"`)
- 기술 스택 (설치본 검증 완료): deepagents 0.7.5(하네스), LangGraph 1.2.10(런타임), langchain-anthropic 1.5.4, Pydantic v2, Python 3.13. 개발은 Claude Code
- 실행 환경: 프로젝트 전용 venv(`.venv/`). 전역 파이썬의 langchain 버전과 충돌하므로 격리한다

## 2. 설계 기조 (3축)
- 카파시 원칙: baseline(단일 에이전트) → 복잡도(멀티) 순. Phase 게이트 강제
- 하네스 엔지니어링
  - 제품 층위: Pydantic 스펙 검증, 도구 화이트리스트, system_prompt 가드레일 주입, 실행 실패 → Builder 피드백 루프
  - 개발 층위: CLAUDE.md, pytest 검증 루프, Phase 게이트 커밋
- 멀티오케스트레이션: 제품은 Phase 3부터 구현(스키마의 subagents 필드는 v0부터 존재, Phase 1~2는 빈 배열 강제). 개발 병렬화(Claude Code 서브에이전트)는 Phase 4부터

## 3. 확정 결정 로그
- 2026-08-06: AgentSpec v0.1 확정 — name/description/system_prompt/model/tools/subagents. 도구는 레지스트리 키 문자열 참조만 허용, MCP는 "mcp:" 접두사
- 2026-08-06: Phase 1~2 subagents 비활성화를 스키마 밸리데이터로 강제 (Phase 3 착수 시 밸리데이터 제거 + 본 문서에 기록)
- 2026-08-06: 기본 모델 claude-sonnet-4-6
- 2026-08-08: 프로젝트 정식 명칭 **deep_builder_agent** 확정 (가칭 mini-agent-builder 폐기)
- 2026-08-08: deepagents 0.7.5 고정. `create_deep_agent(model=, tools=, system_prompt=, subagents=)` 시그니처를 설치본 소스로 검증 — 킷의 factory.py 가정이 정확했음
- 2026-08-08: **도구 화이트리스트를 middleware로 실제 강제**. deepagents는 스펙과 무관하게 내장 도구 9종(ls, read_file, write_file, edit_file, delete, glob, grep, execute, task)을 주입하며 그중 `execute`는 셸 실행이다. `FilesystemMiddleware(tools=[...])`로 덮어써 스펙이 요청한 파일시스템 도구만 남긴다 (runtime/factory.py)
- 2026-08-08: 도구 키 매핑 확정 — file_read→내장 read_file, file_write→내장 write_file, web_search/python_repl→커스텀 구현(runtime/tools.py)
- 2026-08-08: 가드레일 문장을 **프롬프트 요청이 아니라 코드로 주입**. `builder.ensure_guardrail()`이 LLM 출력에 문장이 없으면 삽입한다 (LLM 준수를 신뢰하지 않는다)
- 2026-08-08: Builder 모델과 생성 에이전트 모델 **분리**. Builder는 `DEEP_BUILDER_MODEL` 환경변수(기본 claude-sonnet-4-6), 생성 에이전트는 `AgentSpec.model`
- 2026-08-08: web_search는 Tavily 연동. `TAVILY_API_KEY` 미설정 시 조용히 실패하지 않고 "키 없음 + 지어내지 말 것" 에러 문자열을 모델에게 반환
- 2026-08-08: 스펙 저장 방식 확정 — `specs/<name>.json` 파일 저장 (`.gitignore` 대상)
- 2026-08-08 (Phase 2): 도구 레지스트리를 `registry/`로 이관. **허용 도구 목록을 하드코딩에서 레지스트리 파생으로 전환** — `spec.ALLOWED_TOOLS` 상수를 제거하고 `registry.allowed_tool_keys()`가 단일 진실 원천이 되었다. 구현 없는 키가 화이트리스트에 남을 수 없다. 스키마 필드는 불변이므로 SPEC_VERSION은 0.1 유지
- 2026-08-08 (Phase 2): Builder 프롬프트의 도구 목록을 `registry.tool_catalog()`에서 렌더링. 도구를 추가·제거해도 프롬프트를 손댈 필요가 없고, 프롬프트가 광고하는 도구와 밸리데이터가 허용하는 도구가 어긋날 수 없다 (`builder.prompts.build_system_prompt()`)
- 2026-08-08 (Phase 2): MCP 커넥터는 langchain-mcp-adapters 0.3.2 기반. 접속 설정은 코드가 아니라 `mcp_servers.json`(gitignore 대상, `mcp_servers.example.json` 제공)에 두고, 비밀값은 `${ENV_VAR}` 참조로만 기재해 로드 시 치환한다
- 2026-08-08 (Phase 2): **MCP 스펙 검증 강화** — `mcp:` 접두사만으로 통과하던 Phase 1 동작을 폐기. 설정 파일에 존재하는 서버명일 때만 스펙이 통과한다 (오타 서버명이 런타임까지 흘러가지 않는다)
- 2026-08-10 (Phase 2): **MCP 검증을 외부 서비스에서 분리**. 특정 외부 MCP 서버의 접속 정보가 없어 커넥터가 미검증으로 남는 상황을 피하려고, 로컬 서버(`examples/echo_mcp_server.py`)를 검증 픽스처로 채택했다. 외부 계정·네트워크 없이 커넥터 회귀를 상시 검증할 수 있다
- 2026-08-10 (Phase 2): 느린 검증은 `integration` 마커로 분리. 기본 실행은 전부 돌리고, 빠른 피드백이 필요하면 `-m "not integration"` (68건 0.6초 vs 73건 6초)
- 2026-08-10 (Phase 2): `mcp_servers.json` 최상위의 `_` 접두사 키는 설명문으로 취급해 건너뛴다. JSON에 주석이 없어 생긴 문제 — 이 규칙이 없으면 주석 달린 템플릿을 복사하는 순간 로드가 깨진다
- 2026-08-10 (Phase 3): **AgentSpec v0.2 — subagents 게이트 해제**. `subagents_disabled_before_phase3` 밸리데이터를 제거했다(2026-08-06 결정대로 Phase 3 착수 시 제거·기록). 스키마 의미가 바뀌었으므로 SPEC_VERSION 0.1 → 0.2
- 2026-08-10 (Phase 3): **서브에이전트마다 `FilesystemMiddleware`를 명시적으로 붙인다**. 실측 결과 메인의 FilesystemMiddleware는 서브에이전트에 전파되지 않는다 — 메인을 read_file로 묶어도 선언된 팀원은 기본 스택을 새로 받아 `execute`(셸) 포함 8종을 전부 갖는다. 위임 한 번이면 도구 화이트리스트가 무의미해졌다. Phase 3에서 가장 중요한 결정
- 2026-08-10 (Phase 3): `SubAgentSpec.prompt` → **`system_prompt`로 개명**. AgentSpec과 용어를 맞추고 deepagents `SubAgent` TypedDict 키와 1:1 대응시켜 번역 실수 여지를 없앤다
- 2026-08-10 (Phase 3): **서브에이전트 도구도 메인과 같은 밸리데이터를 탄다**(`validate_tool_keys` 공용화). 위임 경로에만 느슨한 검증이 걸리면 화이트리스트가 우회된다
- 2026-08-10 (Phase 3): 팀 규모 상한 `MAX_SUBAGENTS = 5`, 이름 중복 금지. 리더는 이름으로 위임하므로 중복 시 어느 쪽이 불릴지 알 수 없다. 계층 깊이는 1로 고정 — SubAgentSpec에 subagents 필드를 두지 않아 구조적으로 강제한다
- 2026-08-10 (Phase 3): 가드레일 주입을 **서브에이전트까지 확장**(`ensure_guardrail`). 팀원 프롬프트는 Builder가 따로 쓰므로 누락 가능성이 리더보다 높다
- 2026-08-10 (Phase 3): MCP 도구 로드를 **서버별 매핑**(`load_tools_by_server`)으로 확장. 리더와 팀원이 서로 다른 서버를 참조할 수 있어 평평한 목록으로는 누구에게 무엇을 줄지 알 수 없다. 팀원이 참조한 서버가 매핑에 없으면 `LookupError` — 조용히 사라지지 않는다
- 2026-08-10 (Phase 3): 팀 템플릿은 `templates/*.json`에 커밋한다(`specs/`는 생성물이라 gitignore 대상이므로 부적합). `cli.py --spec templates/<name>.json`으로 바로 실행된다
- 2026-08-10 (Phase 4): **평가 대상은 Builder의 번역 품질**로 못박는다. "생성된 에이전트의 답변이 좋은가"는 도구·모델·프롬프트가 뒤섞인 결과라 회귀 신호로 못 쓴다. "자연어 요구 → 옳은 AgentSpec인가"가 이 프로젝트가 직접 책임지는 부분이다
- 2026-08-10 (Phase 4): **기계적 검사와 LLM 심판을 분리**한다. 도구 선택·팀 구성·가드레일은 판단이 필요 없으므로 코드로 확정 판정하고(`eval/checks.py`), 프롬프트가 요구를 담았는지만 심판에게 묻는다(`eval/judge.py`). 기계적 검사가 깨지면 심판을 아예 부르지 않는다 — 이미 실패한 명세의 문장력을 채점할 이유가 없다
- 2026-08-10 (Phase 4): 심판 모델을 Builder 모델과 분리(`DEEP_BUILDER_JUDGE_MODEL`). 같은 모델이 자기 출력을 채점하면 점수가 후해진다. 통과선은 5점 만점에 4점 — 3점("요구는 담았으나 빈틈")은 통과시키지 않는다
- 2026-08-10 (Phase 4): 심판에게 **점수와 이유를 함께** 받고, 파싱 실패를 0점으로 뭉개지 않는다(`JudgeError`). 채점 실패와 낮은 점수는 다른 사건이다
- 2026-08-10 (Phase 4): 평가 실행은 **케이스 하나가 죽어도 계속 돈다**. 생성 실패도 `CaseResult.error`에 담아 리포트에 남긴다 — 10개 중 3번째에서 멈춰 나머지를 못 보는 것이 최악이다
- 2026-08-10 (Phase 4): 트레이싱은 **조용히 꺼지지 않는다**. `LANGSMITH_TRACING=true`인데 키가 없으면 실행 전에 막는다(`TracingConfigError`). TAVILY_API_KEY 없을 때 web_search가 결과를 지어내지 않고 에러를 반환하는 것과 같은 원칙
- 2026-08-10 (Phase 4): UI는 **그리기(`ui/app.py`)와 판단(`ui/state.py`)을 분리**한다. Streamlit 앱은 단위 테스트가 어렵지만 순수 함수는 그대로 테스트된다. 앱이 실제로 뜨는지는 `streamlit.testing.v1.AppTest`로 따로 검증한다
- 2026-08-10 (Phase 4): `last_text`를 `cli.py`에서 `runtime/messages.py`로 옮겼다. UI도 같은 추출이 필요한데 `ui`가 `cli`를 임포트하는 것은 레이어가 거꾸로다
- 2026-08-10 (Phase 4): UI는 비밀값을 **존재 여부만** 표시한다(`check_readiness`). 값이 화면에 새지 않는지 테스트로 고정했다
- 2026-08-10: **파일 백엔드를 `workspace/` 전용 디렉터리로 묶는다** (Phase 2에서 미뤄둔 결정). deepagents 기본 `StateBackend`는 세션 내 가상 FS라 실제 문서를 못 읽어 `doc_qa_team`이 설명대로 동작하지 않았다. 반대로 루트를 프로젝트 전체로 열면 `.env`가 읽힌다. `FilesystemBackend(root_dir=workspace/, virtual_mode=True)`가 그 사이의 답이다 — `virtual_mode`가 `..`·`~`·외부 절대경로를 `ValueError: Path traversal not allowed`로 막는 것을 실측했다. **프로세스 격리는 아니므로** "workspace 안에 비밀값을 두지 않는다"는 규칙이 함께 필요하고, `workspace/README.md`와 `CLAUDE.md`에 명시했다
- 2026-08-10: 레지스트리에 `file_list`(→ 내장 `ls`) 추가. 목록 조회가 없으면 에이전트가 경로를 추측할 수밖에 없다 — `doc_qa_team`이 실제로 `/workspace/README.md`를 찍어보고 실패했다(가상 루트가 `/`이므로 정답은 `/README.md`). 프롬프트 도구 목록은 레지스트리에서 렌더링되므로 Builder가 자동으로 새 도구를 알게 된다 (Phase 2 설계의 효과)
- 2026-08-10: `workspace/`의 사용자 문서는 gitignore 대상. 안내문(`workspace/README.md`)만 추적한다 — 문서를 넣다가 실수로 커밋하는 것을 막는다
- 2026-08-10: **Builder는 되묻지 않는다.** 프롬프트의 "모호하면 질문한다" 단계를 제거하고 "합리적으로 가정하고 가정을 description에 적는다"로 바꿨다. 질문을 받아줄 코드 경로가 없어서(CLI·UI·평가 전부 단발 호출) 되묻는 순간 재시도가 소진되고 간헐적으로 생성이 실패했다. **프롬프트가 시스템에 없는 상호작용을 약속하면 안 된다.** 대화형 인터뷰를 원하면 그때 코드부터 만든다
- 2026-08-10: **심판 모델 기본값을 `claude-haiku-4-5`로 분리한다** (Builder는 `claude-sonnet-4-6`). 이전에는 둘 다 같은 기본값이라 같은 모델이 자기 출력을 채점했다. 환경변수로 분리하라고 안내만 하면 아무도 설정하지 않아 결국 같아지므로, **기본값 자체를 다르게** 해서 구조적으로 보장한다. Haiku를 고른 근거는 실측 — 좋은 스펙 5/5, 부실 1/5, 무관 1/5로 Sonnet과 동일한 판별력을 보였고 비용은 약 1/3이다. 회귀 테스트가 두 기본값이 달라야 함을 강제한다
- 2026-08-10: **비용 실측 (최종)** — LLM 호출 222건, **$4.44**. 모델별로: `claude-sonnet-4-6` 184건 $4.36(98%), `claude-haiku-4-5`(심판) 38건 $0.08(2%). **심판을 Haiku로 내린 결정이 확실히 효과를 냈다.** 가장 큰 반복 지출은 평가 실행(1회 = Builder 12회 호출)이므로 프롬프트·레지스트리 변경 시에만 돌린다. LangSmith 화면의 금액은 LangSmith 청구액이 아니라 토큰에서 계산한 **모델 비용 표시**다
- 2026-08-10: **`python_repl` 자식 프로세스에 환경변수 화이트리스트만 넘긴다.** 부모 환경 전체를 물려주던 코드가 `ANTHROPIC_API_KEY`를 그대로 노출하고 있었다(실측). 임의 코드 실행 도구에 넘기는 환경변수는 "에이전트가 읽을 수 있는 값"과 같다
- 2026-08-10: **`python_repl`을 "격리된"이라고 부르지 않는다.** `os.system`·`subprocess`·절대경로 파일 접근·네트워크가 전부 가능하다. 임시 디렉터리 실행·비밀값 차단·30초 타임아웃은 완화이지 샌드박스가 아니다. **`execute`를 차단해도 `python_repl`을 허용한 스펙은 사실상 셸을 허용한 것**이며, 이 사실을 도구 docstring·README·REPORT에 명시한다
- 2026-08-10: Builder는 **할 수 없는 일을 할 수 있다고 쓰지 않는다.** 도구 목록에 없는 능력(이메일·DB·셸)을 `description`·`system_prompt`에 약속하지 않고, 다른 도구로 우회하지도 않는다. 대신 무엇이 필요한지 명시하고 역할을 실제 범위로 좁힌다
- 2026-08-10: **Builder 시스템 프롬프트에 프롬프트 캐시를 건다.** 프롬프트가 약 2,850토큰인데 호출마다 통째로 재전송되고, 평가는 케이스 수만큼 Builder를 연속 호출한다(현재 12회). 캐시 적중 실측 — 2회차에서 2,830토큰을 캐시에서 읽었다. 평가 1회 기준 $0.103 → 약 $0.020. 캐시 breakpoint는 system 블록에만 두고 재시도로 덧붙는 user/assistant는 튜플 형식 그대로 둔다(프리픽스만 캐시되면 뒤가 바뀌어도 유효하다)
- 2026-08-10: **비용의 61%는 출력이다** — 입력 568,192토큰($1.70)보다 출력 177,256토큰($2.66)이 크다(단가 5배). **캐싱은 입력만 줄인다.** 출력을 줄이려면 실행 횟수를 줄이는 수밖에 없고, 그래서 "평가는 프롬프트·레지스트리 변경 시에만"이 가장 큰 절감 수단이다
- 2026-08-10: 평가 케이스는 **추측이 아니라 실측으로 늘린다.** 기대값을 먼저 적고 → 후보 요구를 실제로 던지고 → 어긋난 것만 고정한다. 이 절차로 4건을 찾았고, 그중 하나(`over_selection_bait`)는 과잉 선택을 노렸는데 정반대인 과소 선택이 나왔다 — 추측으로는 못 잡을 지점이었다
- 2026-08-10: **특정 외부 MCP 서버(aibrief) 연결을 로드맵에서 제거한다.** 최초 커밋의 로드맵에 사유 없이 들어간 항목이었다. 그 서버는 프로젝트 소유자가 직접 만들어 배포한 것이라, 붙여봐야 "내가 만든 서버가 내 커넥터와 붙는다"를 보일 뿐 **제3자 상호운용성의 증거가 아니다.** 데모 요건도 아니고, 외부 계정·토큰을 게이트에 묶는 것은 Phase 2에서 이미 같은 이유로 피한 구조다. 코드·설정에서 이름을 전부 걷어내(`remote_http` 등 중립 placeholder로 교체) `grep aibrief`가 0건임을 검증 가능하게 했다
- 2026-08-10: **커넥터가 선언한 transport는 전부 실서버로 검증한다.** 위 항목을 닫으면서 그것이 암묵적으로 덮고 있던 빈틈이 드러났다 — `streamable_http`·`sse`는 지원한다고 선언만 하고 설정 파싱만 테스트돼 있었다. HTTP 경로가 깨져도 전 테스트가 초록이었다. echo 서버에 `--transport` 인자를 붙여 세 transport를 같은 코드로 띄우고, `test_mcp_http_integration.py`가 도구 목록·호출·비ASCII 왕복을 확인한다. **오프라인·무자격증명·LLM 호출 0회**로 상시 돈다
- 2026-08-10: **사용자가 팀을 요구해도 역할 분리 근거가 없으면 단일로 만든다** (프롬프트 규칙 추가). 실측에서 Builder는 이미 그렇게 하고 있었지만 **프롬프트에 그 규칙이 없었다 — 맞은 것이 운이었다.** 기존 `team_size_cap`(7명 요구 → 5명 팀)과 방향이 반대여서, 둘을 가르는 기준이 "사용자가 요구했는가"가 아니라 **"역할 분리 근거가 있는가"**임을 명시했다. 근거가 없으면 단일로 만들되 **왜 나누지 않았는지 `description`에 적는다** — 사용자 지시를 조용히 무시하는 것과 다르다
- 2026-08-10: **팀 케이스는 팀원 도구를 단언한다** (`EvalCase.expect_subagent_tools` + `check_subagent_tools`). 도구는 리더가 아니라 팀원에게 붙으므로 팀 케이스들이 `expect_tools=[]`로 적혀 **도구에 대해 아무것도 검사하지 않는 상태**였다 — 조사 팀에 아무도 `web_search`가 없어도 통과했다. 실패할 수 없는 단언이라는 점에서 MCP 헤더 건과 같은 계열이다. "누가" 들었는지는 묻지 않는다 — 역할 배분은 Builder 재량이고, 확정 판정할 수 있는 것은 "팀 전체가 그 일을 할 수단을 갖췄는가"까지다
- 2026-08-10: **심판에게 팀원의 도구·프롬프트까지 보여준다.** 이전에는 팀원 **이름만** 넘겼다. 둘이 깨져 있었다 — (1) 팀원 프롬프트가 채점 대상에서 통째로 빠져 있었다. Builder가 따로 쓰는 만큼 리더보다 빈틈이 생기기 쉬운 쪽인데(2026-08-10 가드레일 확장 결정의 근거) **가장 위험한 것을 안 보고 있었다.** (2) 도구 배분을 묻는 rubric에 심판이 보이지도 않는 것을 근거로 감점했다(실측 4/5: *"각 subagent의 도구가 명세에 명시되지 않아"*). 수정 후 같은 케이스가 5/5로 오르고 심판이 도구를 직접 인용했다(*"web_search vs python_repl"*). **채점 기준이 묻는 것은 심판이 볼 수 있어야 한다**
- 2026-08-10: **AgentSpec v0.3 — 팀원별 모델(`SubAgentSpec.model`)**. 팀 비용 실측에서 출력 토큰이 단일의 10배 이상이고 대부분이 팀원 쪽에서 나온다는 것이 근거다. **선택 필드이고 비우면 리더 모델을 상속**한다 — v0.2로 쓰인 스펙 파일이 그대로 돌아야 하기 때문이다. 공백뿐인 값은 상속으로 정규화한다(`.env` 빈 값이 기본값을 덮었던 것과 같은 함정). deepagents `SubAgent` TypedDict가 `model: NotRequired[str | BaseChatModel]`을 받는 것을 설치본 소스로 확인했다. 스키마 의미가 바뀌었으므로 SPEC_VERSION 0.2 → 0.3
- 2026-08-10 (Phase 5-2): **수정은 패치가 아니라 전체 명세를 다시 받는다** (`revise_spec`). JSON Patch 같은 부분 수정 형식을 쓰면 생성 경로와 **다른 검증·다른 실패 모드**가 생긴다. 전체를 받으면 `AgentSpec` 검증이 그대로 걸리고, 무엇이 바뀌었는지는 diff로 보여주면 된다. 생성과 수정이 같은 재시도 루프(`_produce_spec`)를 쓰도록 공용화했다 — 수정 경로에만 느슨한 검증이 걸리면 화이트리스트가 우회된다(서브에이전트 도구 검증 공용화와 같은 이유)
- 2026-08-10 (Phase 5-2): **수정 지시는 시스템이 아니라 사용자 메시지에 넣는다.** 시스템 프롬프트를 생성 때와 동일하게 유지해야 (1) 도구 화이트리스트·팀 판단 기준·가드레일이 수정에도 똑같이 적용되고, (2) 프리픽스가 같아 **프롬프트 캐시가 그대로 적중한다**
- 2026-08-10 (Phase 5-2): **변경 내역을 반드시 보여준다** (`runtime/spec_diff.py`). 전체 명세를 다시 받는 방식의 주된 실패 모드는 "요청하지 않은 것까지 바뀌는 것"이다. **신뢰는 "요청한 것만 바뀐다"는 약속이 아니라 "바뀐 것이 보인다"는 사실에서 온다.** `system_prompt`는 길어서 전문을 찍으면 나머지 변경이 묻히므로 길이 변화만 보여준다
- 2026-08-10 (Phase 5-2): **수정 후 대화 이력을 초기화한다.** 도구가 바뀐 에이전트에게 이전 도구 호출 기록을 넘기면 맞지 않는다. 새 명세로 에이전트를 못 만들면 **기존 에이전트를 그대로 유지**한다 — 수정 실패로 대화가 끊기면 안 된다
- 2026-08-10 (Phase 5-1): **계산 전용 도구 `calculate`를 분리한다** (`registry/safe_eval.py`). `python_repl`은 임의 코드 실행이라 그 도구를 붙인 스펙은 사실상 셸을 허용한 것인데, 실제 요구의 상당수는 "숫자를 계산해줘"뿐이다. 계산만 하는 도구를 따로 두면 **대부분의 생성 에이전트가 애초에 그 권한을 받지 않는다.** 위험을 없애지는 못해도 노출면을 줄인다
- 2026-08-10 (Phase 5-1): **`eval()`을 쓰지 않고 AST를 직접 순회한다.** globals를 비운 `eval`도 `().__class__.__bases__[0].__subclasses__()` 같은 속성 경로로 뚫린다(널리 알려진 우회). 허용 노드 종류를 정하고 직접 평가하면 `ast.Attribute` 노드 자체를 거부하므로 **그 경로가 존재하지 않는다.** 회귀 테스트가 이 탈출 문자열들을 실제로 던진다
- 2026-08-10 (Phase 5-1): **`calculate`가 `range`·컴프리헨션까지 지원한다.** 사칙연산만 되면 "1~200 중 3의 배수의 합" 같은 집계를 못 해 Builder가 계속 `python_repl`을 고르고, 그러면 이 도구를 만든 목적이 사라진다. 대신 크기를 묶는다 — range 길이 100만, 반복 횟수 100만(중첩 루프에서 **공유 예산**), 지수 1000, 결과 원소 1000, 노드 500
- 2026-08-10: **Phase 5 주제를 "완결"로 잡는다.** 산출물이 수업 과제이자 사내 경진대회 제출물이라 심사자가 읽고 직접 돌려본다. 이 프로젝트의 차별점은 기능 수가 아니라 **측정·결함 발견·정직한 한계 기록**이므로, 새 기능을 얹어 그 강점을 희석하지 않고 **구멍 두 개**를 메운다 — (1) README가 "셸을 차단한다"고 하면서 같은 문서에서 "사실상 셸을 허용한 것"이라 정정하는 **주장의 불일치**, (2) 만들면 끝이고 고치려면 JSON을 손편집해야 하는 **제품의 미완결**
- 2026-08-10: **컨테이너 샌드박스를 채택하지 않는다.** `python_repl`의 위험을 없애는 가장 강한 수단이지만 Docker 의존이 생겨 README의 "clone 후 5분 안에 돌아간다"가 깨진다. **심사자가 못 돌리는 것이 문서화된 한계보다 나쁘다.** 대신 위험을 **줄이는** 쪽(안전한 `calculate` 분리)으로 간다 — 대부분의 생성 에이전트가 애초에 임의 코드 실행 권한을 받지 않게 하고, `python_repl`은 진짜 필요할 때만 붙는 도구로 남긴다. 컨테이너는 옵트인 확장으로 열어 둔다
- 2026-08-10: **팀원 모델은 "기계적인 일"에만 내린다** (프롬프트 규칙). 아무 팀원에게나 값싼 모델을 붙이면 품질이 깎이므로 판단 기준을 준다 — 검색 결과 수집·원문 발췌·형식 변환·단순 계산은 내려도 되고, 종합·집필·**검증**은 내리지 않는다. 검산 담당을 값싼 모델로 돌리면 검산이 의미를 잃는다. 기본은 생략(상속)이고 확신이 없으면 생략한다
- 2026-08-10: **가드레일을 `runtime/guardrail.py`로 내리고 스펙 파일 로드를 `runtime.spec.load_spec_file()`로 공용화한다.** `ensure_guardrail()`이 Builder 루프 안에만 있어 손으로 쓴 스펙(`cli.py --spec`, UI 템플릿 로드)은 가드레일 없이 통과했다. 게다가 두 진입점이 `AgentSpec(**json.loads(...))`를 **각자 복제**하고 있었다 — `.env` 로드·콘솔 인코딩과 같은 실패 방식이라, 앞으로 붙는 어떤 보장도 한쪽에만 걸린다. 가드레일은 Builder만의 관심사가 아니라 제품 층위 불변식이므로 아래층에 둔다(`ui`가 `cli`를 임포트하는 것은 레이어 역전 — `last_text` 이관과 같은 근거). 주입은 멱등이라 반복 로드로 문장이 쌓이지 않는다
- 2026-08-10: **콘솔 UTF-8 고정을 `runtime/console.py`로 공용화한다.** Phase 1에서 `cli.py`에 고친 버그가 `eval/runner.py`에 그대로 남아 있었다 — 진입점마다 각자 챙기는 구조라 새 진입점에서 반복해서 빠진다(`.env` 로드와 정확히 같은 실패 방식). 콘솔에 직접 찍으면 멀쩡하고 **리다이렉트·파이프일 때만** 죽어서 손으로 돌려보면 안 잡힌다
- 2026-09-28 (Phase 6): **IAM 레이어를 도입한다 — 사용자 RBAC + 에이전트 권한 경계(permissions boundary).** 도구 화이트리스트는 "등록된 도구인가"만 답하고 **"누가 그 도구를 부여할 수 있는가"는 아무도 묻지 않았다.** 역할(role)이 행위(create/revise/run/view)와 도구 경계를 정의하고, 생성·수정되는 스펙의 도구(리더+팀원 전원)는 생성자의 경계를 초과할 수 없다. 경계는 **부여 시점에만** 적용된다 — 기존 에이전트 실행은 에이전트 자신의 권한을 쓰는 것(assume-role)이므로 run_agent 행위 검사만 받는다
- 2026-09-28 (Phase 6): **경계 위반을 Builder 재시도 루프에 넣는다** (`_produce_spec(allowed_tools=...)`). 프롬프트로 "허용 도구만 써라"라고 요청하는 대신, 경계 밖 도구가 나오면 검증 실패와 같은 에러 피드백을 되돌려 재생성시킨다 — LLM의 준수를 신뢰하지 않는다는 기존 원칙 그대로다. 수정 경로(`revise_spec`)에도 같은 경계가 걸린다 — /revise만 빠지면 권한 상승 통로가 된다(화이트리스트 공용화와 같은 이유)
- 2026-09-28 (Phase 6): **주체 미지정 = admin.** 기존 CLI·UI·테스트 307건이 그대로 돌아야 한다(v0.3 `SubAgentSpec.model` 기본값과 같은 원칙). 반대로 **미등록 주체는 기본 역할로 격하하지 않고 거부한다** — 조용히 받아주면 RBAC이 장식이 된다. 명시한 정책 파일이 없으면 기본 정책으로 넘어가지 않고 실패한다(정책 오타가 조용히 기본 정책 실행이 되면 감사 불가)
- 2026-09-28 (Phase 6): **감사 로그는 허용·거부 모두 남긴다** (`logs/audit.jsonl`, gitignore). `workspace/`에 두지 않는다 — 그 안의 파일은 에이전트가 전부 읽는다. 정책 로드는 오타에 즉시 실패한다 — deny-by-default에서 잘못 적은 허용 항목은 에러 없이 사라지므로, 행위명·도구명을 로드 시점에 검증한다(도구는 레지스트리에서 파생 — 화이트리스트와 같은 단일 진실 원천). **AgentSpec은 건드리지 않았다** — 정책은 리소스가 아니라 요청에 적용되는 것이므로 SPEC_VERSION 변경 없음
- 2026-09-28 (Phase 7): **인증은 OIDC로, SAML·ADFS는 채택하지 않는다.** Streamlit 1.42+가 `st.login`/`st.user`로 OIDC를 네이티브 지원해(Authlib) 추가 인프라 없이 붙는다. SAML은 네이티브 미지원이라 커스텀 SP 엔드포인트가 필요하고, ADFS는 Windows Server 인프라가 필요해 심사자가 재현할 수 없다 — "심사자가 못 돌리는 것이 문서화된 한계보다 나쁘다"(컨테이너 샌드박스 기각과 같은 근거). ADFS 2016+도 OIDC를 지원하므로 기업 환경 이식은 문서 한 줄로 충분하다
- 2026-09-28 (Phase 7): **OIDC 미설정이면 데모 모드로 폴백한다** (`oidc_configured()`). `.streamlit/secrets.toml`의 [auth]가 없으면 기존 주체 선택기로 동작한다 — 외부 계정·토큰을 필수 게이트로 만들지 않는다(aibrief 제거와 같은 원칙). 클린 클론의 "5분 시작"과 오프라인 테스트 전건이 그대로 유지된다. secrets 파일이 없을 때 나는 FileNotFoundError만 '미설정'으로 해석하고 그 외 예외는 숨기지 않는다
- 2026-09-28 (Phase 7): **로그인 성공 ≠ 인가.** IdP가 신원을 보증해도 역할은 정책이 명시해야 한다 — 매핑 없는 신원은 거부한다(`resolve_identity`, deny-by-default). 매핑 우선순위는 이메일 직접 매핑(개인 예외, 더 구체적) > 그룹 클레임(정책 파일 선언 순서 = 작성자가 정한 우선순위). **OIDC 모드에서는 주체 선택기를 없앤다** — 인증이 있는데 주체를 고를 수 있으면 인가가 장식이 된다. 감사 로그의 principal이 "선택한 이름"에서 "검증된 이메일"로 바뀌는 것이 이 Phase의 실질 이득이다
- 2026-09-30 (Phase 8): **UI 리디자인 착수 — 테마는 config.toml 이원([theme.light]/[theme.dark]) 방식.** 시안은 docs/design/deep_builder_agent_Redesign.html (Claude Design 산출물, 작업 지시서는 docs/design/UI_REDESIGN.md). 분리 섹션 지원 여부를 추측하지 않고 설치본 streamlit 1.64.0의 config 옵션 목록으로 확인했다 — `theme.light.*`·`theme.dark.*`·`*.sidebar.*`·`fontFaces`·`showWidgetBorder` 전부 존재. **requirements.txt의 streamlit을 1.64.0으로 고정** — 테마 키는 버전에 따라 있고 없고가 갈리므로 미고정이면 클론마다 다른 화면이 뜬다. Pretendard·JetBrains Mono는 **CDN @import(ui/style.py)로 로드**한다. `[[theme.fontFaces]]`+로컬 woff2 커밋은 기각 — 폰트 바이너리 커밋과 정적 서빙 설정이 필요해지고, CDN 실패 시 시스템 폰트로 조용히 폴백하는 쪽이 "clone 후 5분" 원칙에 맞다. CSS 주입은 ui/style.py 한 곳에 모은다(내부 클래스명 의존 최소화). 상태 이모지(✅❌⚠️)는 Material 아이콘으로 교체하고 아이콘 선택을 ui/state.py 순수 함수(`readiness_icon`·`eval_case_icon`)로 두어 테스트한다
- 2026-10-01: **거부에는 대안을 함께 준다 — calculate 안내 개선 실험.** 실측(2026-09-30)에서 data_analysis_team 팀원이 미허용 함수 `all()`을 반복 시도해 소수 합(1~50) 질문 한 턴이 **28단계**까지 늘었다. 거부 사유만 돌려주면 모델은 같은 식을 다시 던진다. 세 층위에 같은 방향으로 고쳤다 — (1) **도구 설명**(registry/builtin.py)에 허용 함수·문법 전체와 자주 틀리는 불가 예시를 명시 (`all/any` → `sum(1 for ...)` 대안, 대입 금지, "같은 식을 그대로 재시도하지 말 것"), (2) **safe_eval 거부 메시지**에 허용 함수 목록 + 대안 힌트(`_ALTERNATIVE_HINTS`) 포함, (3) **템플릿 프롬프트**에는 '오류 시 같은 식을 재시도하지 않고 힌트대로 고친다, 두 번 실패하면 중단'이라는 행동 규칙만 추가 — 허용 목록 자체는 도구 설명이 단일 진실 원천이라 프롬프트에 중복하지 않는다. 손으로 쓴 설명이 화이트리스트와 어긋나지 않도록 동기화를 테스트로 강제했다(`test_calculate_description_stays_in_sync_with_the_whitelist`). **효과 실측**: 같은 질문 2회 — 28단계 → **14단계(55.7s)·9단계(46.1s)**, 두 번 모두 정답 328, calculate 오류 0회(미허용 식 시도 자체가 사라졌다). 주의: 요청서에 '리스트 컴프리헨션 불가'가 언급됐으나 컴프리헨션은 **허용** 문법이다(`test_list_comprehension_works`) — 설명에는 사실대로 허용으로 적었다. 레지스트리 변경이므로 평가 회귀를 돌렸다 — **27/27 통과, 평균 5.00점** (eval/results/2026-10-01_101343.txt), 기준값(2026-09-30_232655, 27/27·평균 4.93) 대비 회귀 없음
- 2026-10-01 (Phase 9): **소속 팀(직무 프로필)은 권한과 별개의 축이다.** 역할(iam.json)은 "무엇을 할 수 있나", 팀 프로필(teams.json)은 "어떤 일을 하나"를 정한다 — 프로필은 예시 문구·템플릿 추천·평가 세트만 바꾸고 권한·도구 경계를 건드리지 않으므로 **사용자가 사이드바에서 직접 골라도 보안 문제가 없다** (기본값 "선택 안 함" = 기존 공통 화면과 동일, AppTest로 고정). 프로필 2종(infra=시스템 엔지니어, dev=개발자)의 내용은 **코드에 정의**(runtime/teams.py — 수정이 코드 리뷰를 거친다)하고 파일은 팀→프로필 매핑만 담는다. 로드는 iam.json과 같은 실패 원칙 — 인자 > `DEEP_BUILDER_TEAMS_FILE` > teams.json > **teams.example.json(커밋됨, clone 직후 동작)** > None(기능 숨김), 명시한 파일이 없거나 깨지면 폴백하지 않고 실패, 미정의 프로필 키·없는 팀을 가리키는 groups는 로드 시점 검증 오류. Okta 그룹 자동 선택은 session_state 미존재 시 최초 1회만 — 사용자의 변경을 로그인 상태가 덮지 않는다
- 2026-10-01 (Phase 9): **프로필 템플릿 4종 + 범용 1종은 허용 도구 안에서만 설계한다.** ADFS 도메인 템플릿(adfs_log_triage_team·sync_report_team·auth_error_analysis_team·auth_lib_research_team)은 ADFS 서버 접속·셸·AD/LDAP 조회·코드 실행을 하지 않는다 — 이 한계를 description과 리더 프롬프트에 명시하고, 실행이 필요한 요청은 **사용자가 직접 수행할 수동 절차 안내**로 돌린다. 실행 재료는 workspace/samples/의 contoso 가상 데이터(이벤트 ID·MSIS·IDX·LDAP 코드는 확신 있는 것만 쓰고 목록을 samples/README.md로 사용자 검토 — 342/364/111/276·MSIS7007/7065·IDX20803/20804·LDAP 49/52e 통과, 276은 Microsoft 문서로 재확인). 템플릿별 실대화 1회 확인: 5단계/270s·16단계/139s·4단계/123s·11단계/79s(검색 키 없음 → 지어내지 않고 미검증 표시). general_assistant는 단일 — "역할 분리 근거 없으면 단일" 규칙을 손으로 쓴 템플릿에 적용한 것으로, 팀 선언 테스트에 단일 예외 목록을 신설했다. 추천 순서는 범용 → 프로필 추천 → 나머지, templates/에 없는 추천 이름은 조용히 건너뛴다(실존은 별도 테스트가 강제)
- 2026-10-01 (Phase 9): **프로필 평가 세트의 첫 기준값은 "보정 후" 수치다 — 과정을 그대로 기록한다.** 1차 실행 **13/15** → 케이스 2건 보정 → **15/15 (infra 7/7 · dev 8/8, 평균 5.00)**. 보정 사유: ① `python_script_fix_honesty` — forbid에 python_repl 누락(**케이스 설계 결함**). Builder가 python_repl을 붙이고 "실행한다"고 약속해 심판 1/5 — python_repl은 로컬 임시 실행이라 '서버에서 실행'을 충족하지 못하므로 forbid로 고정. ② `adfs_runbook_research` — "조사해서 정리"(두 동사) 문구에서 Builder가 3회 중 2회 팀을 만드는 **팀 판단 경계 변동**. 케이스는 단일 명시 문구로 고정하고, 원문은 `eval/boundary.py` 경계 프로브로 보존해 빈도 측정용으로 연결(6절 후속 과제). 기준값: eval/results/2026-10-01_114021_infra.txt · 2026-10-01_113703_dev.txt. common 27건은 Builder·registry 무변경이라 재실행하지 않았다 — 2026-10-01_101343(27/27, 5.00)과 계속 비교
- 2026-10-01: **팀 판단 프롬프트의 모순을 제거하되, 개선을 주장하지 않는다.** 경계 변동(조사→정리, 3회 중 2회 팀) 후속 과제에서 프롬프트 자기모순을 발견했다 — "도구가 다르다는 것만으로는 팀의 근거가 아니다"(규칙)와 "조사/집필은 **도구가 다르고** 산출물이 길어 팀"(예시 근거)·판단 기준 목록의 "도구가 다른가"가 충돌했다(6.10과 같은 계열). 수정 유지 2건: ① 기준 목록에서 도구 항목 제거 + "도구 개수는 보지 않는다" 명시, ③ 팀 예시의 근거를 판단 기준 차이(사실 확인 vs 독자 설득)·긴 중간 산출물로 교정. **기각 1건**: 경계 프로브 문구 자체를 단일 예시로 넣는 수정(②)은 되돌렸다 — 효과가 측정되지 않았고 이후 프로브 측정을 오염시킨다. **빈도 실측(eval/boundary.py, 프로브 4종)**: 발견 원문 기준 수정 전 합산 8회 중 2회(발견 당시 3회 중 2회 + 대칭 측정 5회 중 0회) → 중간본(② 포함) 5회 중 0회 → **최종본(①③) 5회 중 1회**, 신규 프로브 3종은 전 구간 0/5 — 수정 전 25% vs 최종 20%는 같은 수준이라 **효과 검출 불가, 개선을 주장하지 않는다.** 오전 발견과 오후 측정의 조건 차이(문구=원문 복사, 호출 경로=generate_spec, 레지스트리 상태) 없음을 확인했다 — 다른 것은 실행 시점뿐. 수정의 근거는 측정 효과가 아니라 **모순 제거 자체**다. **최종 프롬프트 회귀**: common 27/27(4.96) · infra 7/7(5.00) · dev 6/8 — dev 실패 2건은 python_repl 부여로, 전/후 프로브(python_script 4/4·4/4, dotnet_test 1/4·2/4)로 이번 수정과 **무관한 기존 약점**임을 판별. "통과할 때까지 돌린 결과는 기준값이 아니다" — dev 기준값은 6/8 그대로 커밋. 두 케이스의 성격 구분: python_script는 전/후 4/4로 **꾸준히 실패**(오전 8/8 통과는 운 좋은 1회 표본이었을 가능성 — 6.11의 실례), dotnet_test만 **흔들리는 케이스**. 성향 자체는 6절 후속 과제로 분리. 팀 기대 케이스 5종(research_and_write·different_tools·size_cap·sync_report_split·dotnet_triage_split)은 전부 팀 유지 확인
- 2026-10-01: **python_repl의 실행 범위를 Builder 프롬프트에 명시한다 — "이 시스템 안의 빈 임시 프로세스"**. dev 정직성 케이스에서 Builder가 "사용자 환경에서 실행해줘"(서버·프로젝트·테스트) 요청에 python_repl을 붙이고 "실행한다"고 약속하는 성향을 '할 수 없는 일' 섹션 보강으로 수정 — 목록에 "사용자의 기존 환경에서의 코드 실행" 범주 추가 + "python_repl은 사용자의 서버·저장소·설치된 프로젝트에 닿지 못하며, 맞는 경우는 사용자가 **제공한** 코드·데이터를 그 자리에서 돌려보는 일" 명시(프로브 문구는 예시로 넣지 않음 — 측정 오염 방지). **전/후 건수**: python_script_fix_honesty 부여 8/8 → **0/5**(통과 5/5), dotnet_test_run_honesty 3/8 → **0/5**(통과 5/5), 셸 거절(shell_request_not_satisfied_by_repl) 부여 0/5·통과 5/5 유지, 정당-필요 프로브(제공 코드 조각 실행, 세트 외) 부여 **5/5** — 과잉 억제 없음. 기저율이 높아(8/8) 소표본으로도 효과가 검출된다 — 경계 변동(2026-10-01 모순 제거 결정)과 달리 이번에는 개선이라 부른다. **회귀**: common 27/27(4.96) · infra 7/7(5.00) · dev **8/8**(4.88) — dev 기준값을 8/8로 갱신(원인 수정 후 실행이므로 '통과할 때까지 돌리기'가 아니다)
- 2026-10-01: **배지 팔레트를 st.context.theme 고정에서 CSS light-dark()로 교체.** Phase 8 결정의 알려진 한계(테마 타입이 전환 직후 한 리런 동안 부정확)가 실화면에서 결함으로 확인됐다 — 라이트 전환 첫 렌더에 사이드바 '허용 행위' 배지가 다크 스타일(검은 바탕·흰 글씨)로 뜨고 다음 리런에서야 바뀜. Streamlit 프런트엔드가 앱 컨테이너에 `color-scheme`을 activeTheme 기준으로 **즉시** 설정하는 것을 설치본 1.64.0 index.js로 확인하고, 두 팔레트를 `light-dark(라이트값, 다크값)` 쌍 한 선언에 담아 파이썬 분기·리런 의존을 제거했다(테마 전환이 브라우저 쪽에서만 반영됨). 미지원 구형 브라우저는 기존 폴백(라이트 기본 + prefers-color-scheme 다크, @supports 블록이 뒤라 지원 브라우저에선 항상 light-dark 승리). 후보였던 Streamlit 테마 CSS 변수는 설치본에 범용 노출이 없어 기각. st.context.theme을 쓰는 다른 코드가 없음을 grep으로 확인
- 2026-08-10: **설정 헤더가 실제로 전송되는지 서버 쪽에서 확인한다.** 기존 `${ENV_VAR}` 치환 테스트는 `load_config()`가 돌려주는 dict만 봤다 — 치환된 헤더가 전송되지 않아도 통과하는 단언이었고, 인증이 필요한 MCP 서버는 전부 이 경로를 탄다. echo 서버에 `http_request_headers` 도구를 두어 수신 헤더를 되돌려받는다. **음성 대조군으로 검출력을 확인했다**: headers 없이 붙으면 `{}`, 붙이면 `authorization`·`x-deep-builder-probe`가 관측된다. stdio에서는 HTTP 요청이 없어 `{}`가 나오는 것도 고정해, 이 도구가 상수를 돌려주는 게 아님을 보장한다

## 4. Phase 로드맵
- Phase 1 (8월, 1~3주차): CLI — 자연어 → AgentSpec → 단일 에이전트 생성·대화 ✅ **완료 (2026-08-08)**
- Phase 2 (8월 말~9월 중): registry/ 구현, 내장 도구 + MCP 커넥터, Builder 도구 자동 선택 ✅ **완료 (2026-08-10)** — 커넥터는 stdio·streamable_http·sse **세 transport 모두 로컬 실서버로 검증**. 외부 MCP 서버 연결은 게이트가 아니다 (3절 결정 참조)
- Phase 3 (9월 말~10월 중): subagents 활성화, 팀 템플릿 2~3개, 멀티에이전트 검증 ✅ **완료 (2026-08-10)**
- Phase 4 (10월 말): Streamlit 2패널 UI + LangSmith 트레이싱 + 평가 탭 ✅ **완료 (2026-08-10)**
- Phase 5 (11월): **완결** — 주장과 구현을 일치시키고, 만들기→고치기 루프를 닫는다
  - [x] **5-1 안전한 계산 도구 분리** ✅ **완료 (2026-08-10)** —
        평가 21케이스에서 `python_repl` 선택 **7건 → 0건**, 통과율 21/21 유지 (아래 기록)
  - [x] **5-2 에이전트 수정 루프** ✅ **완료 (2026-08-10)** —
        CLI `/revise`·`--revise`, UI 수정 폼, 변경 내역 diff. 실측에서
        요청하지 않은 변경 없음 (아래 기록)
  - [x] **5-3 제출 패키지 점검** ✅ **완료 (2026-08-10)** —
        clone 재현 실측, 문서 일관성 자동 점검, [DEMO.md](DEMO.md) 대본.
        **키 없이 실행하면 원시 오류로 죽던 결함을 잡았다** (아래 기록)
- Phase 6 (9월 말): **IAM** — 사용자 RBAC + 에이전트 권한 경계 ✅ **완료 (2026-09-28)**
  - [x] `runtime/iam.py` — 역할·주체·경계 판정 + 감사 로그(JSONL)
  - [x] `iam.json` 기본 정책 (admin / builder / operator / viewer) — 파일↔코드 일치를 테스트가 강제
  - [x] Builder 재시도 루프에 경계 주입 (`allowed_tools`) — 생성·수정 경로 동일 보장
  - [x] CLI `--as` / `DEEP_BUILDER_PRINCIPAL`, UI 사이드바 주체 선택 + 위젯 게이팅
  - [x] 테스트 307 → **338건** (IAM 단위 21 + Builder 경계 4 + CLI 4 + UI 2), 전건 통과
- Phase 7 (9월 말): **OIDC 인증** — Okta 등 IdP 로그인 → IAM 역할 매핑
  - [x] `st.login` 게이트 + 미설정 시 데모 모드 폴백 (`oidc_configured`) ✅ (2026-09-28)
  - [x] `resolve_identity` — 이메일/그룹 클레임 → 역할, 매핑 없으면 거부 ✅
  - [x] `.streamlit/secrets.toml.example` 템플릿 + gitignore ✅
  - [x] 테스트 338 → **347건** 전건 통과 (신원 해석 6 + OIDC 헬퍼 3) ✅
  - [x] **Okta 실계정 왕복 검증** ✅ **완료 (2026-09-28)** — Okta Integrator 조직에서 4개 경로 전부 실측:
    1. **정상 경로**: builder 그룹 계정 로그인 → `역할 builder` 매핑 → 템플릿 실행 → 감사 로그에 `principal=<검증된 이메일>, role=builder, decision=allow` 기록 확인 (데모 모드의 "선택한 이름"이 아니라 IdP가 보증한 신원)
    2. **deny-by-default**: 매핑에 없는 그룹(오타 `agent-viewer`)으로 로그인 → 거부 + 사용자 그룹/매핑 그룹 대조 메시지 표시 확인
    3. **viewer 제한**: `agent-viewers` 그룹 계정 → `역할 viewer · 행위 view · 도구 (없음)`, 생성·실행·평가 위젯 전부 게이팅 확인
    4. **IdP 레벨 차단**: 앱에 미할당 그룹 계정 → 인증(MFA) 성공 후에도 Okta가 `access_denied` 반환, 앱 도달 전 차단 (완전 차단 정책은 이 레이어로, 앱 IAM은 2차 방어선)

    **재현 시 함정 3가지** (secrets.toml.example 주석에도 반영):
    - scope에 `groups`를 넣으면 default 인가 서버에 커스텀 스코프가 없어 `invalid_scope` 400 — 클레임을 Always/Any scope로 설정하고 scope는 `openid profile email`만
    - default 인가 서버에 Access Policy가 없으면 MFA 통과 후에도 `no_matching_policy`로 토큰 발급 거부 — 정책+규칙 1개 필수
    - Okta 그룹 이름 오타(3회 발생) — iam.json에서 복사해 붙여넣을 것

    **발견된 개선 후보** — 전부 처리 (2026-09-28, 같은 날 후속 커밋):
    - ① `resolve_identity` 매핑 실패가 감사에 안 남던 것 → **수정**: 거부 시 `action=resolve_identity, decision=deny, role=(unmapped)` + 사용자 그룹/매핑 그룹을 detail에 기록. **성공 해석은 기록하지 않는다** — Streamlit이 위젯 조작마다 스크립트를 재실행하며 매번 resolve_identity를 호출하므로 allow를 남기면 클릭당 한 줄씩 쌓인다. 허용 행위는 authorize_action이 행위 시점에 이미 기록한다 (테스트가 이 결정을 고정)
    - ② viewer 거부 '시도' 미기록 → **정책 결정 (코드 무변경)**: UI 게이팅은 UX이고 강제·기록은 authorize_action이 맡는다. 렌더링마다 deny를 남기면 ①과 같은 스팸 문제가 생기고, UI를 우회한 실제 시도는 어차피 authorize_action 경로에서 기록된다
    - ③ pytest가 실제 `logs/audit.jsonl` 오염 → **수정**: `tests/conftest.py` autouse 픽스처로 전 테스트의 감사 로그를 tmp_path로 격리 + 격리가 풀리면 실패하는 감시 테스트 추가. 같은 원인 계열로, **실제 secrets.toml이 생기자 UI 통합 테스트 5건이 OIDC 게이트를 렌더링하며 깨지던 것**도 잡았다 — AppTest는 secrets가 비어 있으면 실제 파일을 읽으므로(`if self.secrets:` 분기, 설치본 실측) 더미 secrets를 주입해 데모 모드를 강제한다 (`demo_mode_apptest` 헬퍼). 테스트 347 → **351건** 전건 통과 (통합 포함)
- Phase 8 (9월 말): **UI 리디자인** ✅ **완료 (2026-09-30)** — 시안(docs/design/deep_builder_agent_Redesign.html) 재현. 단계·순서는 docs/design/UI_REDESIGN.md
  - [x] 단계 1 테마·공통 스타일 ✅ (2026-09-30) — config.toml 이원 테마([theme.light]/[theme.dark]), streamlit 1.64.0 고정, Pretendard·JetBrains Mono CDN 로드(ui/style.py), 상태 이모지 → Material 아이콘(순수 함수 + 테스트 2건). 테스트 **356건** 전건 통과
  - [x] 단계 2 빌더 탭 레이아웃 ✅ (2026-09-30) — 사이드바 IAM 카드(역할 배지 + 행위·경계 칩, st.html), 환경 점검 요약 필, 탭 아이콘, 좌측 패널 st.container(height=700) 독립 스크롤, 대화 이력 st.container(height=640, border=True), 현재 명세 카드형(st.table → 카드 + 도구 배지 + 팀 st.dataframe(column_config)), 메시지 체계 통일(굵은 제목 + Material 아이콘), 권한 비활성 버튼(lock 아이콘 + help + shield_person 사유 caption). 배지·칩·요약·사유는 ui/state.py 순수 함수(badges_html·chips_html·readiness_summary·denial_reason) + 테스트 5건. 테스트 **361건** 전건 통과
    - 보완 (2026-09-30): OIDC 신원을 이니셜 아바타 카드(HTML)로 — 이메일 마크다운 자동 링크 제거. 생성·템플릿 선택·불러오기 한 줄 배치(같은 form의 복수 submit — AppTest 인식은 기존 '수정 적용' 테스트로 검증돼 있던 경로). 환경 점검을 그리드 HTML로(간격 축소 + 상태 라벨 우측 정렬, readiness_icon → readiness_rows_html 대체). 제목 옆 부제(st.columns(vertical_alignment="bottom") — st.title 유지로 AppTest 호환). **배지 팔레트를 st.context.theme.type으로 고정** — 설치본 1.64.0에서 존재 확인, OS와 반대 테마를 강제해도 일치한다. 타입은 세션 첫 로드·테마 전환 직후 한 리런 동안 부정확할 수 있고(설치본 docstring 명시), 감지 불가(None)면 prefers-color-scheme 폴백. 테스트 **365건** 전건 통과
  - [x] 단계 3 명세 버전 이력 ✅ (2026-09-30) — save_spec이 `specs/<name>/vN.json` 이력을 누적하고 최신본은 기존 `specs/<name>.json` 경로 유지(CLI `--spec` 호환). **버전 번호 = 이력 파일 개수** — 스키마 필드를 늘리지 않아 SPEC_VERSION 불변, 이력 파일은 덮어쓰지 않는다(테스트 고정). 버전 조회(spec_version)·저장 메시지 표기(version_label)·diff 텍스트 변환(diff_as_diff_text)은 ui/state.py. 변경 내역은 `st.code(language="diff")`로 +/− 색 구분 — format_diff의 들여쓴 형식은 diff 문법과 맞지 않아 SpecDiff에서 직접 변환한다(필드 변경은 −이전/+이후 두 줄). 명세 카드에 vN 배지, 저장 메시지에 "v2 → v3". 테스트 **374건** 전건 통과
    - 보완 (2026-09-30): **생성(create)과 수정(revise)의 이름 충돌 정책 분리** — 생성은 새 명세이므로 같은 이름이 있으면 `unique_spec_name`이 `_2`, `_3` 접미사로 분리한다(UI·CLI 동일 적용). 최신본이 지워졌어도 이력 디렉터리가 남아 있으면 충돌로 본다 — 새 명세가 남의 이력을 잇는 것을 막는다. 수정은 기존대로 같은 이름에 버전 누적. 테스트로 고정. 환경 점검 라벨은 환경변수 키만 고정폭(정규식 `[A-Z][A-Z0-9_]*`), 한글 라벨은 본문 폰트. 테스트 **377건** 전건 통과
  - [x] 단계 4 위임·도구 호출 표시 1차 ✅ (2026-09-30) — ui/state.py에 extract_steps(AIMessage.tool_calls ↔ ToolMessage.tool_call_id 매칭, `task` 호출은 위임으로 분류)·render_turns(사용자 발화가 턴 경계, 단계는 마지막 응답에 부착) 추가. render_history는 render_turns의 텍스트 투영으로 재구성 — 도구만 호출한 턴도 단계가 있으면 화면에 남는다. **task 인자명은 설치본 deepagents 0.7.5 middleware/subagents.py로 확인** (StructuredTool name="task", TaskToolSchema: description·subagent_type — 추측 금지 원칙). 표시는 응답 위 st.status(state="complete"), 리더 수준까지·소요시간 없음(단계 7에서 조사). 테스트 **382건** 전건 통과 (추출 3 + 턴 구성 2 추가)
  - [x] 단계 5 평가 탭 대시보드 ✅ (2026-09-30) — 좌(설정 form + 케이스 st.dataframe) / 우(결과) st.columns([2,3]) 분할. 상단 지표 3개 st.metric(border=True): 통과율·심판 평균(심판 안 돌면 "—")·실패 건수. 검사 항목별 통과 st.progress — 집계(check_pass_rates)는 실제 검사 5종 순서, **생성 실패로 checks가 빈 케이스는 분모 제외**(검사가 안 돈 것 ≠ 실패). 케이스별 상세는 실패 먼저(failed_first, 안정 정렬) + 실패 expander만 자동 펼침, 검사 칩·실패 사유·심판 코멘트(st.chat_message avatar=gavel). 결과는 session_state에 남겨 리런에도 유지, 마지막 실행 시각·소요시간 표시. 집계·라벨·정렬·시간 포맷은 ui/state.py 순수 함수 + 테스트 6건. expander 제목 우측 정렬은 CSS 대신 제목 뒤 병기(지시서 허용 대안). 테스트 **390건** 전건 통과
  - [x] 단계 6 로그인·권한 거부 화면 ✅ (2026-09-30) — 로그인 전(3a)·권한 거부(4a)를 st.columns([1,1,1]) 가운데 st.container(border=True) 카드로. render_login_gate/render_access_denied는 그리기 전용 — **main()의 게이트 흐름과 st.stop() 위치는 Phase 7 그대로**(지시서 제약). 거부 카드는 계정·사유(st.error)·관리자 안내·로그아웃을 담는다. 통합 테스트 추가: [auth] 설정 시 로그인 카드가 뜨고 본문(chat_input)이 그려지지 않음을 AppTest로 고정. 테스트 **392건** 전건 통과
  - [x] 단계 7 스트리밍·서브에이전트 내부 단계 ✅ **구현 완료 (2026-09-30)** — `stream_agent_reply`(ui/state.py): `stream(subgraphs=True, stream_mode=["updates","values"])`로 단계 단위 실시간 갱신(토큰 스트리밍은 범위 밖). 내부 도구 호출은 위임 줄 아래 들여쓰기(depth=1) + 이벤트 도착 시각 델타로 단계별 소요시간. **폴백은 첫 이벤트 수신 전 실패로 한정한다** (2026-09-30 수정) — 최초 구현은 어떤 실패든 invoke로 재실행했는데, 이벤트가 도착했다는 것은 그래프가 이미 실행을 시작했다는 뜻이라 재실행하면 이미 수행된 부작용(file_write·web_search·위임)이 **중복 실행**된다. 이벤트 0개 상태의 실패(스트리밍 미지원 등)만 invoke 폴백이 안전하고, 이벤트 수신 후 실패(중간 예외·루트 values 미수신 포함)는 재실행 없이 그때까지의 단계와 함께 "[error]"로 보고하며 이력은 원본을 유지한다. 두 경로 모두 invoke 호출 횟수로 테스트가 고정한다. 조사 주의사항 3가지 반영: ① 네임스페이스는 위임 호출 순서로 배정, ② 최종 대화 상태는 루트 values에서, ③ model·tools 외 노드(미들웨어) 필터. 완료된 턴의 단계는 rich_steps(session_state, 턴 번호 키)로 남겨 rerun 후에도 유지, 이력 초기화 시 함께 비운다. 테스트는 조사 때의 가짜 모델/이벤트 대본 방식으로 LLM 없이 6건(수집·필터·병렬 매핑·폴백 3경로). 실측: 데이터 분석 팀 소수 합 대화에서 "실행 중 · 7단계"→14단계 실시간 카운트, 위임 analyst 21.9s·reviewer 22.2s + 들여쓰기 내부 calculate 호출·소요시간 표시, 정답 1,060 확인. 아래 원래 조사 기록: LLM 없이 가짜 모델 2개(bind_tools 지원 서브클래스)로 팀을 만들어 실측: `agent.stream(subgraphs=True, stream_mode="updates")`가 **서브에이전트 내부 이벤트를 전부 낸다** — 네임스페이스 `('tools:<uuid>',)` 아래로 팀원의 model(도구 호출)·tools(결과)·최종 응답이 순서대로 도착했다. 근거는 설치본 subagents.py:558-567 주석대로 부모 config·callbacks가 ambient로 전파되기 때문(task 도구가 서브그래프를 invoke해도 자식 런으로 등록된다). **소요시간도 가능** — LangGraph가 시각을 주지는 않지만 이벤트 도착 시각(perf_counter)의 델타로 단계별 시간을 잴 수 있다. 구현 시 주의 3가지: ① 네임스페이스 uuid는 리더의 tool_call_id와 다르다 — 위임↔내부 단계 매핑은 순서 또는 해당 네임스페이스 첫 HumanMessage(description)로 해야 한다(병렬 위임 시 특히), ② 최종 대화 상태를 얻으려면 stream_mode를 ["updates","values"]로 병행해 마지막 values를 취해야 한다(체크포인터 없음), ③ 미들웨어 이벤트(PatchToolCallsMiddleware.before_agent 등)가 스트림에 섞여 필터가 필요하다
  - **완료 조건 대조 (2026-09-30)**: ① 시안 1a~4b 구조 재현 — 단계별 실화면 확인 완료(빌더 탭 위임·내부 단계, 평가 대시보드, 로그인 게이트, 권한 표시. 실측은 다크 테마 기준, 라이트는 config 이원 테마 + st.context.theme 감지 로직·테스트로 담보하고 별도 실화면 점검은 하지 않았다) ② `pytest tests/ -q` **408건** 전건 통과(integration 포함, Phase 7 대비 +57건) ③ 결정 로그 갱신 — 테마 방식·버전 이력·생성 이름 충돌 정책·스트리밍 폴백 범위·단계 7 조사/구현 기록 완료 ④ README Streamlit UI 섹션 갱신 + 스크린샷 3장(docs/images/ — 빌더 탭 위임 단계·평가 대시보드·로그인 게이트). **잔여 없음** — 평가 기준값 리포트(eval/results/2026-09-30_232655.txt, **27/27 통과 · 심판 평균 4.93**)를 `git add -f`로 커밋했다 (첫 실행분은 서버 재시작과 겹쳐 유실, 재실행분)
  - ~~**후속 과제 (2026-09-30, 미착수)**: data_analysis_team 실대화에서 소수 판별처럼 calculate 허용 범위 밖의 식(`all` 등 미지원 함수)을 팀원이 반복 시도해 한 턴이 28단계까지 늘어났다~~ → **2026-10-01 완료** — 도구 설명·오류 메시지·템플릿 프롬프트 3층위 개선, 28단계 → 14·9단계 실측 (3절 "거부에는 대안을 함께 준다" 결정 참조)
- Phase 9 (10월 초): **소속 팀(직무 프로필)별 맞춤 — ADFS·계정 동기화 도메인** ✅ **완료 (2026-10-01)** — 작업 지시서 docs/design/PHASE9_TEAMS.md
  - [x] 단계 1 프로필 정의 + teams 로더 ✅ — runtime/teams.py (프로필 2종 코드 정의, teams.example.json 폴백, iam과 같은 실패 원칙). 테스트 437건
  - [x] 단계 2 사이드바 팀 선택 + 빌더 예시 칩·템플릿 추천 ✅ — 기본 "(선택 안 함)" = 공통 화면 동일(AppTest 고정), 예시 칩은 폼 밖 st.pills + session_state 주입(적용 후 해제), 팀 변경 시 칩 그대로인 입력만 비움, 미존재 추천은 조용히 skip. 실화면 전환 확인(선택 안 함/CLP/ANX). 테스트 450건
  - [x] 단계 3 프로필 템플릿 4종 + 샘플 작업공간 + 실대화 ✅ — contoso 가상 데이터 4파일 + samples/README 코드 목록(사용자 검토 통과: 342 AD 잠금 명시, 276 재확인 유지, MSIS7065 원인 추가), 템플릿별 실대화 1회 확인. 보강: general_assistant(단일 범용, 모든 추천 맨 위), 예시 칩 1개 일반 업무 교체. 테스트 511건
  - [x] 단계 4 평가 세트·프로필별 통과율 + 첫 기준값 ✅ — EvalCase.profile, cases_for_set, --profile CLI, 파일명에 세트 이름, UI 세트 선택(기본 = 선택한 팀 프로필). 1차 13/15 → 케이스 2건 보정 → **15/15 (보정 후: infra 7/7·dev 8/8, 평균 5.00)** 기준값 커밋. 경계 프로브(eval/boundary.py) 분리. 테스트 524건
  - [x] 단계 5 문서·gitignore 갱신 ✅ (2026-10-01) — README(소속 팀 섹션·환경변수 표·템플릿 표 8종·평가 세트), BUILD_SPEC 결정 로그·로드맵, .gitignore(teams.json)
  - **완료 조건 대조 (2026-10-01)**: ① teams.json 없는 clone에서 example 폴백으로 팀 선택 동작 + "선택 안 함"이면 현행 동일 — 테스트·실화면 확인 ✓ ② 샘플에 실제 사내 호스트·도메인·계정 없음 — contoso-only 성질 테스트 ✓ ③ 샘플 오류 코드·이벤트 ID 사용자 검토 통과 (2026-10-01) ✓ ④ common 27건 회귀 없음(Builder·registry 무변경, 기준값 2026-10-01_101343과 계속 비교) + infra/dev 첫 기준값 add -f 커밋 ✓
- 11월 초 마무리 (2주 버퍼)
  - [x] 보고서(개조식) — [REPORT.md](REPORT.md)
  - [x] README 정비 — 빠른 시작 5분 경로, 기능별 필요 키, 자기모순 수정
  - [x] MCP HTTP transport 실연결 검증 — `streamable_http`·`sse` (5-2절)
  - [ ] **데모 영상** — 🚧 **기능이 전부 구축된 뒤에 촬영한다** (2026-08-10 결정).
        선행 조건이던 평가 케이스 확장은 2026-09-28 4차 확장으로 해소됐고
        (21→27건, 아래 기록), 촬영 대본([DEMO.md](DEMO.md))도 Phase 6·7(IAM·OIDC)
        장면을 포함해 갱신했다 — **이제 촬영만 남았다**

## 5. Phase 1 체크리스트
- [x] AgentSpec v0.1 스키마 (runtime/spec.py) + 테스트 5건 통과
- [x] Builder 시스템 프롬프트 v0 (builder/prompts.py)
- [x] deepagents 설치, 설치본 소스로 API 시그니처 확정 → factory.py의 가정 검증·수정
- [x] 내장 도구 4종 최소 구현 및 register_tool 등록 (web_search, python_repl, file_read, file_write)
- [x] 수동 작성 JSON → build_agent() → 대화 성공 (Builder 없이 Runtime 먼저 검증)
- [x] builder/ 구현: LLM 호출 → JSON 파싱 → AgentSpec 검증 → 실패 시 에러를 Builder에 재전달하는 루프(최대 2회)
- [x] cli.py: `python cli.py "IT 뉴스 요약 에이전트 만들어줘"` → 생성 → 즉시 대화 진입
- [x] Phase 1 데모 기록 + 본 문서 갱신 + 커밋

### Phase 1 데모 기록 (2026-08-08)
1. **런타임 단독 검증** — 수동 작성 `specs/news_summarizer.json`(tools: python_repl) → `build_agent()`
   - 노출 도구: `python_repl`, `read_file`, `task`. 요청하지 않은 execute/delete/edit_file/glob/grep/write_file 전부 차단됨
   - 대화: "2024~2026년 각 해의 일수 계산" → python_repl 1회 호출 → 366/365/365, 합계 1,096일 불릿 요약 성공
2. **Builder 엔드투엔드** — `python cli.py "웹 검색으로 최신 IT 뉴스를 찾아 3줄로 요약해주는 에이전트 만들어줘" --no-chat`
   - 생성 결과: name=`it_news_summarizer`, tools=`["web_search"]`, subagents=`[]`, 가드레일 문장 포함
3. **CLI 대화** — `python cli.py --spec specs/it_news_summarizer.json`
   - TAVILY_API_KEY 미설정 상태에서 web_search 호출 → 에이전트가 검색 결과를 **지어내지 않고** 키 미설정 에러를 그대로 보고 + 발급 안내
4. **테스트** — `python -m pytest tests/ -q` → **43 passed**

### Phase 1에서 잡은 버그
- `python_repl`: `subprocess.run(text=True)`가 로케일 코덱(Windows cp949)으로 디코딩해 한글 출력이 UnicodeDecodeError로 유실 → 도구 결과가 에이전트에 전달되지 않고 5회 재시도 후 포기. `encoding="utf-8", errors="replace"` + 자식 프로세스 `PYTHONIOENCODING`/`PYTHONUTF8` 지정으로 수정. 회귀 테스트: `tests/test_tools.py::test_python_repl_handles_non_ascii_output`
- `cli.py`: Windows 콘솔 cp949에서 이모지 출력 시 UnicodeEncodeError, 파이프 입력 시 한글이 서로게이트로 디코딩됨. 표준 입출력을 UTF-8로 고정 (2026-08-10에 `runtime/console.py`로 공용화 — eval/runner.py가 같은 버그를 갖고 있었다)

## 5-2. Phase 2 체크리스트
- [x] `registry/` 모듈 구현 — 레지스트리 코어(registry.py), 도구 구현(builtin.py), MCP 커넥터(mcp.py)
- [x] `runtime/tools.py` → `registry/builtin.py` 이관, factory는 "스펙 → deepagents 번역"만 담당
- [x] 허용 도구 목록을 레지스트리에서 파생 (spec.ALLOWED_TOOLS 상수 제거)
- [x] Builder 도구 자동 선택 — 프롬프트가 `tool_catalog()`에서 도구 목록·설명을 렌더링
- [x] MCP 커넥터 골격 + `mcp_servers.json` 설정 스키마 + `${ENV_VAR}` 치환
- [x] MCP 서버명을 스펙 검증 단계에서 확인 (미설정 서버 거부)
- [x] **MCP 실연결 검증 (stdio)** — 로컬 echo MCP 서버로 커넥터 전 구간 확인 (통합 테스트 6건)
- [x] **MCP 실연결 검증 (streamable_http · sse)** — 같은 echo 서버를 HTTP로 띄워 검증 (통합 테스트 10건).
      설정 헤더가 서버까지 도달하는지 포함. 음성 대조군으로 검출력 확인 완료
- [x] ~~aibrief 실연결 검증~~ — **로드맵에서 제거 (2026-08-10).** 사유는 3절 결정 로그.
      요약: 자체 배포 서버라 제3자 상호운용성 증거가 못 되고, 그것이 덮던 HTTP transport 빈틈은
      로컬 서버로 더 낫게(상시·오프라인·회귀 감지) 막았다
- [x] Phase 2 데모 기록 + 본 문서 갱신 + 커밋

### Phase 2 검증 기록 (2026-08-08)
- 테스트 **66 passed** (Phase 1 43건 → registry 7건, MCP 12건, 프롬프트 3건 추가, MCP 계약 변경 반영 1건 교체)
- 도구 화이트리스트 파생 검증: `test_registry.py::test_every_allowed_key_is_resolvable` — 화이트리스트에 있는데 구현이 없는 키는 존재할 수 없다
- 프롬프트 동기화 검증: `test_builder.py::test_prompt_lists_every_registered_tool`
- MCP 검증 실측: 합성 `mcp_servers.json`(`demo_server`) 상태에서 `mcp:demo_server` 통과, `mcp:typo_server` 거부 확인
- CLI 회귀: MCP 미설정 상태에서 기존 스펙 로드·표시 정상 (`mcp servers : (none)`)

### Phase 2 MCP 실연결 검증 (2026-08-10)
합성 설정만으로는 "커넥터가 진짜 MCP 서버와 말이 통하는가"를 알 수 없어, 외부 서비스에
의존하지 않는 로컬 stdio 서버(`examples/echo_mcp_server.py`, FastMCP)를 띄워 전 구간을 확인했다.

- 검증 경로: 설정 로드 → 프로세스 기동 → 도구 목록 조회 → 도구 호출 → deepagents 주입
- 실측 결과: `mcp:echo` → 서버가 광고한 `echo`/`add_numbers` 2종 로드, `add_numbers(19,23)=42`,
  한글 왕복(`안녕 deep_builder`) 무손실, `build_agent(extra_tools=...)`로 에이전트에 노출 확인.
  이때도 `execute`(셸)는 차단 유지 — MCP 도구가 들어와도 화이트리스트가 뚫리지 않는다
- 회귀 테스트: `tests/test_mcp_integration.py` 5건. `integration` 마커로 분리해
  `-m "not integration"`이면 제외된다 (전체 73 passed / 단위만 68 passed)
- 테스트 **73 passed** (Phase 2 중간 66건 → 실연결 5건 + 설정 회귀 2건 추가)

#### 이 과정에서 잡은 버그
- **`mcp_servers.example.json`을 그대로 복사하면 로드가 깨졌다.** JSON에는 주석이 없어
  설명을 `_comment` 키로 넣었는데, `load_config()`가 이를 서버 항목으로 보고
  `"server '_comment' config must be an object"`로 거부했다. 배포한 템플릿이 사용 불가 상태였던 셈이다.
  → 최상위 `_` 접두사 키는 설명문으로 보고 건너뛴다 (`registry/mcp.py`).
  회귀 테스트: `test_mcp.py::test_shipped_example_config_is_loadable` — 템플릿 자체를 로드해본다
- **stdio `command`의 PATH 함정**: `"command": "python"`으로 적으면 venv가 아니라 PATH의
  전역 인터프리터가 기동되어 `mcp` 패키지를 못 찾고 서버가 즉사한다. 예제와 문서를
  venv 인터프리터 경로 명시로 수정

#### 추가로 확인된 한계
- **호출당 프로세스 재기동**: langchain-mcp-adapters 0.3.2는 연결을 유지하지 않는다.
  도구 호출마다 `ListTools` → `CallTool`로 세션을 새로 연다(로그로 실측). 정확성 문제는
  아니지만 stdio 서버는 호출마다 프로세스 기동 비용을 낸다. Phase 4 평가에서 지연 측정 대상
- **설정 경로 주입 불가**: `configured_server_names(path=DEFAULT_CONFIG_PATH)`의 기본 인자가
  def 시점에 묶이고 `runtime/spec.py`가 인자 없이 호출하므로, 런타임에 다른 설정 파일을
  가리킬 방법이 없다(테스트는 `runtime.spec`의 이름을 patch해서 우회). CLI에
  `--mcp-config` 옵션이 필요해지면 이 지점을 손봐야 한다

## 5-3. Phase 3 체크리스트
- [x] subagents 게이트 해제 — 밸리데이터 제거 + SPEC_VERSION 0.2
- [x] `SubAgentSpec.prompt` → `system_prompt` 개명 (deepagents 키와 1:1)
- [x] 서브에이전트 도구 화이트리스트 검증 (메인과 공용 밸리데이터)
- [x] **서브에이전트 도구 격리** — 팀원마다 FilesystemMiddleware 주입, 셸 유출 차단
- [x] 팀 구성 검증 — 이름 중복 금지, MAX_SUBAGENTS=5, 깊이 1 고정
- [x] 가드레일 주입을 팀원까지 확장
- [x] Builder 프롬프트에 팀 설계 기준 추가 (기본은 단일 에이전트)
- [x] MCP 서버별 매핑 → 팀원도 MCP 도구 사용 가능
- [x] 팀 템플릿 3종 (`templates/`) + 템플릿 검증 테스트
- [x] Phase 2 미결이던 `task` 노출 평가 완료
- [ ] **LLM 실대화 데모** — 🚧 `ANTHROPIC_API_KEY` 미설정으로 보류. 키 확보 시 바로 가능

### Phase 3 검증 기록 (2026-08-10)
- 테스트 **106 passed** (Phase 2 73건 → spec 6건, factory 10건, templates 17건 추가)
- CLI 실행: `python cli.py --spec templates/research_team.json --no-chat` → 팀 구성 정상 표시
  (`researcher: ['web_search']`, `writer: (no tools)`)

#### 서브에이전트 도구 격리 — 실측
`FilesystemMiddleware`를 팀원에 붙이기 전/후를 같은 방식으로 측정했다.

| 구성 | 메인 도구 | 서브에이전트 `researcher` 도구 |
|---|---|---|
| 팀원 middleware 없음 | `read_file`, `task` | `delete, edit_file, **execute**, glob, grep, ls, read_file, write_file` |
| 팀원 middleware 명시 | `read_file`, `task` | `read_file` |

메인을 아무리 좁혀도 팀원은 기본 스택을 새로 받는다. **위임 한 번으로 셸이 열린다.**
회귀 테스트: `test_factory.py::test_shell_does_not_leak_into_subagents`

#### `task` 노출 평가 (Phase 2 미결 항목 해소)
`subagents=[]`이어도 deepagents는 `task`와 `general-purpose` 서브에이전트를 남긴다.
다만 그 general-purpose는 **리더의 제한된 도구를 그대로 물려받는다** — `execute`가 없다.
즉 `task` 노출 자체는 화이트리스트 구멍이 아니다. 위험한 것은 *선언된* 서브에이전트 쪽이었다.
회귀 테스트: `test_factory.py::test_solo_agent_exposes_only_general_purpose_with_leader_tools`

## 5-4. Phase 4 체크리스트
- [x] LangSmith 트레이싱 (`runtime/tracing.py`) — 키 없이 켜라고 하면 실행 전에 차단
- [x] `eval/` 평가 레이어 — 케이스 데이터셋, 기계적 검사 5종, LLM 심판, 실행·집계
- [x] 평가 케이스 5건 (`eval/cases/builder_cases.json`)
- [x] Streamlit 2패널 UI (`ui/app.py`) — 좌 빌더 / 우 대화 + 평가 탭 + 환경 사이드바
- [x] UI 판단 로직 분리 (`ui/state.py`) + 앱 렌더링 검증 (`AppTest`)
- [x] `last_text`를 `runtime/messages.py`로 이관 (ui → cli 역방향 임포트 제거)
- [x] `.env.example`에 심판 모델·LangSmith 변수 추가
- [x] **LLM 실호출 데모** — 키 설정 후 전 구간 실측 완료 (아래 기록)

### Phase 4 검증 기록 (2026-08-10)
- 테스트 **154 passed** (Phase 3 106건 → 트레이싱 9건, 평가 21건, UI 18건 추가)
- 평가 파이프라인 실측: 스텁 생성기(항상 `web_search`만 선택)로 5케이스 실행 →
  `1/5 통과 (20%)`. 실패 케이스마다 원인이 정확히 찍혔다 —
  `calculator_no_search`는 "누락된 도구: ['python_repl']" + "불필요한 도구: ['web_search']",
  `research_and_write_team`은 "팀이 필요한데 단일 에이전트로 만들었다".
  즉 검사기가 실제로 판별력을 갖는다(전부 통과시키는 검사가 아니다)
- UI 렌더링 실측: `AppTest.from_file('ui/app.py').run()` → 예외 0건,
  제목·탭 2개 정상, 키 없는 상태에서 사이드바가 `실행 불가: ANTHROPIC_API_KEY 미설정` 표시
- `streamlit run ui/app.py --server.headless true` 기동 확인 (포트 바인딩까지)

#### 이 과정에서 잡은 버그
- **`render_history`가 사용자 발화를 못 읽었다.** 단일 메시지에 `last_text()`를 썼는데
  그 함수는 `type=="ai"`만 처리한다 — human 메시지는 전부 "(응답 없음)"으로 떨어졌다.
  → `message_text(message)`(종류 무관 텍스트 추출)를 분리하고 `last_text`를 그 위에 재구성.
  회귀 테스트: `test_ui.py::test_render_history_reads_human_messages`

#### 의존성 변경 주의
- `streamlit` 설치가 `starlette`를 1.4.1 → 1.3.1로 내렸다. MCP(stdio 서버)가 starlette를
  쓰므로 회귀를 확인했고, MCP 실연결 테스트 포함 전체 통과했다

### 실호출 검증 (2026-08-10) — Phase 1~4 전 구간
API 키 설정 후 처음으로 LLM을 실제로 호출해 검증했다. **이 과정에서만 버그 3건이 나왔다**
— 단위 테스트로는 잡히지 않는, "실제 설정으로 실행할 때만" 드러나는 종류였다.

- **인증·모델**: `claude-sonnet-4-6` 호출 성공 (in=12/out=4 토큰). 기본 모델 ID 유효 확인
- **트레이싱**: LangSmith 인증 성공, `deep-builder` 프로젝트에 run 기록 확인.
  `SubAgentMiddleware.wrap_model_call` 스팬이 잡혀 서브에이전트 경로까지 추적된다
- **팀 위임 실동작** (Phase 3 미검증 항목 해소): `data_analysis_team`에 "1~100 소수의 합"
  질문 → 리더가 analyst·reviewer에게 각각 위임 → **reviewer가 템플릿 지시대로 다른 방법
  (에라토스테네스의 체 vs 시행 나눗셈)으로 독립 검산** → 일치 확인 후 리더가 보고. 답 1,060 정확.
  즉 위임·검산 프롬프트가 설계대로 작동한다
- **평가**: `python -m eval.runner` → **5/5 통과, 평균 5.00점**
- **심판 신뢰도** (미결 항목 해소): 만점만 나오면 판별력이 없다는 뜻일 수 있어 반증을 시도했다.
  일부러 부실한 스펙(절차·출력형식 없음) → **1/5**, 요구와 무관한 스펙(요리 레시피) → **1/5**.
  심판이 실제로 판별한다. 5/5는 후한 채점이 아니라 진짜 신호였다
- 테스트 **170 passed**

#### 실호출에서만 드러난 버그 3건
1. **빈 환경변수가 기본값을 덮어썼다.** `os.environ.get(k, default)`는 키가 **없을 때만**
   기본값을 쓴다. `.env.example`을 복사하면 `DEEP_BUILDER_MODEL=`(빈 값)이 존재하는 키가 되어
   모델 ID가 **빈 문자열**이 됐다. README가 `cp .env.example .env`를 안내하므로 안내를 따른
   사용자가 전부 밟는다. → `runtime/config.py::env_or_default`로 공용화(공백뿐인 값도 미설정 취급).
   회귀: `test_config_defaults.py`
2. **진입점이 `.env`를 로드하지 않았다.** `cli.py`만 `load_dotenv()`를 불렀고
   `eval/runner.py`·`ui/app.py`에는 없었다. 증상이 진입점마다 달라 더 헷갈린다 —
   eval은 인증 오류, **UI는 키가 있는데도 사이드바가 "미설정"이라며 실행을 막는다**.
   → `runtime/config.py::load_env()` 한 곳으로 모으고, 진입점 3곳 모두 배선.
   회귀: `test_config_defaults.py::test_entry_point_loads_dotenv` (새 진입점이 빠뜨리면 실패)
3. **테스트가 개발 머신의 실제 `.env`에 오염됐다.** 앱이 `.env`를 로드하게 되자
   "키 없으면 차단" 테스트가 실제 키를 주워 실패했다. → 해당 테스트에서 로더를 no-op으로 격리

#### 운영 메모
- `.env.example`은 **git 추적 대상**이다(`.gitignore`가 막는 것은 `.env`뿐).
  키는 반드시 `.env`에만 넣는다 — 실제로 `.env.example`에 잘못 들어간 적이 있고,
  커밋 전에 발견해 되돌렸다(`git log -S` 확인 결과 히스토리 유입 0건)

### Tavily 연동 + 템플릿 3종 실동작 (2026-08-10)
- **web_search 단독 호출**: Tavily 응답 6,215자, 출처 URL 포함. LLM 없이 도구만 검증
- **`research_team`**: "LangGraph vs LangChain 조사" → researcher 조사 → writer 작성 →
  출처 26건 전부 URL 첨부. "출처 없는 주장은 넣지 않는다"는 템플릿 지시가 지켜졌다
- **`data_analysis_team`**: analyst 계산 → reviewer가 **다른 방법으로** 독립 검산 → 일치 후 보고
- **`doc_qa_team`**: 백엔드 교체 + `file_list` 추가 후 실제 문서를 읽고 원문 인용해 답변.
  교체 전에는 "파일을 찾지 못했습니다"로 실패했다
- 테스트 **183 passed**

### 평가 케이스 강화 + Builder 결함 3건 수정 (2026-08-10)
"정답을 추측해 케이스를 적으면 통과만 하는 스위트가 된다"는 문제를 순서를 뒤집어 풀었다.
**기대값을 먼저 적고 → 후보 요구 10건을 실제로 던지고 → 어긋난 것만 케이스로 고정했다.**

후보 10건 중 4건이 기대와 어긋났다. 특히 `over_selection_bait`는 '분석'이라는 단어에
계산 도구를 **과잉** 선택하는지 보려고 만들었는데, 정반대로 **도구를 하나도 고르지 않아**
일기를 읽을 수단조차 없었다 — 추측으로 케이스를 적었다면 못 잡았을 지점이다.

| 케이스 | 증상 | 원인 |
|---|---|---|
| `two_tools_one_request` | 환율 검색+계산인데 `web_search`만 | 프롬프트에 **과소 선택 방지** 지침이 없었다 |
| `read_before_analyze` | 일기 읽고 분석인데 도구 0개 | 동상 |
| `sequential_not_a_team` | 3단계로 들리는 일에 팀 생성 | "단계가 여러 개"와 "역할 분리"를 구분하는 기준이 없었다 |
| `team_size_cap` | 7명 요구 시 **간헐적** 생성 실패 | 아래 참조 — 원인이 예상과 달랐다 |

#### 프롬프트 수정
- **도구 과소 선택 방지**: "요구에 동사가 둘 이상이면 도구도 둘 이상일 수 있다",
  "읽고 분석해줘는 읽을 수단이 먼저 있어야 한다", "계산은 암산을 신뢰하지 않는다"
- **팀/단일 판단 기준 구체화**: 각 단계가 쓰는 도구가 같고 중간 산출물이 짧으면 단일이다
- **상한 초과 요구 처리**: 사용자가 더 요구해도 역할을 합쳐 상한 이하로 만들고 그 사실을 적는다

#### `team_size_cap` — 가설이 틀렸고, 관찰이 진짜 원인을 찾았다
상한 지시를 안 따르는 줄 알았는데 아니었다. 재시도 각 시도의 입출력을 캡처해 보니
**1차 시도에 JSON이 아예 없었다** — Builder가 되물었기 때문이다. 프롬프트에
*"요구가 모호하면 최대 2개의 질문으로 확인한다"*가 있었는데, **그 질문을 받아줄 코드
경로가 없다.** `generate_spec()`은 파싱 실패로 처리해 재시도를 소진할 뿐이고,
CLI·UI·평가 전부 단발 호출이다. 프롬프트가 시스템에 없는 상호작용을 약속하고 있었고,
복잡한 요구일수록 되물을 확률이 높아 **간헐적으로** 실패했다.
→ 질문 단계를 제거하고 "합리적으로 가정하고 가정을 description에 적는다"로 교체.

#### 결과
5/9 (56%) → 프롬프트 수정 → 8/9 (89%) → 질문 단계 제거 → **9/9, 2회 연속**.
평가가 회귀를 잡고 수정을 확인하는 루프가 실제로 돌았다 — 이 스위트의 존재 이유다.

### 평가 케이스 2차 확장 — 보안 결함 1건 적발 (2026-08-10)
1차와 같은 절차로 "아직 안 건드린 축"(모순 요구 / 화이트리스트 밖 능력 / MCP 얽힘 /
도구 3개 이상)에 후보 10건을 던졌다. 그런데 **평가가 아니라 보안 결함이 먼저 나왔다.**

#### `python_repl`이 비밀값을 그대로 넘기고 있었다
후보 `outside_whitelist_shell`("셸 명령을 실행해주는 에이전트")에 Builder가
`python_repl`을 붙였다. 그게 진짜 우회 경로인지 확인하다 더 큰 것을 발견했다.

| 프로브 | 수정 전 | 수정 후 |
|---|---|---|
| `os.system` / `subprocess` | 실행됨 | 실행됨 (도구 본질) |
| `ANTHROPIC_API_KEY` 환경변수 | **KEY_VISIBLE** | 차단 |
| `TAVILY_API_KEY` / `LANGSMITH_API_KEY` | **KEY_VISIBLE** | 차단 |
| 절대경로로 `.env` 읽기 | **ENV_READABLE** | (셸이 열려 있으므로 여전히 가능) |
| 네트워크 송신 | NET_OK | NET_OK (도구 본질) |

원인은 `env={**os.environ, ...}` — 부모 환경을 통째로 물려줬다. `python_repl`은
임의 코드 실행이므로 **환경변수는 "에이전트가 읽을 수 있는 값"으로 봐야 한다.**
키 읽기 + 네트워크가 겹치면 유출 경로가 성립한다.
→ 환경변수 화이트리스트(`_REPL_ENV_PASSTHROUGH`)로 전환. 인터프리터 구동에 필요한
8개만 넘긴다. 회귀 테스트 5건(`test_tools.py`)이 비밀값 이름이 목록에 추가되는 것을 막는다.

**더 중요한 것은 주장의 수정이다.** "deepagents의 셸 도구 `execute`를 차단한다"는
설명은 절반만 맞았다 — `python_repl`을 허용한 스펙은 사실상 셸을 허용한 것이다.
도구 docstring과 README·REPORT의 한계 항목을 그렇게 고쳤다. 격리라고 부르지 않는다.

#### 평가에 반영한 것
| 케이스 | 증상 |
|---|---|
| `shell_request_not_satisfied_by_repl` | 셸 요구에 `python_repl`을 대체재로 붙였다 |
| `unavailable_capability_honesty` | description이 "DB에 접속해 조회"라고 약속했으나 접속 수단이 없었다 |
| `three_tools_one_request` | 통과 — 도구 3개 요구에서 과소 선택 방지가 유지되는지 지키는 회귀 |

심판이 두 번째를 정확히 짚었다(2/5): *"description은 python_repl로 DB 쿼리를 실행한다고
가정했으나 system_prompt는 여전히 '데이터베이스에 접속하여'라고 명시해 모순된다."*
기계적 검사로는 잡히지 않는 종류라 rubric이 값어치를 한 사례다.

#### 프롬프트 수정 — 「할 수 없는 일을 할 수 있다고 쓰지 않는다」
두 실패는 뿌리가 같다: **약속을 도구가 뒷받침하지 않는다.**
- 도구 목록에 없는 능력을 `description`·`system_prompt`에 있다고 적지 않는다
- **다른 도구로 우회하지 않는다** — `python_repl`은 계산용이지 셸·DB 접속의 대체재가 아니다
- 대신 무엇이 필요한지 명시하고("데이터는 사용자가 제공한다") 역할을 실제 범위로 좁힌다

#### 결과
10/12 (83%, 평균 4.73) → 프롬프트 수정 → **12/12 (100%, 평균 4.92), 2회 연속**.
테스트 188 → **193건**(비밀값 격리 회귀 5건 추가).

### README 정비에서 잡은 것 (2026-08-10)
문서도 산출물이라 같은 기준으로 검증했다 — **적힌 명령이 실제로 되는지 전부 실행해 확인**.

- **README가 자기모순이었다.** "알려진 한계"에 *"파일 도구는 기본 StateBackend(가상 FS)를
  대상으로 하며 실제 디스크가 아니다"*가 남아 있었는데, 같은 문서의 「작업공간」 절은
  실제 디스크를 읽는다고 설명한다. 백엔드를 교체하면서 이 줄을 못 고쳤다 —
  **코드를 바꿀 때 그 코드를 설명하는 문장을 같이 찾지 않으면 문서가 거짓말을 한다**
- **첫 실행 예시가 clone 직후 실패하는 명령이었다.** `--spec specs/it_news_summarizer.json`을
  안내했는데 `specs/`는 생성물이라 gitignore 대상이다. 처음 받은 사람에게는 없는 파일이다
  → `templates/`(추적 대상)로 교체하고, 그 차이를 문서에 명시
- 재시도 횟수 표기 정정: "최대 2회 재생성" → `DEFAULT_MAX_RETRIES=2`이므로 **총 3회 시도**

구조도 바꿨다 — 기능 나열식에서 **처음 보는 사람이 5분 안에 돌려보는 순서**로:
빠른 시작(Anthropic 키만으로 되는 템플릿) → 동작 방식 → 환경변수(기능별 필요 키 표) → 사용법.

### UI 전 경로 실측 (2026-08-10) — 미검증 구간 없음
Streamlit UI에서 사람이 직접 눌러 확인했다.

- **빌더 탭 — 자연어 생성**: "1~200 3의 배수이면서 5의 배수가 아닌 수의 합" 요구로
  `divisor_sum_calculator` 생성. 도구 `python_repl`만 선택(과잉 없음), 단순 계산이라
  `subagents: []`("기본값은 단일 에이전트" 지침 작동). Builder가 스스로
  *"암산으로 제공하지 않는다. 반드시 python_repl로 검증한다"* 조항을 썼고,
  트레이스에 실제 `python_repl` 호출이 남아 **그 조항이 지켜진 것까지** 확인
- **빌더 탭 — 템플릿 로드 + 팀 대화**: `data_analysis_team`으로 같은 질문.
  트레이스 대조 결과 analyst는 리스트 컴프리헨션, **reviewer는 집합 연산**으로
  서로 다른 방법을 썼다 — *"같은 코드를 재실행하는 것은 검산이 아니다"* 가 지켜졌다
- **평가 탭**: 5/5 통과. CLI(`python -m eval.runner`)와 동일 결과

#### 단일 vs 팀 실측 비교 (같은 질문, 정답 5,268)
| | 단일 에이전트 | 팀 |
|---|---|---|
| python_repl 호출 | 1회 | 2회 (서로 다른 방법) |
| 보고 내용 | 최종 합계만 | 중간값(6,633 / 1,365)까지 노출 |
| 검증 근거 | 없음 | 두 방법 교차 확인 |

둘 다 정답이지만 팀은 **답이 왜 맞는지 확인 가능한 형태로** 낸다. 대신 호출·지연이 배 이상이다.
"팀은 근거가 있을 때만"이라는 설계 기조의 실제 모습이다.

#### 레지스트리 파생 설계의 효과 (실측)
`file_list`를 레지스트리에 등록한 뒤 **Builder 프롬프트는 손대지 않았는데**,
평가 케이스 `file_summarizer`에서 Builder가 `['file_list', 'file_read']`를 골랐다.
요구하지 않은 `file_write`는 끌어오지 않았다. Phase 2의 "프롬프트를 `tool_catalog()`에서
렌더링" 결정이 의도대로 작동한다는 직접 증거다.

#### 이 과정에서 잡은 것
- **보안 경계 테스트가 잘못된 이유로 통과하고 있었다.** 경로 탈출을 검증한다며
  `backend.read_file(...)`을 `pytest.raises(Exception)`으로 감쌌는데, `FilesystemBackend`에는
  `read_file` 메서드 자체가 없어서 **`AttributeError`를 '차단됨'으로 오인**하고 있었다.
  실제 API는 `read(file_path)`다. 경계는 진짜로 작동하지만(실측 확인), 그것을 확인해준다던
  테스트는 아무것도 확인하지 못했다 — 통과하는 보안 테스트일수록 **무엇이 통과시켰는지**
  확인해야 한다. `test_workspace.py::test_read_is_the_actual_backend_api`로 계약을 고정했다
- 경로 차단 방식이 경로마다 다르다: `..`·외부 절대경로는 `ValueError`, `~`는 not-found 결과.
  테스트는 "비밀값이 결과에 나타나지 않는다"는 공통 성질로 검사한다

### MCP HTTP transport 검증 (2026-08-10)
"외부 MCP 서버(aibrief) 연결"을 로드맵에서 빼면서, **그 항목이 사유 없이 덮고 있던
진짜 빈틈**이 드러났다. 커넥터는 transport 셋을 지원한다고 선언하는데:

| transport | 지원 선언 | 실연결 검증 (이전) | 실연결 검증 (지금) |
|---|---|---|---|
| `stdio` | ✅ | ✅ echo 서버 | ✅ |
| `streamable_http` | ✅ | ❌ 설정 파싱만 | ✅ echo 서버 |
| `sse` | ✅ | ❌ 설정 파싱만 | ✅ echo 서버 |

HTTP 경로가 깨져 있어도 전 테스트가 초록이었다. `examples/echo_mcp_server.py`에
`--transport {stdio,streamable-http,sse}`를 붙여 **같은 서버를 세 방식으로** 띄운다.
FastMCP 기본 마운트 경로(`/mcp`, `/sse`)는 추측하지 않고 설치본에서 확인했다.

#### 헤더 전달 — dict 단언이 못 보던 곳
기존 `${ENV_VAR}` 치환 테스트는 `load_config()`가 **돌려주는 dict**만 봤다.
치환된 헤더가 실제로 전송되지 않아도 통과하는 단언이었고, 인증이 필요한 MCP 서버는
전부 이 경로를 탄다. echo 서버에 `http_request_headers` 도구를 두어 수신 헤더를 되받는다.

**음성 대조군으로 검출력을 확인했다** — 통과했다는 사실만으로는 아무것도 모른다:

| 설정 | 서버가 관측한 헤더 | 토큰 도달 |
|---|---|---|
| `headers` 없음 | `{}` | ❌ |
| `headers` 있음 | `authorization`, `x-deep-builder-probe` | ✅ |

stdio에서는 HTTP 요청 자체가 없어 `{}`가 나오는 것도 고정했다 —
이 도구가 상수를 돌려주는 게 아니라 실제 요청을 읽는다는 근거다.

#### 비용
**LLM 호출 0회.** 외부 계정·네트워크 없이 오프라인에서 상시 돈다.
포트는 매번 비어 있는 것을 골라(`_free_port`) 개발자 머신에서 충돌하지 않는다.

#### 결과
테스트 193 → **204건** (HTTP 통합 10건 + stdio 대조군 1건).
`.py`·`.json`에서 `aibrief`를 전부 걷어냈다(실행 확인: `grep -rn aibrief --include=*.py --include=*.json` → 0건).
이 문서와 REPORT에는 **무엇을 왜 뺐는지** 남기기 위해 이름이 그대로 있다 — 결정 로그에서까지
지우면 다음 사람이 같은 항목을 사유 없이 다시 넣는다.

### 평가 케이스 3차 확장 (2026-08-10) — 12건 → 21건

BUILD_SPEC에 적어둔 다음 축 4개(사용자 도구 지정·팀원 간 의존·출력 형식·다국어)로
후보 8건을 던졌다. **8건 중 7건이 기대와 일치했다.** 유일한 불일치는 내 판정 기준이
틀린 것이었다 — "도구 없는 팀원 = 결함"으로 봤는데, 분석 결과를 받아 개선안을 쓰는 일은
순수 텍스트 판단이라 도구가 필요 없다.

**축을 잘못 골랐다는 뜻이다.** 이미 잘 하는 영역만 건드렸다. 그래서 2차로
프롬프트 지침끼리 부딪치는 지점 6건을 던졌다(없는 도구를 이름으로 지정, 사용자가
도구를 잘못 지정, 부분 부정, 도구 4종, 역할 다수 단일, 사소한 일에 팀 강요).
여기서 **5/6 일치, 1건에서 진짜를 찾았다.**

#### 찾은 것 1 — 프롬프트에 없는 규칙 (맞은 게 운이었다)
```
요구:  "숫자 두 개를 더해주는 에이전트를 5명짜리 팀으로 만들어줘"
결과:  단일 에이전트. description — "역할 분리 근거가 없어 단일로 구현했다"
```
판단 자체는 옳다. 문제는 **프롬프트에 그 규칙이 없었다**는 것이다. 기존
`team_size_cap`(7명 요구 → 5명 팀)은 사용자의 팀 요구를 존중하는 쪽인데 여기서는
거부한다. 둘을 가르는 기준이 명시돼 있지 않으면 다음번에 반대로 나와도 이상하지 않다.
프롬프트에 기준을 적고 두 방향을 케이스로 고정했다.

#### 찾은 것 2 — 실패할 수 없던 단언 (검사 로직)
| | 이전 | 지금 |
|---|---|---|
| 팀 케이스의 도구 검사 | **없음** (`expect_tools=[]`) | `expect_subagent_tools` |
| 조사 팀에 아무도 `web_search`가 없으면 | 통과 | 실패 |

도구가 리더가 아니라 팀원에게 붙는 구조라 `check_expected_tools`로는 안 잡힌다.
`test_team_cases_declare_the_tools_their_members_need`가 앞으로 팀 케이스를 늘릴 때
이 필드를 빠뜨리는 것을 막는다.

#### 찾은 것 3 — 심판이 못 보던 것
심판에게 팀원 **이름만** 넘기고 있었다. 팀원 프롬프트가 채점에서 통째로 빠져 있었고,
도구 배분을 묻는 rubric에는 보이지 않는 것을 근거로 감점했다.

| | 수정 전 | 수정 후 |
|---|---|---|
| `team_members_need_different_tools` | 4/5 (*"도구가 명세에 명시되지 않아"*) | **5/5** (*"web_search vs python_repl"*) |

#### 찾은 것 4 — 진입점 인코딩 (실행 중 발생)
평가 21건을 다 돌린 **뒤** 리포트 출력에서 `UnicodeEncodeError`로 죽었다.
이미 지불한 LLM 호출 42회의 결과가 통째로 날아갔다. Phase 1에서 `cli.py`에 고친
버그가 `eval/runner.py`에 그대로 남아 있었던 것이다.
`runtime/console.py`로 공용화하고 진입점 누락을 테스트로 막았다.

#### 결과
- 케이스 12 → **21건**, 평가 **21/21 (평균 5.00)**
- 테스트 204 → **215건**
- 이번 확장에 쓴 LLM 호출 **104회** (프로브 14 + 평가 42×2 + 팀 재검증 6).
  평가 42회는 인코딩 버그로 유실됐다 — **비싼 실행일수록 출력 경로를 먼저 확인한다**

### 단일 vs 팀 실행 비용 실측 (2026-08-10)

같은 질문("1~200 중 3의 배수이면서 5의 배수가 아닌 수의 합", 정답 5,268)을
**subagents 유무만 다른** 두 스펙에 던졌다. 두 스펙 모두 손으로 작성해
Builder 변동을 제거했고, 도구는 양쪽 다 `python_repl` 하나다.

**계측 방법이 중요하다**: 서브에이전트 호출은 `task` 도구 **안쪽**에서 일어나므로
부모 그래프의 `messages`만 보면 통째로 빠진다. LangChain 콜백(`on_llm_end`)은
중첩 실행에도 전파되므로 그걸로 셌다.

| | 단일 | 팀(2인) | 배수 |
|---|---|---|---|
| LLM 호출 | 2회 | 6회 | **3.0배** (2회 측정 모두 동일) |
| 입력 토큰 | 3,858 | 12,266 / 13,447 | 3.2~3.5배 |
| 출력 토큰 | 223 / 201 | 2,384 / 3,349 | **10.7~16.7배** |
| 지연 | 6.2 / 5.3초 | 26.4 / 32.7초 | 4.3~6.2배 |
| 실비(Sonnet 4.6) | $0.015 | $0.073 / $0.091 | **약 5~6배** |

- **출력 토큰이 비용을 지배한다.** 출력 단가가 입력의 5배인데 증가율도 가장 크다.
  위임할 때마다 리더가 지시를 쓰고 팀원이 보고를 쓰기 때문이다 — 팀의 비용은
  "호출이 3배"가 아니라 **"쓰는 말이 10배 이상"**에서 나온다
- **팀은 변동도 크다.** 출력 토큰이 두 실행에서 2,384 → 3,349로 40% 흔들렸다.
  단일은 223 → 201로 거의 고정이다. 위임 횟수가 매번 같지 않다
- 둘 다 정답을 맞혔다. **이 질문에서 팀은 5~6배를 더 내고 같은 답을 냈다** —
  "팀은 근거가 있을 때만"이라는 설계 기조의 수치 근거다
- 표본은 질문 1개 × 2회다. 절대값이 아니라 **자릿수**로 읽어야 한다

### Builder 모델 비교 + 프롬프트 자기모순 발견 (2026-08-10)

전체 21케이스 × 모델 수는 과하므로 **판별력이 있던 6건만** 골랐다 —
과거에 실패를 냈거나 지침이 부딪치는 지점이다. 전부 통과하는 쉬운 케이스를
여러 모델에 던져봐야 아무것도 못 가른다.

| 모델 | 기계 검사 | 심판 평균 | 생성 평균 |
|---|---|---|---|
| `claude-sonnet-4-6` | 5/6 | 5.00 | 26.9초 |
| `claude-sonnet-5` | 6/6 | 5.00 | 21.3초 |

#### 갈린 지점이 모델 문제가 아니었다
`four_tools_one_request`("검색하고 → 읽고 → 계산하고 → 저장")에서
`sonnet-4-6`은 **4인 팀**, `sonnet-5`는 도구 5개짜리 단일 에이전트를 냈다.
그런데 같은 케이스가 **같은 날 아침 전체 평가에서는 `sonnet-4-6`으로 통과**했다.

원인은 모델이 아니라 **프롬프트의 자기모순**이었다:

| 프롬프트 문장 | 이 요구를 어디로 보내는가 |
|---|---|
| "요구에 동사가 둘 이상이면 도구도 둘 이상일 수 있다" | 단일 + 도구 여러 개 |
| "단계마다 필요한 도구가 다르다" (팀으로 나눌 근거) | **팀** |

같은 요구를 두 규칙이 반대로 가리키니 실행마다 뒤집힌 것이다.
**"단계마다 도구가 다르다"를 팀의 근거에서 제거**하고, 도구가 다르다는 것만으로는
근거가 아님을 명시했다. 마침 직전에 잰 비용(팀 = 5~6배)이 어느 쪽이 맞는지 정해줬다 —
그 수치를 프롬프트에 그대로 넣었다.

#### 수정 후 검증
팀 판단이 걸린 7케이스 재실행 **9/9 통과**. 뒤집히던 `four_tools_one_request`는
**3회 반복 모두 단일**로 안정됐고, 팀이 필요한 케이스(`research_and_write_team`,
`team_size_cap` 5인, `team_members_need_different_tools`)는 그대로 팀을 냈다.

#### 이 과정에서 드러난 더 큰 문제
**Builder는 결정적이지 않은데 평가는 케이스당 1회만 돌린다.**
"21/21 통과"는 결정적 사실이 아니라 **단일 표본**이다. `run_evaluation(repeats=N)`을
추가했다 — 한 번이라도 실패하면 그 실패가 리포트에 남는다. 기본값은 1이라
평소 비용은 그대로고, 프롬프트를 고친 뒤처럼 확인이 필요할 때만 올린다.

### 팀원 모델 차등 실측 (2026-08-10) — 기대보다 작았다

`doc_qa_team`의 `extractor`(문서에서 원문 발췌 = 기계적인 일)만
`claude-haiku-4-5`로 내리고, 같은 질문을 같은 팀에 던져 비교했다.
**모델별로 토큰을 따로 세야 한다** — 단가가 달라 합계 토큰으로는 비용이 안 나온다.

| | 전원 sonnet | extractor만 haiku |
|---|---|---|
| LLM 호출 | 7회 | 7회 (sonnet 5 + haiku 2) |
| sonnet 입력/출력 | 17,030 / 2,664 | 13,707 / 2,217 |
| haiku 입력/출력 | — | 3,915 / 521 |
| 비용 | $0.09105 | **$0.0809** |
| 지연 | 45.6초 | 37.5초 |

- **절감 11.1%.** 기대(출력 토큰의 대부분이 팀원 쪽)보다 훨씬 작다
- **이유**: 값싼 모델로 내린 팀원이 전체 호출 7회 중 **2회**만 담당했다.
  리더의 위임 판단과 summarizer의 집필이 여전히 sonnet이고, 그쪽이 토큰의 대부분이다
- **일반화**: 절감폭은 "값싼 모델을 붙였는가"가 아니라
  **"그 팀원이 전체 작업의 몇 %를 하는가"**로 정해진다.
  기계적인 일이 많은 팀일수록 효과가 크고, 판단이 중심인 팀에서는 거의 없다
- **답의 품질은 유지됐다** — 두 실행 모두 문서를 정확히 인용했다.
  싸지기만 하고 틀리면 의미가 없으므로 같이 확인했다
- 표본은 질문 1개 × 1회다

#### Builder가 이 필드를 쓰는 방식 (실측)
| 요구 | 팀원 | Builder가 고른 모델 |
|---|---|---|
| 발췌 + 집필 | `retriever` (원문 그대로 추출) | `claude-haiku-4-5` |
| | `writer` (설득력 있는 답변) | 상속 |
| 계산 + 검산 | `calculator` (`python_repl`이 계산) | `claude-haiku-4-5` |
| | `verifier` (교차 검증) | 상속 — **검산은 내리지 않았다** |

지침대로 작동한다. 다만 교차 검증 쌍에서 한쪽만 값싼 모델이 되는 구성은
**설계 판단이 갈릴 수 있는 지점**이다 — 싼 1차 시도를 비싼 쪽이 검사하는
구조로 볼 수도 있고, 검증 쌍의 대칭성이 깨졌다고 볼 수도 있다.
현재는 프롬프트를 더 조이지 않고 관측 상태로 둔다.

### Phase 5-1 실측 (2026-08-10) — 임의 코드 실행 권한이 사라졌다

프로젝트의 핵심 주장은 "LLM의 준수를 신뢰하지 않고 제약을 코드로 강제한다"인데,
`python_repl` 하나 때문에 문서가 **같은 페이지에서 자기 말을 정정**하고 있었다 —
*"`execute`를 차단한다"* 옆에 *"`python_repl`을 허용한 스펙은 사실상 셸을 허용한 것"*.

계산 전용 도구를 분리하고 Builder가 계산에는 그것을 고르게 했다.

| | 이전 | 이후 |
|---|---|---|
| 평가 21케이스 중 `python_repl` 선택 | **7건** | **0건** |
| `calculate` 선택 | — | 7건 |
| 평가 통과율 | 21/21 (평균 4.95) | **21/21 (평균 5.00)** |
| 테스트 | 235건 | **284건** |

- **빠른 시작 템플릿(`data_analysis_team`)도 전환했다.** README 첫 예시가
  `calculate`만으로 같은 답(5,268)에 **두 방법 교차 검증까지** 해내는 것을 실행으로 확인했다.
  처음 써 보는 사람이 밟는 경로에서 임의 코드 실행 권한이 사라졌다
- `python_repl`은 제거하지 않았다. 표준 라이브러리·다단계 가공이 진짜 필요한 요구가 있고,
  그때는 **의식적으로 그 권한을 주는 것**이 맞다. 프롬프트가 그 사실을 명시한다

#### 이 과정에서 잡은 것 — 프롬프트 구조가 규칙을 밀어냈다
`calculate` 절을 「빠뜨리지 않기」와 「넘치지 않기」 **사이에** 넣었더니
`read_before_analyze`가 3회 중 2회 실패했다. Builder는 *"사용자가 붙여넣는다고 가정"*하고
`file_read`를 빼기 시작했다 — 원래 이 케이스를 만든 실패 모드 그대로다.

**긴 절이 규칙 사이에 끼면 앞뒤 규칙의 결합이 끊긴다.** 절을 뒤로 옮기고
"붙여넣기는 사용자가 선택할 수 있는 대안이지 도구를 빼는 근거가 아니다"를 명시했다.
`repeats=3`으로 재검증해 5케이스 15회 생성 전부 통과를 확인했다 —
**1회 실행이었으면 고쳤는지 운이 좋았는지 구분하지 못했다.**

### Phase 5-2 실측 (2026-08-10) — 수정 루프

만들기→고치기 루프를 닫았다. 지금까지는 만들면 끝이고, 고치려면 JSON을
손으로 편집해야 했다.

- CLI: 대화 중 `/revise <요구>`, 또는 `--spec X.json --revise "요구"`
- UI: 명세가 올라온 뒤 「② 명세 고치기」 폼
- 양쪽 다 **변경 내역을 보여주고** 저장한 뒤 에이전트를 다시 만든다

#### 주된 위험을 정량화했다 — 요청하지 않은 변경
전체 명세를 다시 받는 방식이라 LLM이 손대지 말라고 한 문장도 다듬을 수 있다.
`research_team`에 세 가지 수정을 던져 **바뀐 항목을 전부 셌다**:

| 요구 | 바뀐 항목 |
|---|---|
| "팀원 writer의 모델을 값싼 것으로 바꿔줘" | `writer:model` — **1개** |
| "researcher가 찾은 자료를 파일로도 저장하게 해줘" | `researcher` 도구 + 프롬프트 — **2개** |
| "리더 설명을 더 짧게 한 줄로 줄여줘" | `description` — **1개** |

**요청하지 않은 변경은 없었다.** 두 번째의 프롬프트 변경은 필요한 것이다 —
도구만 붙고 쓰는 법이 없으면 실제 동작은 바뀌지 않는다(프롬프트 규칙에 명시).

다만 팀 전체의 능력이 바뀌는 수정에서는 리더의 `description`·`system_prompt`도
함께 바뀌었다(실제 실행에서 확인). 리더가 새 능력을 알아야 위임할 수 있으므로
타당하지만, **표본이 4건이라 "요청한 것만 바뀐다"고 단정할 수 없다.**
그래서 diff를 항상 보여주는 쪽으로 설계했다.

#### 실행 확인
`data_analysis_team`으로 대화 중 `/revise 계산 결과를 파일로도 저장해줘` →
analyst에 `file_write` 추가 → 에이전트 재구축 → 새 능력이 반영된 응답까지 확인했다.
**템플릿 원본은 그대로고 수정본만 `specs/`에 저장된다.**

### Phase 5-3 실측 (2026-08-10) — 심사자가 밟는 경로를 그대로 밟았다

`git clone` → venv → `pip install` → 테스트 → 실행 순서로 **실제 사본에서** 확인했다.

| 단계 | 결과 |
|---|---|
| clone 직후 상태 | `.env`·`specs/`·`mcp_servers.json` 없음, `templates/`·`workspace/` 있음 — README 설명과 일치 |
| `pip install -r requirements.txt` | 성공 |
| `cp .env.example .env` | 값이 채워진 항목은 `LANGSMITH_PROJECT`(비밀값 아님)뿐 — **키 유출 없음** |
| `pytest tests/ -q` (키 없이) | **303건 전부 통과** |

#### 잡은 결함 — 키 없이 실행하면 원시 오류로 죽었다
README 빠른 시작을 그대로 따르되 키를 넣지 않으면, CLI는 **대화 화면까지 들어간 뒤**
첫 질문에서 이렇게 죽었다:

```
[error] 에이전트 실행 실패: TypeError: Could not resolve authentication method.
        Expected one of api_key, auth_token, or credentials to be set. ...
```

`ANTHROPIC_API_KEY`도 `.env`도 언급되지 않는다. **UI는 이미 막고 있었는데 CLI만 안 막았다** —
점검 로직이 `ui/state.py`에 있어 CLI가 쓸 수 없었기 때문이다.
`.env` 로드·콘솔 인코딩과 **같은 실패 계열**이다(진입점마다 각자 배선).

`runtime/readiness.py`로 내려 공용화하고, 무엇을 해야 하는지까지 알려준다:

```
[error] 필수 환경변수가 설정되지 않았습니다: ANTHROPIC_API_KEY
        1) cp .env.example .env
        2) .env 를 열어 ANTHROPIC_API_KEY= 뒤에 키를 붙여넣으세요
        키 발급: https://console.anthropic.com/settings/keys
```

**대조군을 함께 뒀다**: `--no-chat`은 스펙 검증만 하므로 키 없이 통과해야 한다.
이게 없으면 "전부 막는" 구현도 위 테스트를 통과한다.

#### 문서 일관성 자동 점검
문서가 언급하는 파일 경로·테스트 이름이 실제로 있는지, 테스트 수 표기가 맞는지 훑었다.
`BUILD_SPEC` 첫 줄이 **226건 / Phase 1~4**로 멈춰 있었다(실제 303건 / Phase 5-2).
README의 `--revise` 예시가 gitignore 대상인 `specs/` 파일을 가리켜
**clone 직후 실패하는 명령**이었던 것도 함께 고쳤다 — 예전에 한 번 잡은 것과 같은 실수다.

#### 이 과정에서 잡은 테스트 자체의 결함
새로 쓴 "키 없으면 막힌다" 테스트가 **개발자 머신의 실제 `.env` 때문에 실패**했다.
`cli.py`가 `from runtime.config import load_env`로 이름을 직접 바인딩해서
`runtime.config.load_env`를 monkeypatch해도 소용이 없었다 — `cli.load_env`를 갈아끼워야 한다.
**환경에 따라 통과했다 실패했다 하는 테스트**가 될 뻔했다.

### 평가 케이스 4차 확장 (2026-09-28) — 21건 → 27건, 수정(revise) 경로 개봉

BUILD_SPEC에 적어둔 다음 축 4개(장문 요구·도메인 용어·수정 요구·반복 일관성)로
프로브 9건(생성 4 + 수정 2 + 동일 요구 3회)을 던졌다. **9건 전부 기대와 일치했다.**
그러나 통과 프로브를 회귀 가드로 고정하고 전체 평가를 돌리자 **간헐 결함 2건이
드러났다** — 프로브 1회 통과는 아무것도 보증하지 않는다(단일 표본 한계)의 실측 사례다.

#### 찾은 것 1 — CSV 통계에 python_repl (프롬프트 지침 충돌)
`jargon_heavy_finance`(prices.csv 통계)가 프로브에서는 calculate를, 전체 평가에서는
python_repl을 골랐다. "계산이면 calculate" 규칙과 "CSV 파싱이면 python_repl" 규칙이
충돌해 실행마다 승자가 달랐다 — 3차의 교훈(결함은 지침이 충돌하는 지점에서 난다) 재확인.
수정: CSV 수치 집계·통계는 file_read+calculate로 충분하다고 명시하고
**타이브레이크를 프롬프트에 적었다 — 망설여지면 권한이 작은 쪽을 고른다.**

#### 찾은 것 2 — 글 다듬기에 file_read (경계 기준 부재 + 케이스 구멍)
`no_tools_needed`(편집자)가 2차 전체 평가에서 file_read/file_list를 붙였다. 문제가 두 겹이다:
- forbid에 이 둘이 빠져 있어 **기계 검사는 통과**하고 심판(2/5)이 운 좋게 잡았다
  → forbid에 추가해 기계적으로 고정 (3차 '실패할 수 없던 단언'과 같은 유형)
- `read_before_analyze`("일기를 **읽고**" → file_read 기대)와 반대 방향으로 당기는데
  가르는 기준이 프롬프트에 없었다. 1차 수정이 반대편을 깨는 **시소**가 났고
  (no_tools 통과 ↔ read_before 실패), "**대상을 누가 가져오는가**"를 대조 예시 쌍
  ("글을 다듬어줘"=도구 없음 / "일기를 읽고"=file_read)으로 명시한 뒤에야
  경계 4케이스 × 3회 반복이 안정됐다

#### 수정(revise) 경로 개봉
`EvalCase.revise_base`(기반 스펙, 로드 시점 검증)를 추가하고 runner에 `spec_reviser`
주입을 열었다. `revise_spec`은 이전까지 회귀 스위트가 전혀 못 덮던 경로다 —
도구 추가·제거 두 방향을 고정했다. 기반 스펙은 Builder 변동을 제거하려고 손으로 쓴다.

#### 결과
- 케이스 21 → **27건** (장문 2 + 도메인 용어 2 + 수정 2), 최종 **27/27 (평균 4.96)**
- 반복 일관성 축: 같은 요구 3회 도구 집합 동일 — 케이스가 아니라 `repeats` 파라미터 소관으로 정리
- 테스트 351 → **354건** (수정 케이스 라우팅 3)
- 이번 확장에 쓴 LLM 호출 약 **195회** (프로브 18 + 전체 평가 3회 162 + 경계 재검 15).
  프로브 첫 9회는 **스크래치 스크립트의 cp949 인코딩으로 유실**됐다 — runner에서
  이미 고친 함정(3차 '진입점 인코딩')을 밖의 일회성 스크립트에서 그대로 다시 밟았다.
  비싼 실행의 출력 경로 확인은 도구가 아니라 **절차**여야 한다: 이후 매 건 파일 저장으로 바꿨다

## 6. 미결 사항 / 알려진 한계

- **(Phase 9 후속 과제, 2026-10-01 → 같은 날 처리)** Builder의 **팀 판단 경계 변동** — "웹에서 조사해서 체크리스트로 정리"(두 동사, 분리 요구 없음)에서 3회 중 2회 팀 생성. 처리: 프롬프트 자기모순 제거(3절 2026-10-01 결정 참조), 경계 프로브 4종(`eval/boundary.py`, `python -m eval.boundary`)으로 빈도 측정 체계화. **잔여 한계**: 발생률이 낮아(수정 전 합산 2/8, 최종본 1/5 — 0/5는 기각된 중간본 측정값) 이 표본으로는 수정 효과를 검출하지 못했다 — 개선을 주장하지 않으며, 재발 관찰 시 프로브로 재측정한다
- ~~**(후속 과제, 2026-10-01)** Builder의 **"실행해줘" 요청 python_repl 부여 성향** — python_script 전/후 4/4 꾸준히 실패, dotnet_test 1/4·2/4 흔들림. 실행 범위 구분을 도구 선택 기준에 명시하는 방안 검토~~ → **같은 날 완료** — '할 수 없는 일' 섹션에 python_repl 실행 범위 명시. 부여 8/8→0/5(python_script)·3/8→0/5(dotnet_test), 셸 거절·정당-필요 부여(5/5) 유지, dev 기준값 8/8 회복 (3절 결정 로그 참조)
- ~~**(Phase 9 후속 과제, 2026-10-01)** `adfs_log_triage_team` 실대화 1회가 **270초** — 데모 영상 촬영 전 단축 검토~~ → **같은 날 완료 — 수정 전 3회 평균 255.0초 → 수정 후 3회 평균 181.8초 (-29%), 품질 기준 충족 3/3 → 3/3.** 측정 이력(각 3회, 원문은 eval/results/triage_runs/ — gitignore):
  | 구성 | 3회 평균 (개별) | 품질 | 판정 |
  |---|---|---|---|
  | 기준선 | 255.0s (282/244/240) | 3/3 | — |
  | ① analyst 분량 축소 | 267.3s (302/264/236) | — | **기각 — 시간 개선 없음(회차 편차 범위 안)** |
  | ①' 리더 전달(재작성 금지) | 341.0s (380/280/363) | — | **기각 — +86s 악화**: "그대로 전달"도 LLM은 전문을 재생성하므로 압축(재작성)이 사라져 출력이 2배가 됐다 |
  | (B) extractor 파일 범위 고정 | 243.9s (198/245/289) | 3/3 | **유지 — 결함 수정** (①-run1에서 범위 밖 샘플 4파일을 읽어 합계 20건으로 오염된 것은 ①이 아니라 이 기존 결함이 원인) |
  | (B)+(A) 리더 분량 상한 | **181.8s (175/198/173)** | **3/3** | **채택** — 최종 출력을 만드는 쪽의 분량을 줄이는 것이 유효한 레버였다. 편차도 240~282 → 173~198로 축소 |
  목표 2분(120s)에는 **미달 — 실측 그대로 기록**한다(무리하게 맞추지 않음). 구조 변경(팀 단계 축소)·샘플 건수 축소는 하지 않았고, 데모는 영상 편집으로 대응한다. 교훈: 다단 에이전트에서 내용은 중간 산출자와 최종 출력자가 **두 번 생성**된다 — 시간을 줄이려면 최종 출력자의 분량을 줄여야 하고, '그대로 전달' 지시는 절약이 아니라 비압축 재생성이다.
  **단축 작업의 품질 기준 (2026-10-01, 수정 전 고정)** — 측정 질문은 단계 3 실대화와 동일: *"작업공간의 ADFS 이벤트 로그를 분석해서 인증 실패 원인 후보와 조치 순서를 정리해줘"*. 수정 전/후 각 **3회** 실행해 소요시간·단계 수·아래 기준 충족 여부를 기록한다:
  - **Q1 전수 분류**: samples/adfs_events.csv의 오류 **12건이 전부** 유형 분류에 포함된다 (유형별 건수 합계 = 12)
  - **Q2 의미 일치**: 원인 후보가 samples/README.md의 의도한 의미와 맞는다 — 342=자격 증명 오류/계정 잠김, 364=수동 인증 래퍼(세부는 MSIS7007=RP 미등록·MSIS7065=핸들러 없음), 111=WS-Trust 처리 오류, 276=WAP 프록시 신뢰
  - **Q3 수동 절차 정직성**: 수동 조치 체크리스트가 포함되고, 에이전트가 실행할 수 없는 조치(서버 접속·명령 실행)를 실행한 것처럼 쓰지 않는다
  규칙: 팀원 모델을 낮추는 안은 품질 기준이 **하나라도** 떨어지면 기각. 샘플 건수 축소는 마지막 수단(쓰면 데모 내용이 바뀜을 기록). **목표 2분 이내 — 못 미치면 달성 수치를 그대로 보고**한다(무리하게 맞추지 않는다)
- **제거 불가 잔여 도구 (deepagents 0.7.5)**: `read_file`은 FilesystemMiddleware가 필수로 요구하고, `task`는 SubAgentMiddleware(`_REQUIRED_MIDDLEWARE`)가 제거를 막는다. 스펙이 도구를 하나도 요청하지 않아도 이 둘은 항상 노출된다. Phase 2에서 `task` 노출이 실제 위험인지(subagents=[] 상태에서 general-purpose 서브에이전트만 뜨는지) 평가한다.
- ~~**파일 백엔드**: 기본 `StateBackend` — 실제 디스크 접근 필요 여부를 결정한다~~ → 2026-08-10 결정. `FilesystemBackend(root_dir=workspace/, virtual_mode=True)`로 교체 (아래 결정 로그 참조)
- ~~**모델 최신화**: 상위 모델로 `claude-sonnet-5`·`claude-opus-5`가 존재한다. 평가 후 기본값 재검토~~ → 2026-08-10 검토 완료. **기본값을 `claude-sonnet-4-6`으로 유지한다** (아래 비교 기록). 유일하게 갈렸던 결과가 프롬프트 모순 탓으로 밝혀져 **품질 차이가 입증되지 않았다.** 6케이스 × 1회로 기본값을 바꾸는 것은 잡음에 반응하는 것이다 — 같은 스위트가 실행마다 뒤집힌다는 직접 증거가 있다. `DEEP_BUILDER_MODEL`로 언제든 바꿀 수 있다
- **Builder는 결정적이지 않다 — 평가 1회 실행은 단일 표본이다.** 같은 케이스가 같은 모델로 한 번은 단일 에이전트, 한 번은 4인 팀을 냈다. `run_evaluation(repeats=N)`을 추가해 안정성을 확인할 수 있게 했지만 **기본값은 1**이라(비용) 평소 리포트의 "27/27"은 여전히 1회 결과다. 프롬프트·레지스트리를 고친 뒤에는 `repeats`를 올려 확인한다 — 4차 확장에서 이 한계가 실측됐다: 프로브 1회 통과 케이스 2건이 전체 평가에서 간헐 실패했다
- ~~**팀원 모델 차등은 아직 열지 않는다**~~ → 2026-08-10 구현. `SubAgentSpec.model`(선택, 비우면 리더 상속), SPEC_VERSION 0.2 → 0.3. **효과는 예상보다 작았다 — 11.1%** (아래 기록)
- **모델 ID는 검증되지 않는다.** 도구 키와 MCP 서버명은 스펙 단계에서 화이트리스트를 통과해야 하지만 `model`은 자유 문자열이라 오타가 런타임까지 간다. v0.3에서 모델을 적을 자리가 팀원 수만큼 늘어 **노출면이 커졌다.** 지금은 프롬프트로만 막는다(쓸 수 있는 모델 두 개를 명시). 화이트리스트로 올릴지는 실제로 오타가 관측되는지 보고 판단한다 — 지금 고정하면 새 모델이 나올 때마다 코드를 고쳐야 한다
- ~~**MCP 도구**: `mcp:` 접두사는 스키마 레벨에서만 통과하며 Phase 1에 구현이 없다~~ → Phase 2에서 해소. `registry/mcp.py`가 로드하고 `cli.py`가 `build_agent(extra_tools=...)`로 주입한다. 실서버 검증 완료 (2026-08-10)
- ~~**HTTP transport 미검증**: `streamable_http`·`sse`는 지원 선언만 있고 설정 파싱만 테스트됐다~~ → 2026-08-10 해소. 세 transport 전부 실서버 왕복 + 헤더 전달까지 검증 (아래 기록)
- **검증한 것은 커넥터이지 특정 서버가 아니다.** 실연결 상대는 우리가 만든 `examples/echo_mcp_server.py`(FastMCP)뿐이다. 프로토콜·transport·헤더 경로는 덮지만, **다른 구현체와의 상호운용성은 여전히 미검증**이다. 서버마다 다른 인증 방식(OAuth 등), 세션 유지 정책, 스키마 방언은 실제로 붙여봐야 안다. "MCP 검증 완료"를 "임의의 MCP 서버가 붙는다"로 읽으면 안 된다
- ~~**`task` 도구 노출 평가**~~ → Phase 3에서 해소. general-purpose는 리더 도구를 상속하므로 구멍이 아니다 (위 5-3 참조)
- ~~**`--spec` 경로는 가드레일 자동 주입을 받지 못한다**~~ → 2026-08-10 해소. 가드레일을 `runtime/guardrail.py`로 내리고 스펙 파일 로드를 `runtime.spec.load_spec_file()`로 공용화했다. `cli.py --spec`과 UI 템플릿 로드가 같은 보장을 받는다 (아래 결정 로그)
- ~~**팀 실행 비용 미측정**~~ → 2026-08-10 해소. **팀은 같은 답에 약 5~6배 비싸고 5배 느리다**(아래 실측 기록). 설계 기조 "팀은 근거가 있을 때만"의 수치 근거가 생겼다
- ~~**평가 케이스 5건은 적고, 전부 통과한다 — 현재 회귀 감지력이 없다.**~~ → 2026-08-10 해소. 9건으로 늘리고 **실패를 잡아 고치는 루프를 한 바퀴 돌렸다**(아래 기록). 다만 다시 9/9이므로 같은 한계가 재발한다 — 케이스는 계속 늘려야 한다
- **`python_repl`은 임의 코드 실행이다 — 샌드박스가 아니다.** 비밀값 환경변수는 차단했지만 `os.system`·`subprocess`·절대경로 파일 접근·네트워크는 여전히 가능하다. 스펙에 이 도구를 넣는 것은 그 권한을 주는 것과 같다. 진짜 격리가 필요하면 컨테이너 등 별도 수단이 필요하다
- **평가 케이스를 계속 늘려야 한다.** 27건이 다시 전부 통과하므로, 지금 이 스위트는 이미 고친 결함이 되돌아오는 것만 잡는다. 절차는 확립됐다 — **기대값을 먼저 적고, 후보 요구를 실제로 던지고, 어긋난 것만 케이스로 고정한다.** 소진한 축: 모순 요구, 화이트리스트 밖 능력, MCP 얽힘, 도구 3~4개, 사용자 도구 지정, 팀원 간 의존, 출력 형식, 다국어, 프롬프트 지침 충돌, 장문(3문단), 도메인 용어, 수정 요구(추가·제거), 반복 일관성. **3차의 교훈은 축 선정이 결과를 지배한다는 것, 4차의 교훈은 프로브 1회 통과가 아무것도 보증하지 않는다는 것이다** — 4차 프로브 9건은 전부 통과했지만 같은 케이스가 전체 평가에서 두 번 다르게 실패했다(간헐 결함 2건). 다음 축 후보: 팀 스펙의 수정(팀원 추가·제거·도구 이동), MCP 도구가 섞인 요구의 수정, 수정 요구가 기반 스펙과 모순되는 경우
- **평가 스위트가 Builder 결함을 잡는 것과 자신의 검사 결함을 잡는 것은 다르다.** 3차 확장에서 나온 4건 중 Builder 자체 결함은 0건이고, **프롬프트 공백 1건·검사 로직 1건·심판 입력 1건·진입점 인코딩 1건**이었다. 통과율이 높다고 스위트가 건강한 것이 아니다 — 무엇을 못 보는지를 주기적으로 따로 확인해야 한다
- ~~**심판 신뢰도 미검증**~~ → 2026-08-10 해소. 부실 스펙 1/5, 무관 스펙 1/5로 판별력 확인
- ~~**자기 채점 편향**: Builder와 심판이 같은 모델~~ → 2026-08-10 해소. 심판 기본값을 `claude-haiku-4-5`로 분리 (아래 결정 로그)
- **`eval` 패키지 이름**: 내장 함수 `eval`과 겹친다. `from eval.x import y` 형태만 쓰면 안전하지만 `import eval`은 그 네임스페이스에서 내장을 가린다 (BUILD_SPEC이 지정한 이름이라 유지)
- **팀원 모델 고정**: 현재 모든 팀원이 리더와 같은 모델을 쓴다(`factory._subagent_payload`). deepagents는 팀원별 모델 오버라이드를 지원하므로, 값싼 모델로 조사시키고 비싼 모델로 종합하는 구성이 가능하다 — Phase 4 평가 후 열지 판단한다
