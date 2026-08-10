# BUILD_SPEC.md — deep_builder_agent

## 1. 프로젝트 개요
- 명칭: **deep_builder_agent** (2026-08-08 확정. 가칭 mini-agent-builder 폐기)
- 현재 상태: **Phase 1~4 완료 (2026-08-10)** — CLI·Streamlit UI, 팀(subagents), MCP 연동, LangSmith 트레이싱, 평가 레이어. **테스트 188건 통과, 전 경로 실호출 검증 완료.** 남은 외부 의존은 aibrief 접속 정보 하나뿐
- 보고서: [REPORT.md](REPORT.md)
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
- 2026-08-10 (Phase 2): **MCP 검증을 외부 서비스에서 분리**. aibrief 접속 정보가 없어 커넥터가 미검증으로 남는 상황을 피하려고, 로컬 stdio 서버(`examples/echo_mcp_server.py`)를 검증 픽스처로 채택했다. 외부 계정·네트워크 없이 커넥터 회귀를 상시 검증할 수 있고, aibrief는 설정 한 줄로 붙는 문제로 축소된다
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
- 2026-08-10: **비용 실측** — 하루 작업 기준 LLM 호출 138건, 토큰 566,654(입력 445,240 / 출력 121,414), 정가 약 $3.16(캐싱 반영 $2.84). **출력이 비용의 58%**다(단가가 5배). 가장 큰 반복 지출은 평가 실행(1회 = Builder 9회 호출)이므로 프롬프트·레지스트리 변경 시에만 돌린다. LangSmith 화면의 금액은 LangSmith 청구액이 아니라 토큰에서 계산한 **모델 비용 표시**다
- 2026-08-10: 평가 케이스는 **추측이 아니라 실측으로 늘린다.** 기대값을 먼저 적고 → 후보 요구를 실제로 던지고 → 어긋난 것만 고정한다. 이 절차로 4건을 찾았고, 그중 하나(`over_selection_bait`)는 과잉 선택을 노렸는데 정반대인 과소 선택이 나왔다 — 추측으로는 못 잡을 지점이었다

## 4. Phase 로드맵
- Phase 1 (8월, 1~3주차): CLI — 자연어 → AgentSpec → 단일 에이전트 생성·대화 ✅ **완료 (2026-08-08)**
- Phase 2 (8월 말~9월 중): registry/ 구현, 내장 도구 + MCP 커넥터, Builder 도구 자동 선택 ✅ **완료 (2026-08-10)** — 커넥터는 로컬 실서버로 검증. aibrief 실연결은 접속 정보 확보 시 설정만 추가하면 되므로 게이트를 막지 않는다
- Phase 3 (9월 말~10월 중): subagents 활성화, 팀 템플릿 2~3개, 멀티에이전트 검증 ✅ **완료 (2026-08-10)**
- Phase 4 (10월 말): Streamlit 2패널 UI + LangSmith 트레이싱 + 평가 탭 ✅ **완료 (2026-08-10)**
- 11월 초: 보고서(개조식)·README·데모 영상 마무리. 2주 버퍼

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
- `cli.py`: Windows 콘솔 cp949에서 이모지 출력 시 UnicodeEncodeError, 파이프 입력 시 한글이 서로게이트로 디코딩됨. `_force_utf8_stdio()`로 stdin/stdout/stderr를 UTF-8 고정

## 5-2. Phase 2 체크리스트
- [x] `registry/` 모듈 구현 — 레지스트리 코어(registry.py), 도구 구현(builtin.py), MCP 커넥터(mcp.py)
- [x] `runtime/tools.py` → `registry/builtin.py` 이관, factory는 "스펙 → deepagents 번역"만 담당
- [x] 허용 도구 목록을 레지스트리에서 파생 (spec.ALLOWED_TOOLS 상수 제거)
- [x] Builder 도구 자동 선택 — 프롬프트가 `tool_catalog()`에서 도구 목록·설명을 렌더링
- [x] MCP 커넥터 골격 + `mcp_servers.json` 설정 스키마 + `${ENV_VAR}` 치환
- [x] MCP 서버명을 스펙 검증 단계에서 확인 (미설정 서버 거부)
- [x] **MCP 실연결 검증** — 로컬 echo MCP 서버로 커넥터 전 구간 확인 (통합 테스트 5건)
- [ ] **aibrief 실연결 검증** — 🚧 외부 의존으로 보류. 접속 정보(transport/URL/인증) 확보 후 진행.
      커넥터 자체는 실서버로 검증했으므로 남은 일은 `mcp_servers.json`에 aibrief 항목을 넣는 것뿐이다
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
- [x] `eval/` 평가 레이어 — 케이스 데이터셋, 기계적 검사 4종, LLM 심판, 실행·집계
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

