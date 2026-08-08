"""AgentSpec v0 가드레일 테스트 — Claude Code 자가 검증 루프의 기준점."""

import pytest
from pydantic import ValidationError

from runtime.spec import AgentSpec


def _base(**over):
    d = dict(
        name="news_summarizer",
        description="IT 뉴스 수집·요약 에이전트",
        system_prompt="너는 IT 뉴스 요약 에이전트다.",
        tools=["web_search"],
    )
    d.update(over)
    return d


def test_valid_spec_passes():
    spec = AgentSpec(**_base())
    assert spec.spec_version == "0.1"
    assert spec.subagents == []


def test_unregistered_tool_rejected():
    with pytest.raises(ValidationError, match="unregistered tool"):
        AgentSpec(**_base(tools=["shell_exec"]))


def test_mcp_prefixed_tool_allowed_at_schema_level():
    spec = AgentSpec(**_base(tools=["mcp:aibrief"]))
    assert "mcp:aibrief" in spec.tools


def test_subagents_disabled_until_phase3():
    sub = dict(name="researcher", description="조사 담당", prompt="조사하라", tools=[])
    with pytest.raises(ValidationError, match="disabled until Phase 3"):
        AgentSpec(**_base(subagents=[sub]))


def test_bad_name_rejected():
    with pytest.raises(ValidationError):
        AgentSpec(**_base(name="News Summarizer"))
