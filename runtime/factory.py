"""AgentSpec → deepagents 에이전트 인스턴스 변환.

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

from typing import Any, Callable, TypeVar

from runtime.spec import AgentSpec

# Phase 1: 레지스트리 대체용 임시 매핑. Phase 2에서 registry 모듈로 이관.
_TOOL_IMPLS: dict[str, Any] = {}

# 스펙 도구 키 → deepagents 내장 파일시스템 도구 이름.
# 이 키들은 커스텀 구현 대신 라이브러리 내장 도구로 위임한다.
BUILTIN_FS_TOOLS: dict[str, str] = {
    "file_read": "read_file",
    "file_write": "write_file",
}

# FilesystemMiddleware가 반드시 요구하는 도구. 스펙이 요청하지 않아도 항상 켜진다.
_REQUIRED_FS_TOOL = "read_file"

T = TypeVar("T")


def register_tool(name: str) -> Callable[[T], T]:
    """도구 구현을 이름으로 등록하는 데코레이터.

    LangChain `@tool`로 감싼 `BaseTool`을 그대로 받도록 반환값을 보존한다.
    """

    def deco(obj: T) -> T:
        _TOOL_IMPLS[name] = obj
        return obj

    return deco


def _load_tool_implementations() -> None:
    """도구 모듈을 임포트해 register_tool 데코레이터를 실행시킨다.

    지연 임포트: runtime.tools가 이 모듈을 임포트하므로 순환 참조를 피한다.
    """
    import runtime.tools  # noqa: F401


def resolve_tools(spec: AgentSpec) -> list[Any]:
    """스펙의 커스텀 도구 참조를 실제 구현으로 해석한다.

    내장 파일시스템 도구(BUILTIN_FS_TOOLS)는 여기서 제외된다 —
    그것들은 middleware 설정으로 활성화되기 때문이다.
    """
    _load_tool_implementations()
    custom_keys = [t for t in spec.tools if t not in BUILTIN_FS_TOOLS]
    missing = [t for t in custom_keys if t not in _TOOL_IMPLS]
    if missing:
        raise LookupError(f"tools referenced but not implemented: {missing}")
    return [_TOOL_IMPLS[t] for t in custom_keys]


def resolve_builtin_fs_tools(spec: AgentSpec) -> list[str]:
    """스펙이 요청한 내장 파일시스템 도구 이름 목록을 만든다.

    `read_file`은 FilesystemMiddleware가 필수로 요구하므로 항상 포함된다.
    """
    names = [_REQUIRED_FS_TOOL]
    for key, builtin_name in BUILTIN_FS_TOOLS.items():
        if key in spec.tools and builtin_name not in names:
            names.append(builtin_name)
    return names


def build_agent(spec: AgentSpec):
    """검증된 AgentSpec으로 deepagents 에이전트를 생성한다."""
    # 지연 임포트: 테스트가 deepagents 없이도 스펙 검증을 돌릴 수 있게 한다.
    from deepagents import FilesystemMiddleware, create_deep_agent

    return create_deep_agent(
        model=spec.model,
        tools=resolve_tools(spec),
        system_prompt=spec.system_prompt,
        middleware=[FilesystemMiddleware(tools=resolve_builtin_fs_tools(spec))],
        # Phase 3 전까지 spec.subagents는 항상 [] (spec.py 밸리데이터가 보장)
    )
