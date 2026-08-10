"""AgentSpec → deepagents 에이전트 인스턴스 변환.

도구 레지스트리는 Phase 2에서 registry/ 모듈로 이관했다. 이 모듈은 이제
"검증된 스펙을 deepagents 호출로 번역"하는 일만 한다.

deepagents 0.7.5 검증 결과 (2026-08-08, 설치본 소스 대조):
- `create_deep_agent(model=..., tools=..., system_prompt=..., subagents=...)` 시그니처 확인.
- `model`은 `"claude-sonnet-4-6"` 같은 순수 문자열도 `ChatAnthropic`으로 해석된다.
- create_deep_agent은 스펙과 무관하게 내장 도구 9종을 주입한다:
  ls, read_file, write_file, edit_file, delete, glob, grep, execute, task.
  `execute`는 셸 실행이므로 그대로 두면 도구 화이트리스트 가드레일이 무력화된다.
  → `middleware=[FilesystemMiddleware(tools=[...])]`로 파일시스템 도구를 최소 집합만 남긴다.
- 제거 불가 잔여 도구: `read_file`(FilesystemMiddleware 필수), `task`(SubAgentMiddleware 필수).
  BUILD_SPEC.md "6. 미결 사항"에 한계로 기록한다.
- 파일시스템 백엔드는 `FilesystemBackend(root_dir=workspace/, virtual_mode=True)`로
  교체했다. deepagents 기본값 `StateBackend`는 세션 내 가상 FS라 실제 문서를 읽지
  못했고(doc_qa_team이 설명대로 동작하지 않는 것을 실측), 그렇다고 루트를 프로젝트
  전체로 열면 `.env`가 읽힌다. `workspace/` 전용 디렉터리가 그 사이의 답이다.
  (2026-08-10 결정 — BUILD_SPEC 참조)

Phase 3 추가 검증 (2026-08-10, 실측):
- **메인 에이전트의 FilesystemMiddleware는 서브에이전트에 전파되지 않는다.**
  메인을 read_file로 묶어도, 선언된 서브에이전트는 기본 스택을 새로 받아
  execute(셸)를 포함한 내장 도구 8종을 전부 갖는다. 위임 한 번이면 화이트리스트가 뚫린다.
  → 서브에이전트마다 `FilesystemMiddleware`를 명시적으로 붙인다(`_subagent_payload`).
  이것이 Phase 3에서 가장 중요한 한 줄이다.
"""

from __future__ import annotations

from typing import Any

from registry import (
    BUILTIN_FS_TOOLS,
    MCP_PREFIX,
    REQUIRED_FS_TOOL,
    get_custom_tool,
)
from runtime.config import workspace_dir
from runtime.spec import AgentSpec, SubAgentSpec


def _resolve_custom_tools(keys: list[str]) -> list[Any]:
    """커스텀 도구 키를 구현으로 바꾼다. FS·MCP 키는 이 경로가 아니다.

    Raises:
        LookupError: 구현이 레지스트리에 없을 때.
    """
    missing: list[str] = []
    tools: list[Any] = []
    for key in keys:
        if key in BUILTIN_FS_TOOLS or key.startswith(MCP_PREFIX):
            continue
        try:
            tools.append(get_custom_tool(key))
        except LookupError:
            missing.append(key)
    if missing:
        raise LookupError(f"tools referenced but not implemented: {missing}")
    return tools


def _resolve_mcp_tools(
    keys: list[str], mcp_tools_by_server: dict[str, list[Any]] | None
) -> list[Any]:
    """`mcp:<server>` 키를 그 서버가 제공한 도구 목록으로 바꾼다.

    매핑이 주어지지 않으면 빈 목록을 돌려준다 — 메인 에이전트는 Phase 2부터
    `extra_tools`로 MCP 도구를 받아왔고 그 경로를 깨지 않는다.

    Raises:
        LookupError: 매핑은 주어졌는데 그 안에 해당 서버가 없을 때.
                     서브에이전트의 MCP 참조가 조용히 사라지는 것을 막는다.
    """
    if mcp_tools_by_server is None:
        return []

    tools: list[Any] = []
    missing: list[str] = []
    for key in keys:
        if not key.startswith(MCP_PREFIX):
            continue
        server = key[len(MCP_PREFIX) :]
        if server not in mcp_tools_by_server:
            missing.append(key)
            continue
        tools.extend(mcp_tools_by_server[server])
    if missing:
        raise LookupError(f"MCP servers referenced but not loaded: {missing}")
    return tools


def resolve_tools(spec: AgentSpec) -> list[Any]:
    """스펙의 커스텀 도구 참조를 실제 구현으로 해석한다.

    내장 파일시스템 도구(BUILTIN_FS_TOOLS)는 여기서 제외된다 —
    그것들은 middleware 설정으로 활성화되기 때문이다.
    MCP 도구는 별도 경로(registry.mcp)에서 비동기로 로드한다.

    Raises:
        LookupError: 스펙이 참조한 도구의 구현이 레지스트리에 없을 때.
    """
    return _resolve_custom_tools(spec.tools)


