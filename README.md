# deep_builder_agent

자연어 요구를 받아 AI 에이전트를 **생성·실행**하는 빌더. LangChain deepagents 하네스 위에서
Pydantic 스펙(`AgentSpec`)이 도구 화이트리스트와 가드레일을 강제한다.

> 현재 상태: **Phase 1 완료** (단일 에이전트 생성·대화 CLI).
> 모든 설계 결정과 진행 상황은 [BUILD_SPEC.md](BUILD_SPEC.md)에 있다.

## 동작 방식

```
자연어 요구
   ↓  builder/    LLM 호출 → JSON 파싱 → 가드레일 문장 주입
   ↓  runtime/    AgentSpec 검증 (도구 화이트리스트 / subagents 게이트)
   ↓  runtime/    deepagents 인스턴스화 (요청한 도구만 노출)
대화
```

핵심은 **LLM의 준수를 신뢰하지 않는 것**이다.

- 도구 화이트리스트는 프롬프트 요청이 아니라 Pydantic 밸리데이터가 거부한다.
- 가드레일 문장은 LLM이 빠뜨리면 `ensure_guardrail()`이 코드로 삽입한다.
- deepagents가 자동 주입하는 셸 실행 도구(`execute`)는 `FilesystemMiddleware` 재정의로 차단한다.
- 검증에 실패하면 에러 메시지를 Builder에게 되돌려 최대 2회 재생성한다.

## 설치

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

cp .env.example .env    # ANTHROPIC_API_KEY를 채운다
```

| 환경변수 | 필수 | 용도 |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Builder와 생성된 에이전트 |
| `TAVILY_API_KEY` | — | `web_search` 도구. 없으면 도구가 명확한 에러를 반환한다 |
| `DEEP_BUILDER_MODEL` | — | Builder LLM 모델 (기본 `claude-sonnet-4-6`) |

## 사용법

```bash
# 자연어로 에이전트를 만들고 바로 대화
python cli.py "웹 검색으로 최신 IT 뉴스를 찾아 3줄로 요약해주는 에이전트 만들어줘"

# 저장된 스펙으로 대화
python cli.py --spec specs/it_news_summarizer.json

# 생성·검증만 하고 종료 (대화 없음)
python cli.py "..." --no-chat
```

생성된 스펙은 `specs/<name>.json`에 저장된다.

## AgentSpec v0.1

```json
{
  "spec_version": "0.1",
  "name": "news_summarizer",
  "description": "IT 뉴스를 수집해 핵심만 요약하는 에이전트",
  "system_prompt": "너는 IT 뉴스 요약 에이전트다. ...",
  "model": "claude-sonnet-4-6",
  "tools": ["web_search"],
  "subagents": []
}
```

- `tools` 허용값: `web_search`, `python_repl`, `file_read`, `file_write` (그 외는 거부)
- `subagents`는 Phase 3까지 빈 배열만 허용 (`spec.py` 밸리데이터가 강제)
- `mcp:` 접두사는 스키마를 통과하지만 구현은 Phase 2

## 개발

```bash
./.venv/Scripts/python.exe -m pytest tests/ -q
```

작업 규칙은 [CLAUDE.md](CLAUDE.md) 참조.

## 알려진 한계

- `read_file`과 `task`는 deepagents가 필수 미들웨어로 강제하므로 스펙이 요청하지 않아도 항상 노출된다.
- 파일 도구는 기본 `StateBackend`(에이전트 상태 내 가상 FS)를 대상으로 하며 실제 디스크가 아니다.
