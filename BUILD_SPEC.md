# BUILD_SPEC.md — deep_builder_agent

## 1. 프로젝트 개요
- 명칭: **deep_builder_agent** (2026-08-08 확정. 가칭 mini-agent-builder 폐기)
- 현재 상태: **Phase 3 완료 (2026-08-10)** — subagents 활성화(AgentSpec v0.2) + 팀 템플릿 3종 + 서브에이전트 도구 격리, 테스트 106건 통과. aibrief 실연결과 LLM 실대화 데모만 외부 의존으로 보류
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

## 4. Phase 로드맵
- Phase 1 (8월, 1~3주차): CLI — 자연어 → AgentSpec → 단일 에이전트 생성·대화 ✅ **완료 (2026-08-08)**
- Phase 2 (8월 말~9월 중): registry/ 구현, 내장 도구 + MCP 커넥터, Builder 도구 자동 선택 ✅ **완료 (2026-08-10)** — 커넥터는 로컬 실서버로 검증. aibrief 실연결은 접속 정보 확보 시 설정만 추가하면 되므로 게이트를 막지 않는다
- Phase 3 (9월 말~10월 중): subagents 활성화, 팀 템플릿 2~3개, 멀티에이전트 검증 ✅ **완료 (2026-08-10)**
- Phase 4 (10월 말): Streamlit 2패널 UI + LangSmith 트레이싱 + 평가 탭
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

## 6. 미결 사항 / 알려진 한계
- **제거 불가 잔여 도구 (deepagents 0.7.5)**: `read_file`은 FilesystemMiddleware가 필수로 요구하고, `task`는 SubAgentMiddleware(`_REQUIRED_MIDDLEWARE`)가 제거를 막는다. 스펙이 도구를 하나도 요청하지 않아도 이 둘은 항상 노출된다. Phase 2에서 `task` 노출이 실제 위험인지(subagents=[] 상태에서 general-purpose 서브에이전트만 뜨는지) 평가한다.
- **파일 백엔드**: 기본 `StateBackend` — file_read/file_write는 실제 디스크가 아니라 에이전트 상태 내 가상 FS를 대상으로 한다. Phase 2에서 실제 디스크 접근 필요 여부를 결정한다.
- **모델 최신화**: 현재 기본값 `claude-sonnet-4-6`은 유효하나 상위 모델로 `claude-sonnet-5`·`claude-opus-5`가 존재한다. Phase 4 평가 탭에서 모델별 비교 후 기본값 재검토.
- ~~**MCP 도구**: `mcp:` 접두사는 스키마 레벨에서만 통과하며 Phase 1에 구현이 없다~~ → Phase 2에서 해소. `registry/mcp.py`가 로드하고 `cli.py`가 `build_agent(extra_tools=...)`로 주입한다. 실서버 검증 완료 (2026-08-10)
- ~~**`task` 도구 노출 평가**~~ → Phase 3에서 해소. general-purpose는 리더 도구를 상속하므로 구멍이 아니다 (위 5-3 참조)
- **`--spec` 경로는 가드레일 자동 주입을 받지 못한다**: `ensure_guardrail()`은 Builder 루프 안에만 있다. 손으로 쓴 스펙을 `cli.py --spec`으로 넣으면 가드레일 문장 없이도 통과한다. 지금은 템플릿 테스트(`test_templates.py::test_every_prompt_carries_the_guardrail`)로 배포본만 막아 두었다. 스키마 레벨 강제로 올릴지는 Phase 4에서 판단한다
- **팀 실행 비용 미측정**: 서브에이전트는 그래프를 따로 컴파일하고 위임마다 별도 LLM 호출이 붙는다. 단일 에이전트 대비 토큰·지연 비용을 아직 재지 않았다 (API 키 확보 후 Phase 4 평가 탭에서 측정)
- **팀원 모델 고정**: 현재 모든 팀원이 리더와 같은 모델을 쓴다(`factory._subagent_payload`). deepagents는 팀원별 모델 오버라이드를 지원하므로, 값싼 모델로 조사시키고 비싼 모델로 종합하는 구성이 가능하다 — Phase 4 평가 후 열지 판단한다
