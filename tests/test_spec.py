"""AgentSpec v0 가드레일 테스트 — Claude Code 자가 검증 루프의 기준점."""

import pytest
from pydantic import ValidationError

from runtime.spec import MAX_SUBAGENTS, SPEC_VERSION, AgentSpec


def _base(**over):
    d = dict(
        name="news_summarizer",
        description="IT 뉴스 수집·요약 에이전트",
        system_prompt="너는 IT 뉴스 요약 에이전트다.",
        tools=["web_search"],
    )
    d.update(over)
    return d


def _sub(**over):
    d = dict(
        name="researcher",
        description="조사 담당",
        system_prompt="너는 조사 담당이다.",
        tools=["web_search"],
    )
    d.update(over)
    return d


def test_valid_spec_passes():
    spec = AgentSpec(**_base())
    assert spec.spec_version == SPEC_VERSION
    assert spec.subagents == []


def test_unregistered_tool_rejected():
    with pytest.raises(ValidationError, match="unregistered tool"):
        AgentSpec(**_base(tools=["shell_exec"]))


def test_configured_mcp_server_allowed(monkeypatch):
    monkeypatch.setattr("runtime.spec.configured_server_names", lambda: {"aibrief"})
    spec = AgentSpec(**_base(tools=["mcp:aibrief"]))
    assert "mcp:aibrief" in spec.tools


def test_unconfigured_mcp_server_rejected():
    """Phase 2: mcp: 접두사만으로는 통과하지 못한다. 설정된 서버여야 한다."""
    with pytest.raises(ValidationError, match="unconfigured MCP server"):
        AgentSpec(**_base(tools=["mcp:ghost_server"]))


# --- Phase 3: subagents ---------------------------------------------------


def test_subagents_are_enabled():
    """Phase 3에서 게이트를 열었다. Phase 1~2에서는 이 스펙이 거부됐다."""
    spec = AgentSpec(**_base(subagents=[_sub()]))

    assert [s.name for s in spec.subagents] == ["researcher"]
    assert spec.subagents[0].tools == ["web_search"]


def test_subagent_tools_use_the_same_whitelist():
    """위임이 도구 화이트리스트 우회 경로가 되면 안 된다."""
    with pytest.raises(ValidationError, match="unregistered tool"):
        AgentSpec(**_base(subagents=[_sub(tools=["shell_exec"])]))


def test_subagent_mcp_server_must_be_configured():
    """팀원의 MCP 참조도 설정된 서버여야 한다."""
    with pytest.raises(ValidationError, match="unconfigured MCP server"):
        AgentSpec(**_base(subagents=[_sub(tools=["mcp:ghost_server"])]))


def test_duplicate_subagent_names_rejected():
    """리더는 이름으로 위임한다 — 이름이 겹치면 어느 쪽이 불릴지 알 수 없다."""
    with pytest.raises(ValidationError, match="duplicate subagent names"):
        AgentSpec(**_base(subagents=[_sub(), _sub()]))


def test_too_many_subagents_rejected():
    team = [_sub(name=f"member_{i}") for i in range(MAX_SUBAGENTS + 1)]
    with pytest.raises(ValidationError, match="too many subagents"):
        AgentSpec(**_base(subagents=team))


def test_subagents_cannot_nest():
    """깊이 1 고정 — SubAgentSpec에 subagents 필드가 없어 구조적으로 막힌다."""
    nested = _sub(subagents=[_sub(name="deeper")])

    spec = AgentSpec(**_base(subagents=[nested]))

    assert not hasattr(spec.subagents[0], "subagents")


def test_bad_name_rejected():
    with pytest.raises(ValidationError):
        AgentSpec(**_base(name="News Summarizer"))