## 6. 미결 사항 / 알려진 한계
- **제거 불가 잔여 도구 (deepagents 0.7.5)**: `read_file`은 FilesystemMiddleware가 필수로 요구하고, `task`는 SubAgentMiddleware(`_REQUIRED_MIDDLEWARE`)가 제거를 막는다. 스펙이 도구를 하나도 요청하지 않아도 이 둘은 항상 노출된다. Phase 2에서 `task` 노출이 실제 위험인지(subagents=[] 상태에서 general-purpose 서브에이전트만 뜨는지) 평가한다.
- ~~**파일 백엔드**: 기본 `StateBackend` — 실제 디스크 접근 필요 여부를 결정한다~~ → 2026-08-10 결정. `FilesystemBackend(root_dir=workspace/, virtual_mode=True)`로 교체 (아래 결정 로그 참조)
- **모델 최신화**: 현재 기본값 `claude-sonnet-4-6`은 유효하나 상위 모델로 `claude-sonnet-5`·`claude-opus-5`가 존재한다. Phase 4 평가 탭에서 모델별 비교 후 기본값 재검토.
- ~~**MCP 도구**: `mcp:` 접두사는 스키마 레벨에서만 통과하며 Phase 1에 구현이 없다~~ → Phase 2에서 해소. `registry/mcp.py`가 로드하고 `cli.py`가 `build_agent(extra_tools=...)`로 주입한다. 실서버 검증 완료 (2026-08-10)
- ~~**`task` 도구 노출 평가**~~ → Phase 3에서 해소. general-purpose는 리더 도구를 상속하므로 구멍이 아니다 (위 5-3 참조)
- **`--spec` 경로는 가드레일 자동 주입을 받지 못한다**: `ensure_guardrail()`은 Builder 루프 안에만 있다. 손으로 쓴 스펙을 `cli.py --spec`으로 넣으면 가드레일 문장 없이도 통과한다. 지금은 템플릿 테스트(`test_templates.py::test_every_prompt_carries_the_guardrail`)로 배포본만 막아 두었다. 스키마 레벨 강제로 올릴지는 Phase 4에서 판단한다
- **팀 실행 비용 미측정**: 서브에이전트는 그래프를 따로 컴파일하고 위임마다 별도 LLM 호출이 붙는다. 단일 에이전트 대비 토큰·지연 비용을 아직 재지 않았다. 측정 수단은 갖췄다(LangSmith 트레이싱) — 키만 있으면 바로 잰다
- ~~**평가 케이스 5건은 적고, 전부 통과한다 — 현재 회귀 감지력이 없다.**~~ → 2026-08-10 해소. 9건으로 늘리고 **실패를 잡아 고치는 루프를 한 바퀴 돌렸다**(아래 기록). 다만 다시 9/9이므로 같은 한계가 재발한다 — 케이스는 계속 늘려야 한다
- **평가 케이스를 계속 늘려야 한다.** 9건이 다시 전부 통과하므로, 지금 이 스위트는 오늘 고친 결함이 되돌아오는 것만 잡는다. 새 결함을 찾으려면 같은 절차를 반복해야 한다 — **기대값을 먼저 적고, 후보 요구를 실제로 던지고, 어긋난 것만 케이스로 고정한다.** 아직 안 건드린 축: 서로 모순되는 요구, 화이트리스트 밖 능력을 요구하는 경우(이메일·DB 등), MCP 도구가 얽힌 요구, 한 요구에 도구 3개 이상
- ~~**심판 신뢰도 미검증**~~ → 2026-08-10 해소. 부실 스펙 1/5, 무관 스펙 1/5로 판별력 확인
- ~~**자기 채점 편향**: Builder와 심판이 같은 모델~~ → 2026-08-10 해소. 심판 기본값을 `claude-haiku-4-5`로 분리 (아래 결정 로그)
- **`eval` 패키지 이름**: 내장 함수 `eval`과 겹친다. `from eval.x import y` 형태만 쓰면 안전하지만 `import eval`은 그 네임스페이스에서 내장을 가린다 (BUILD_SPEC이 지정한 이름이라 유지)
- **팀원 모델 고정**: 현재 모든 팀원이 리더와 같은 모델을 쓴다(`factory._subagent_payload`). deepagents는 팀원별 모델 오버라이드를 지원하므로, 값싼 모델로 조사시키고 비싼 모델로 종합하는 구성이 가능하다 — Phase 4 평가 후 열지 판단한다