def _builtin_fs_names(keys: list[str]) -> list[str]:
    """요청된 내장 파일시스템 도구 이름 목록을 만든다.

    `read_file`은 FilesystemMiddleware가 필수로 요구하므로 항상 포함된다.
    """
    names = [REQUIRED_FS_TOOL]
    for key, builtin_name in BUILTIN_FS_TOOLS.items():
        if key in keys and builtin_name not in names:
            names.append(builtin_name)
    return names


def resolve_builtin_fs_tools(spec: AgentSpec) -> list[str]:
    """스펙이 요청한 내장 파일시스템 도구 이름 목록을 만든다."""
    return _builtin_fs_names(spec.tools)


def _filesystem_middleware(tool_keys: list[str]):
    """요청된 FS 도구만 켠 FilesystemMiddleware를 만든다.

    백엔드를 `workspace/`에 묶는다. 기본값인 StateBackend는 세션 내 가상 FS라
    실제 문서를 읽지 못했고(doc_qa_team이 설명대로 동작하지 않았다), 반대로
    루트를 프로젝트 전체로 열면 `.env`가 읽힌다. 전용 디렉터리가 그 사이의 답이다.

    `virtual_mode=True`가 `..`·`~`·root_dir 밖 절대경로를 차단한다. 다만
    프로세스 격리는 아니므로 workspace 안에 비밀값을 두지 않는 규칙이 함께 필요하다.
    """
    from deepagents import FilesystemMiddleware
    from deepagents.backends import FilesystemBackend

    return FilesystemMiddleware(
        tools=_builtin_fs_names(tool_keys),
        backend=FilesystemBackend(root_dir=workspace_dir(), virtual_mode=True),
    )


def _subagent_payload(
    sub: SubAgentSpec,
    *,
    model: str,
    mcp_tools_by_server: dict[str, list[Any]] | None,
) -> dict[str, Any]:
    """SubAgentSpec을 deepagents `SubAgent` TypedDict로 번역한다.

    `middleware`가 핵심이다. 이걸 빼면 서브에이전트가 내장 도구 전체(execute 포함)를
    물려받아 도구 화이트리스트가 무의미해진다 — 실측으로 확인한 동작이다.
    """
    return {
        "name": sub.name,
        "description": sub.description,
        "system_prompt": sub.system_prompt,
        # 모델은 리더와 동일하게 고정한다. 서브에이전트만 몰래 다른 모델을 쓰는 일이 없도록.
        "model": model,
        "tools": [
            *_resolve_custom_tools(sub.tools),
            *_resolve_mcp_tools(sub.tools, mcp_tools_by_server),
        ],
        "middleware": [_filesystem_middleware(sub.tools)],
    }


def resolve_subagents(
    spec: AgentSpec, *, mcp_tools_by_server: dict[str, list[Any]] | None = None
) -> list[dict[str, Any]]:
    """스펙의 서브에이전트를 deepagents가 받는 형태로 변환한다.

    Raises:
        LookupError: 서브에이전트가 참조한 도구·MCP 서버를 해석할 수 없을 때.
    """
    return [
        _subagent_payload(sub, model=spec.model, mcp_tools_by_server=mcp_tools_by_server)
        for sub in spec.subagents
    ]


def build_agent(
    spec: AgentSpec,
    *,
    extra_tools: list[Any] | None = None,
    mcp_tools_by_server: dict[str, list[Any]] | None = None,
):
    """검증된 AgentSpec으로 deepagents 에이전트를 생성한다.

    Args:
        spec: 검증된 명세.
        extra_tools: 레지스트리 밖에서 준비한 리더용 추가 도구
            (예: MCP 커넥터가 로드한 도구 목록).
        mcp_tools_by_server: 서버명 → 도구 목록 매핑. 서브에이전트의 `mcp:` 참조를
            해석하는 데 쓴다. 없으면 서브에이전트는 MCP 도구를 받지 못한다.
    """
    # 지연 임포트: 테스트가 deepagents 없이도 스펙 검증을 돌릴 수 있게 한다.
    from deepagents import create_deep_agent

    tools = [*resolve_tools(spec), *(extra_tools or [])]
    subagents = resolve_subagents(spec, mcp_tools_by_server=mcp_tools_by_server)

    return create_deep_agent(
        model=spec.model,
        tools=tools,
        system_prompt=spec.system_prompt,
        middleware=[_filesystem_middleware(spec.tools)],
        # 빈 리스트를 넘기면 deepagents가 "최소 1개" 검사에 걸리므로 None으로 접는다.
        subagents=subagents or None,
    )
