"""MCP 실연결 통합 테스트 — 진짜 MCP 서버 프로세스를 띄워 커넥터 전 구간을 확인한다.

`test_mcp.py`는 설정 파싱만 본다(네트워크·프로세스 없음). 여기서는 그 반대로,
`examples/echo_mcp_server.py`를 stdio로 기동해서 커넥터가 실제 MCP 서버와
말이 통하는지 확인한다: 설정 로드 → 프로세스 기동 → 도구 목록 조회 → 도구 호출.

외부 서비스에 의존하지 않으므로 오프라인·무자격증명으로 돌아간다.
HTTP transport(streamable_http·sse)는 `test_mcp_http_integration.py`가 덮는다.
느리므로 `-m "not integration"`으로 제외할 수 있다.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from registry.mcp import load_tools_async
from runtime.spec import AgentSpec

pytest.importorskip("mcp", reason="MCP 서버 SDK가 없으면 실연결 검증을 건너뛴다")

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def echo_config(tmp_path: Path) -> Path:
    """echo 서버를 가리키는 mcp_servers.json 을 만든다.

    `command`는 반드시 `sys.executable`이어야 한다. `"python"`으로 적으면
    PATH의 다른 인터프리터가 잡혀 의존성이 없는 환경에서 서버가 죽는다.
    """
    config = {
        "echo": {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-m", "examples.echo_mcp_server"],
            "cwd": str(PROJECT_ROOT),
        }
    }
    path = tmp_path / "mcp_servers.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


@pytest.fixture
def echo_tools(echo_config: Path) -> dict[str, object]:
    """echo 서버를 기동해 도구를 이름으로 색인한다."""
    tools = asyncio.run(load_tools_async(["mcp:echo"], path=echo_config))
    return {t.name: t for t in tools}


def test_connector_lists_tools_from_a_live_server(echo_tools):
    """서버가 광고하는 도구가 그대로 올라온다."""
    assert set(echo_tools) == {"echo", "add_numbers", "http_request_headers"}


def test_stdio_has_no_http_request(echo_tools):
    """stdio에는 HTTP 요청이 없으므로 헤더도 없다.

    `http_request_headers`가 상수를 돌려주는 게 아니라 실제 요청을 읽는다는 근거다.
    HTTP 쪽 헤더 검증(test_mcp_http_integration.py)의 대조군 역할을 한다.
    """
    result = asyncio.run(echo_tools["http_request_headers"].ainvoke({}))

    assert "{}" in str(result)


def test_connector_invokes_a_live_tool(echo_tools):
    """도구 호출 결과가 실제로 서버를 거쳐 돌아온다."""
    result = asyncio.run(echo_tools["add_numbers"].ainvoke({"a": 19, "b": 23}))

    assert "42" in str(result)


def test_non_ascii_survives_the_mcp_round_trip(echo_tools):
    """한글이 stdio 경계를 넘어도 깨지지 않는다.

    Phase 1의 python_repl이 정확히 이 지점(자식 프로세스 인코딩)에서 깨졌다.
    """
    result = asyncio.run(echo_tools["echo"].ainvoke({"text": "안녕 deep_builder"}))

    assert "안녕 deep_builder" in str(result)


def test_spec_accepts_a_configured_server(echo_config: Path, monkeypatch):
    """설정에 존재하는 서버는 스펙 검증을 통과한다 (오타 거부는 test_mcp.py).

    `runtime.spec`가 부르는 이름을 갈아끼운다. `registry.mcp.DEFAULT_CONFIG_PATH`를
    patch해도 소용없다 — 기본 인자는 def 시점에 묶이고 spec은 인자 없이 호출한다.
    """
    import runtime.spec as spec_mod

    monkeypatch.setattr(
        spec_mod,
        "configured_server_names",
        lambda *a, **kw: set(json.loads(echo_config.read_text(encoding="utf-8"))),
    )

    spec = AgentSpec(
        name="mcp_probe",
        description="echo MCP 서버를 쓰는 프로브 에이전트",
        system_prompt="너는 프로브다. 모르는 것은 지어내지 않는다.",
        tools=["mcp:echo"],
    )

    assert spec.tools == ["mcp:echo"]


def test_live_mcp_tools_reach_the_built_agent(echo_tools, monkeypatch):
    """커넥터가 로드한 도구가 deepagents 에이전트에 실제로 노출된다.

    LLM을 호출하지 않는다 — 에이전트 생성까지만 하고 도구 목록을 확인한다.
    """
    pytest.importorskip("deepagents")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    from runtime.factory import build_agent

    spec = AgentSpec(
        name="mcp_probe",
        description="echo MCP 서버를 쓰는 프로브 에이전트",
        system_prompt="너는 프로브다. 모르는 것은 지어내지 않는다.",
        tools=[],
    )

    agent = build_agent(spec, extra_tools=list(echo_tools.values()))
    exposed = _exposed_tool_names(agent)

    assert {"echo", "add_numbers"} <= exposed
    # 스펙이 요청하지 않은 셸 실행 도구는 여전히 차단되어야 한다.
    assert "execute" not in exposed


def _exposed_tool_names(agent) -> set[str]:
    """컴파일된 그래프에서 도구 노드가 들고 있는 도구 이름을 뽑는다."""
    node = agent.nodes["tools"]
    bound = getattr(node, "bound", node)
    return set(getattr(bound, "tools_by_name", {}))
