"""MCP 커넥터 테스트 — 설정 파싱과 스펙 검증 연동을 네트워크 없이 확인한다.

실제 MCP 서버 접속은 여기서 하지 않는다. 검증 대상은 "설정이 틀렸을 때
조용히 넘어가지 않는가"와 "비밀값이 설정 파일에 박히지 않는가"이다.
"""

import json

import pytest

from registry.mcp import (
    MCPConfigError,
    configured_server_names,
    load_config,
    server_key,
    server_name,
)
from runtime.spec import AgentSpec

HTTP_SERVER = {
    "transport": "streamable_http",
    "url": "https://example.invalid/mcp",
    "headers": {"Authorization": "Bearer ${TEST_MCP_TOKEN}"},
}
STDIO_SERVER = {"transport": "stdio", "command": "python", "args": ["-m", "srv"]}


def _write(tmp_path, payload):
    path = tmp_path / "mcp_servers.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --- 키 변환 --------------------------------------------------------------


def test_server_key_roundtrip():
    assert server_key("aibrief") == "mcp:aibrief"
    assert server_name("mcp:aibrief") == "aibrief"


def test_server_name_rejects_non_mcp_key():
    with pytest.raises(ValueError, match="not an MCP tool key"):
        server_name("web_search")


# --- 설정 로딩 ------------------------------------------------------------


def test_missing_config_is_empty_not_error(tmp_path):
    assert load_config(tmp_path / "absent.json") == {}


def test_env_reference_is_expanded(tmp_path, monkeypatch):
    """토큰은 설정 파일이 아니라 환경변수에 둔다."""
    monkeypatch.setenv("TEST_MCP_TOKEN", "synthetic-token")
    config = load_config(_write(tmp_path, {"aibrief": HTTP_SERVER}))
    assert config["aibrief"]["headers"]["Authorization"] == "Bearer synthetic-token"


def test_missing_env_reference_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_MCP_TOKEN", raising=False)
    with pytest.raises(MCPConfigError, match="TEST_MCP_TOKEN"):
        load_config(_write(tmp_path, {"aibrief": HTTP_SERVER}))


def test_stdio_server_loads(tmp_path):
    config = load_config(_write(tmp_path, {"local": STDIO_SERVER}))
    assert config["local"]["command"] == "python"


def test_unsupported_transport_raises(tmp_path):
    bad = {"srv": {"transport": "carrier_pigeon", "url": "https://example.invalid"}}
    with pytest.raises(MCPConfigError, match="unsupported transport"):
        load_config(_write(tmp_path, bad))


def test_missing_required_field_raises(tmp_path):
    with pytest.raises(MCPConfigError, match="requires 'url'"):
        load_config(_write(tmp_path, {"srv": {"transport": "streamable_http"}}))


def test_invalid_json_raises(tmp_path):
    path = tmp_path / "mcp_servers.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(MCPConfigError, match="invalid JSON"):
        load_config(path)


def test_broken_config_yields_no_server_names(tmp_path):
    """검증 단계는 예외 대신 '서버 없음'으로 처리한다."""
    path = tmp_path / "mcp_servers.json"
    path.write_text("{not json", encoding="utf-8")
    assert configured_server_names(path) == set()


# --- 스펙 검증 연동 -------------------------------------------------------


def test_unconfigured_mcp_server_is_rejected():
    """설정에 없는 MCP 서버는 스펙 단계에서 막힌다 (Phase 1에서는 통과했다)."""
    with pytest.raises(ValueError, match="unconfigured MCP server"):
        AgentSpec(
            name="mcp_agent",
            description="MCP 도구를 쓰는 에이전트",
            system_prompt="p",
            tools=["mcp:nonexistent_server"],
        )
