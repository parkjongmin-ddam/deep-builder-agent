"""factory 가드레일 테스트 — 도구 화이트리스트가 실제로 강제되는지 확인한다.

deepagents는 스펙과 무관하게 내장 도구를 주입하므로, 스펙이 요청하지 않은
파일시스템 도구(특히 셸 실행 `execute`)가 켜지지 않는지가 핵심 검증 대상이다.
"""

import pytest

from registry import BUILTIN_FS_TOOLS
from runtime.factory import (
    resolve_builtin_fs_tools,
    resolve_subagents,
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


def test_mcp_tools_are_not_resolved_as_custom(monkeypatch):
    """mcp: 키는 registry.mcp 경로가 로드한다. 커스텀 도구 해석 대상이 아니다."""
    monkeypatch.setattr("runtime.spec.configured_server_names", lambda: {"aibrief"})
    assert resolve_tools(_spec(tools=["mcp:aibrief"])) == []


def test_unimplemented_tool_raises():
    """스펙 검증을 우회해 들어온 미구현 키는 런타임에서 막힌다."""
    spec = _spec(tools=[])
    spec.tools = ["ghost_tool"]  # 밸리데이터를 우회한 직접 대입
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
    """파일 관련 키만 내장 위임 대상이다 — execute/delete 같은 것은 여기 없다."""
    assert set(BUILTIN_FS_TOOLS) == {"file_read", "file_write", "file_list"}


def test_file_list_enables_the_ls_tool():
    """경로를 모를 때 목록을 볼 수 있어야 한다 (doc_qa_team이 여기서 막혔다)."""
    assert "ls" in resolve_builtin_fs_tools(_spec(tools=["file_list"]))
    assert "ls" not in resolve_builtin_fs_tools(_spec(tools=["file_read"]))


# --- Phase 3: subagents ---------------------------------------------------


def _sub(**over) -> dict:
    d = dict(
        name="researcher",
        description="조사 담당",
        system_prompt="너는 조사 담당이다.",
        tools=["web_search"],
    )
    d.update(over)
    return d


class _FakeTool:
    """MCP 도구 자리를 채우는 최소 스텁."""

    def __init__(self, name: str):
        self.name = name


def _middleware_fs_tools(payload: dict) -> set[str]:
    """서브에이전트 payload의 FilesystemMiddleware가 허용한 도구 이름.

    `middleware.tools`는 이름이 아니라 도구 객체를 담고 있다.
    """
    return {
        getattr(tool, "name", tool)
        for mw in payload["middleware"]
        for tool in getattr(mw, "tools", [])
    }


def _subagent_tool_names(agent) -> dict[str, set[str]]:
    """컴파일된 서브에이전트 그래프별로 실제 노출된 도구 이름을 뽑는다."""
    node = agent.nodes["tools"]
    bound = getattr(node, "bound", node)
    task = bound.tools_by_name["task"]
    result: dict[str, set[str]] = {}
    for cell in (task.func or task.coroutine).__closure__ or ():
        value = cell.cell_contents
        if not isinstance(value, dict):
            continue
        for key, graph in value.items():
            if not hasattr(graph, "nodes") or "tools" not in graph.nodes:
                continue
            sub_node = graph.nodes["tools"]
            sub_bound = getattr(sub_node, "bound", sub_node)
            result[key] = set(getattr(sub_bound, "tools_by_name", {}))
    return result


def test_subagent_payload_matches_deepagents_keys():
    """deepagents SubAgent TypedDict가 요구하는 키로 번역된다."""
    payload = resolve_subagents(_spec(subagents=[_sub()]))[0]

    assert payload["name"] == "researcher"
    assert payload["system_prompt"].startswith("너는 조사 담당이다")
    assert [t.name for t in payload["tools"]] == ["web_search"]


def test_subagent_inherits_leader_model():
    """팀원만 몰래 다른 모델을 쓰지 않는다."""
    spec = _spec(model="claude-opus-5", subagents=[_sub()])

    assert resolve_subagents(spec)[0]["model"] == "claude-opus-5"


def test_subagent_gets_its_own_filesystem_middleware():
    """이 middleware가 없으면 팀원이 내장 도구 전체(execute 포함)를 물려받는다."""
    payload = resolve_subagents(_spec(subagents=[_sub()]))[0]

    assert payload["middleware"], "서브에이전트에 FilesystemMiddleware가 없다"


def test_subagent_write_file_requires_explicit_request():
    read_only = resolve_subagents(_spec(subagents=[_sub()]))[0]
    writer = resolve_subagents(_spec(subagents=[_sub(tools=["file_write"])]))[0]

    assert "write_file" not in _middleware_fs_tools(read_only)
    assert "write_file" in _middleware_fs_tools(writer)


def test_subagent_mcp_reference_without_mapping_is_loud(monkeypatch):
    """팀원의 MCP 참조가 조용히 사라지지 않는다."""
    monkeypatch.setattr("runtime.spec.configured_server_names", lambda: {"aibrief"})
    spec = _spec(subagents=[_sub(tools=["mcp:aibrief"])])

    with pytest.raises(LookupError, match="not loaded"):
        resolve_subagents(spec, mcp_tools_by_server={})


def test_subagent_mcp_tools_are_injected_when_mapped(monkeypatch):
    monkeypatch.setattr("runtime.spec.configured_server_names", lambda: {"aibrief"})
    spec = _spec(subagents=[_sub(tools=["mcp:aibrief"])])
    fake = _FakeTool("aibrief_search")

    payload = resolve_subagents(spec, mcp_tools_by_server={"aibrief": [fake]})[0]

    assert payload["tools"] == [fake]


def test_shell_does_not_leak_into_subagents(monkeypatch):
    """Phase 3 핵심 회귀.

    메인의 FilesystemMiddleware는 서브에이전트에 전파되지 않는다(실측).
    factory가 팀원마다 middleware를 붙이지 않으면 위임 한 번으로 셸이 열린다.
    """
    pytest.importorskip("deepagents")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    from runtime.factory import build_agent

    agent = build_agent(_spec(tools=["web_search"], subagents=[_sub()]))

    leaked = {
        name: tools
        for name, tools in _subagent_tool_names(agent).items()
        if "execute" in tools
    }
    assert not leaked, f"셸 실행이 서브에이전트로 샜다: {leaked}"


def test_solo_agent_exposes_only_general_purpose_with_leader_tools(monkeypatch):
    """Phase 2 미결 항목의 답 — subagents=[]일 때 `task`가 무엇을 띄우는가.

    deepagents는 subagents가 비어도 `task`와 general-purpose 서브에이전트를 남긴다.
    다만 그 general-purpose는 리더의 제한된 도구를 그대로 물려받으므로
    셸이 열리지 않는다. 즉 `task` 노출 자체는 화이트리스트 구멍이 아니다.
    """
    pytest.importorskip("deepagents")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    from runtime.factory import build_agent

    agent = build_agent(_spec(tools=["web_search"]))
    exposed = _subagent_tool_names(agent)

    assert set(exposed) == {"general-purpose"}
    assert "execute" not in exposed["general-purpose"]


def test_declared_subagent_is_reachable_by_name(monkeypatch):
    """리더가 task(subagent_type='researcher')로 위임할 수 있어야 한다."""
    pytest.importorskip("deepagents")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    from runtime.factory import build_agent

    agent = build_agent(_spec(subagents=[_sub()]))

    assert "researcher" in _subagent_tool_names(agent)
