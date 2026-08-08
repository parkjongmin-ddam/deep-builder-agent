# BUILD_SPEC.md — deep_builder_agent

## 1. 프로젝트 개요
- 목표: 자연어 대화로 AI 에이전트를 생성·실행·평가하는 빌더 제작 (브레인크루 Deep Agent Builder 미니 재현)
- 제출: 2026년 11월, 생성 AI 교육과정 파이널 과제
- 기반: LangChain deepagents(하네스), LangGraph 런타임, Claude Code로 개발

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

## 4. Phase 로드맵
- Phase 1 (8월, 1~3주차): CLI — 자연어 → AgentSpec → 단일 에이전트 생성·대화 ✅ **완료 (2026-08-08)**
- Phase 2 (8월 말~9월 중): registry/ 구현, 내장 도구 + MCP 커넥터(aibrief 연결 검증), Builder 도구 자동 선택
- Phase 3 (9월 말~10월 중): subagents 활성화, 팀 템플릿 2~3개, 멀티에이전트 검증
- Phase 4 (10월 말): Streamlit 2패널 UI + LangSmith 트레이싱 + 평가 탭
- 11월 초: 보고서(개조식)·README·데모 영상·제출. 2주 버퍼

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

## 6. 미결 사항 / 알려진 한계
- **제거 불가 잔여 도구 (deepagents 0.7.5)**: `read_file`은 FilesystemMiddleware가 필수로 요구하고, `task`는 SubAgentMiddleware(`_REQUIRED_MIDDLEWARE`)가 제거를 막는다. 스펙이 도구를 하나도 요청하지 않아도 이 둘은 항상 노출된다. Phase 2에서 `task` 노출이 실제 위험인지(subagents=[] 상태에서 general-purpose 서브에이전트만 뜨는지) 평가한다.
- **파일 백엔드**: 기본 `StateBackend` — file_read/file_write는 실제 디스크가 아니라 에이전트 상태 내 가상 FS를 대상으로 한다. Phase 2에서 실제 디스크 접근 필요 여부를 결정한다.
- **모델 최신화**: 현재 기본값 `claude-sonnet-4-6`은 유효하나 상위 모델로 `claude-sonnet-5`·`claude-opus-5`가 존재한다. Phase 4 평가 탭에서 모델별 비교 후 기본값 재검토.
- **MCP 도구**: `mcp:` 접두사는 스키마 레벨에서만 통과하며 Phase 1에 구현이 없다 — `resolve_tools()`가 `LookupError`를 던진다 (설계된 동작).
