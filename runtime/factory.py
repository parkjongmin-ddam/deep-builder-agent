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
- 기본 파일시스템 백엔드는 `StateBackend`(에이전트 상태 내 가상 FS)이므로
  file_read/file_write는 실제 디스크가 아니라 세션 상태를 대상으로 한다.
"""

from __future__ import annotations

from typing import Any

from registry import (
    BUILTIN_FS_TOOLS,
    MCP_PREFIX,
    REQUIRED_FS_TOOL,
    get_custom_tool,
)
from runtime.spec import AgentSpec


def resolve_tools(spec: AgentSpec) -> list[Any]:
    """스펙의 커스텀 도구 참조를 실제 구현으로 해석한다.

    내장 파일시스템 도구(BUILTIN_FS_TOOLS)는 여기서 제외된다 —
    그것들은 middleware 설정으로 활성화되기 때문이다.
    MCP 도구는 별도 경로(resolve_mcp_tools)에서 비동기로 로드한다.

    Raises:
        LookupError: 스펙이 참조한 도구의 구현이 레지스트리에 없을 때.
    """
    custom_keys = [
        t
        for t in spec.tools
        if t not in BUILTIN_FS_TOOLS and not t.startswith(MCP_PREFIX)
    ]
    missing = []
    tools = []
    for key in custom_keys:
        try:
            tools.append(get_custom_tool(key))
        except LookupError:
            missing.append(key)
    if missing:
        raise LookupError(f"tools referenced but not implemented: {missing}")
    return tools


def resolve_builtin_fs_tools(spec: AgentSpec) -> list[str]:
    """스펙이 요청한 내장 파일시스템 도구 이름 목록을 만든다.

    `read_file`은 FilesystemMiddleware가 필수로 요구하므로 항상 포함된다.
    """
    names = [REQUIRED_FS_TOOL]
    for key, builtin_name in BUILTIN_FS_TOOLS.items():
        if key in spec.tools and builtin_name not in names:
            names.append(builtin_name)
    return names


def build_agent(spec: AgentSpec, *, extra_tools: list[Any] | None = None):
    """검증된 AgentSpec으로 deepagents 에이전트를 생성한다.

    Args:
        spec: 검증된 명세.
        extra_tools: 레지스트리 밖에서 준비한 추가 도구 (예: MCP 커넥터가 로드한 도구).
    """
    # 지연 임포트: 테스트가 deepagents 없이도 스펙 검증을 돌릴 수 있게 한다.
    from deepagents import FilesystemMiddleware, create_deep_agent

    tools = [*resolve_tools(spec), *(extra_tools or [])]

    return create_deep_agent(
        model=spec.model,
        tools=tools,
        system_prompt=spec.system_prompt,
        middleware=[FilesystemMiddleware(tools=resolve_builtin_fs_tools(spec))],
        # Phase 3 전까지 spec.subagents는 항상 [] (spec.py 밸리데이터가 보장)
    )
