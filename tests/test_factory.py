"""factory 가드레일 테스트 — 도구 화이트리스트가 실제로 강제되는지 확인한다.

deepagents는 스펙과 무관하게 내장 도구를 주입하므로, 스펙이 요청하지 않은
파일시스템 도구(특히 셸 실행 `execute`)가 켜지지 않는지가 핵심 검증 대상이다.
"""

import pytest

from runtime.factory import (
    BUILTIN_FS_TOOLS,
    resolve_builtin_fs_tools,
    resolve_tools,
)
from runtime.spec import AgentSpec


def _spec(**over) -> AgentSpec:
    data = dict(
        name="news_summarizer",
        description="IT 뉴스 수집·요약 에이전트",
        system_prompt="너는 IT 뉴스 요약 에이전트다.",
        tools=[],
    )
    data.update(over)
    return AgentSpec(**data)


def test_custom_tools_resolve_to_implementations():
    tools = resolve_tools(_spec(tools=["web_search", "python_repl"]))
    assert [t.name for t in tools] == ["web_search", "python_repl"]


def test_builtin_fs_keys_are_not_returned_as_custom_tools():
    # file_read/file_write는 middleware로 활성화되므로 tools 인자에 실려서는 안 된다.
    assert resolve_tools(_spec(tools=["file_read", "file_write"])) == []


def test_unimplemented_tool_raises():
    spec = _spec(tools=["mcp:aibrief"])  # 스키마는 통과하지만 Phase 1에 구현이 없다
    with pytest.raises(LookupError, match="not implemented"):
        resolve_tools(spec)


def test_execute_is_never_enabled():
    """셸 실행 도구는 어떤 스펙으로도 켜지지 않는다."""
    for tools in ([], ["file_read"], ["file_write"], ["web_search", "python_repl"]):
        assert "execute" not in resolve_builtin_fs_tools(_spec(tools=tools))


def test_write_file_requires_explicit_spec_request():
    assert "write_file" not in resolve_builtin_fs_tools(_spec(tools=["file_read"]))
    assert "write_file" in resolve_builtin_fs_tools(_spec(tools=["file_write"]))


def test_read_file_always_present():
    """FilesystemMiddleware가 read_file을 필수로 요구한다 (deepagents 0.7.5)."""
    assert resolve_builtin_fs_tools(_spec(tools=[])) == ["read_file"]


def test_builtin_map_covers_only_file_keys():
    assert set(BUILTIN_FS_TOOLS) == {"file_read", "file_write"}
