"""도구 레지스트리 — 스펙이 참조할 수 있는 도구 키의 단일 진실 원천.

Phase 1에서는 runtime/factory.py가 `_TOOL_IMPLS` dict로 이 역할을 임시로 맡았다.
Phase 2에서 이 모듈로 이관하면서 두 가지가 달라졌다:

1. AgentSpec의 허용 도구 목록이 하드코딩 상수가 아니라 레지스트리에서 파생된다.
   구현과 화이트리스트가 어긋날 수 없다.
2. Builder 프롬프트가 도구 목록·설명을 레지스트리에서 동적으로 읽는다
   (`tool_catalog()`). 도구를 추가해도 프롬프트를 손댈 필요가 없다.

도구는 두 종류다:
- **커스텀 도구**: 이 프로젝트가 구현한 LangChain 도구 (registry/builtin.py)
- **내장 FS 도구**: deepagents가 제공하는 파일시스템 도구에 위임하는 키
"""

from __future__ import annotations

from typing import Any, Callable, NamedTuple, TypeVar

# MCP 도구는 "mcp:<server_name>" 접두사로 참조한다.
MCP_PREFIX = "mcp:"

# 스펙 도구 키 → deepagents 내장 파일시스템 도구 이름.
# 이 키들은 커스텀 구현 대신 라이브러리 내장 도구로 위임한다.
BUILTIN_FS_TOOLS: dict[str, str] = {
    "file_read": "read_file",
    "file_write": "write_file",
}

# FilesystemMiddleware가 반드시 요구하는 도구. 스펙이 요청하지 않아도 항상 켜진다.
REQUIRED_FS_TOOL = "read_file"

# 내장 FS 도구 키의 설명. Builder 프롬프트가 사용한다.
_BUILTIN_FS_DESCRIPTIONS: dict[str, str] = {
    "file_read": "세션 작업공간의 파일을 읽는다.",
    "file_write": "세션 작업공간에 파일을 쓴다.",
}

_CUSTOM_TOOLS: dict[str, Any] = {}
_builtins_loaded = False

T = TypeVar("T")


class ToolInfo(NamedTuple):
    """Builder 프롬프트에 노출되는 도구 요약."""

    key: str
    description: str


def register_tool(name: str) -> Callable[[T], T]:
    """도구 구현을 이름으로 등록하는 데코레이터.

    LangChain `@tool`로 감싼 `BaseTool`을 그대로 받도록 반환값을 보존한다.
    """

    def deco(obj: T) -> T:
        _CUSTOM_TOOLS[name] = obj
        return obj

    return deco


def load_builtin_tools() -> None:
    """도구 모듈을 임포트해 register_tool 데코레이터를 실행시킨다.

    지연 임포트: registry.builtin이 이 모듈을 임포트하므로 순환 참조를 피한다.
    반복 호출해도 안전하다.
    """
    global _builtins_loaded
    if _builtins_loaded:
        return
    import registry.builtin  # noqa: F401

    _builtins_loaded = True


def custom_tool_keys() -> list[str]:
    """등록된 커스텀 도구 키 목록."""
    load_builtin_tools()
    return sorted(_CUSTOM_TOOLS)


def allowed_tool_keys() -> set[str]:
    """AgentSpec이 참조할 수 있는 도구 키 전체 (MCP 접두사 제외)."""
    return set(custom_tool_keys()) | set(BUILTIN_FS_TOOLS)


def get_custom_tool(key: str) -> Any:
    """등록된 커스텀 도구 구현을 반환한다.

    Raises:
        LookupError: 해당 키의 구현이 없을 때.
    """
    load_builtin_tools()
    if key not in _CUSTOM_TOOLS:
        raise LookupError(f"tool referenced but not implemented: {key!r}")
    return _CUSTOM_TOOLS[key]


def tool_catalog() -> list[ToolInfo]:
    """Builder 프롬프트에 넣을 도구 목록을 만든다.

    커스텀 도구의 설명은 LangChain 도구의 description 첫 줄에서 가져온다.
    """
    load_builtin_tools()

    catalog = [
        ToolInfo(key, _BUILTIN_FS_DESCRIPTIONS[key]) for key in sorted(BUILTIN_FS_TOOLS)
    ]
    for key in sorted(_CUSTOM_TOOLS):
        raw = (getattr(_CUSTOM_TOOLS[key], "description", "") or "").strip()
        catalog.append(ToolInfo(key, raw.splitlines()[0] if raw else ""))
    return sorted(catalog)
