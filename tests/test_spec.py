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


# --- 팀원 모델 (v0.3) ------------------------------------------------------


def test_subagent_model_defaults_to_inherit():
    """모델을 안 적으면 None — 리더 상속이 기본이다.

    **기존 스펙 파일이 그대로 돌아야 한다.** v0.2로 쓰인 템플릿·평가 케이스에는
    이 필드가 없다.
    """
    spec = AgentSpec(**_base(subagents=[_sub()]))

    assert spec.subagents[0].model is None


def test_subagent_model_can_be_overridden():
    spec = AgentSpec(**_base(subagents=[_sub(model="claude-haiku-4-5")]))

    assert spec.subagents[0].model == "claude-haiku-4-5"


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_blank_subagent_model_becomes_inherit(blank):
    """공백뿐인 모델 ID는 상속으로 정규화한다.

    그대로 넘기면 deepagents가 빈 모델 ID를 해석하려다 런타임에 죽는다.
    `.env`의 빈 값이 기본값을 덮어썼던 것과 같은 함정이다.
    """
    spec = AgentSpec(**_base(subagents=[_sub(model=blank)]))

    assert spec.subagents[0].model is None


def test_leader_model_is_untouched_by_subagent_models():
    """팀원 모델을 지정해도 리더 모델은 그대로다 (대조군)."""
    spec = AgentSpec(
        **_base(model="claude-sonnet-4-6", subagents=[_sub(model="claude-haiku-4-5")])
    )

    assert spec.model == "claude-sonnet-4-6"


def test_unregistered_tool_rejected():
    with pytest.raises(ValidationError, match="unregistered tool"):
        AgentSpec(**_base(tools=["shell_exec"]))


def test_configured_mcp_server_allowed(monkeypatch):
    monkeypatch.setattr("runtime.spec.configured_server_names", lambda: {"remote_http"})
    spec = AgentSpec(**_base(tools=["mcp:remote_http"]))
    assert "mcp:remote_http" in spec.tools


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
