"""MCP 커넥터 — 외부 MCP 서버의 도구를 AgentSpec에 노출한다.

스펙은 `"mcp:<server_name>"` 형태로 서버를 통째로 참조한다. 개별 도구 이름을
스펙에 박지 않는 이유는 서버가 제공하는 도구 목록이 서버 쪽 사정으로 바뀌기 때문이다.

접속 설정은 코드가 아니라 `mcp_servers.json`에 둔다. 비밀값은 파일에 직접 쓰지 않고
`${ENV_VAR}` 참조로 적으면 로드 시점에 환경변수로 치환된다 — 설정 파일을 커밋해도
토큰이 새지 않는다.

langchain-mcp-adapters 0.3.2 검증 (2026-08-08, 설치본 시그니처 대조):
- `MultiServerMCPClient(connections: dict[str, Connection])`
- `await client.get_tools(server_name=...) -> list[BaseTool]`
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

from registry.registry import MCP_PREFIX

# 프로젝트 루트의 기본 설정 경로. 없으면 MCP 서버가 하나도 없는 것으로 취급한다.
DEFAULT_CONFIG_PATH = Path("mcp_servers.json")

# 설정값 안의 "${VAR}" 자리를 환경변수로 치환한다.
_ENV_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# stdio는 command, HTTP 계열은 url이 필수다.
_REQUIRED_FIELDS: dict[str, str] = {
    "stdio": "command",
    "streamable_http": "url",
    "sse": "url",
}


class MCPConfigError(ValueError):
    """설정 파일이 없거나, 형식이 틀렸거나, 참조한 환경변수가 비어 있다."""


def server_key(name: str) -> str:
    """서버 이름을 스펙 도구 키로 바꾼다 (`aibrief` → `mcp:aibrief`)."""
    return f"{MCP_PREFIX}{name}"


def server_name(tool_key: str) -> str:
    """스펙 도구 키에서 서버 이름을 뽑는다 (`mcp:aibrief` → `aibrief`)."""
    if not tool_key.startswith(MCP_PREFIX):
        raise ValueError(f"not an MCP tool key: {tool_key!r}")
    return tool_key[len(MCP_PREFIX) :]


def _expand_env(value: Any, *, path: str) -> Any:
    """설정값 내부의 ${VAR} 참조를 환경변수로 치환한다 (재귀)."""
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            var = match.group(1)
            resolved = os.environ.get(var)
            if not resolved:
                raise MCPConfigError(
                    f"{path}: environment variable {var!r} is referenced but not set"
                )
            return resolved

        return _ENV_REF_RE.sub(replace, value)
    if isinstance(value, dict):
        return {k: _expand_env(v, path=f"{path}.{k}") for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v, path=f"{path}[{i}]") for i, v in enumerate(value)]
    return value


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, dict]:
    """MCP 서버 설정을 읽는다. 파일이 없으면 빈 설정을 반환한다.

    Raises:
        MCPConfigError: JSON 형식 오류, 필수 필드 누락, 환경변수 미설정.
    """
    if not path.exists():
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MCPConfigError(f"{path}: invalid JSON ({exc})") from exc

    if not isinstance(raw, dict):
        raise MCPConfigError(f"{path}: top level must be an object of server configs")

    config: dict[str, dict] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            raise MCPConfigError(f"{path}: server {name!r} config must be an object")

        transport = entry.get("transport")
        if transport not in _REQUIRED_FIELDS:
            raise MCPConfigError(
                f"{path}: server {name!r} has unsupported transport {transport!r} "
                f"(expected one of {sorted(_REQUIRED_FIELDS)})"
            )

        required = _REQUIRED_FIELDS[transport]
        if not entry.get(required):
            raise MCPConfigError(
                f"{path}: server {name!r} with transport {transport!r} requires {required!r}"
            )

        config[name] = _expand_env(entry, path=f"{path}:{name}")
    return config


def configured_server_names(path: Path = DEFAULT_CONFIG_PATH) -> set[str]:
    """설정된 MCP 서버 이름 집합. 스펙 검증이 사용한다.

    설정이 깨졌더라도 여기서는 예외를 올리지 않는다 — 스펙 검증 단계에서는
    "그런 서버 없음"으로 처리하고, 실제 원인은 도구 로드 시점에 그대로 드러난다.
    """
    try:
        return set(load_config(path))
    except MCPConfigError:
        return set()


async def load_tools_async(
    tool_keys: list[str], *, path: Path = DEFAULT_CONFIG_PATH
) -> list[Any]:
    """`mcp:` 도구 키 목록에 해당하는 서버들의 도구를 로드한다.

    Raises:
        MCPConfigError: 스펙이 참조한 서버가 설정에 없을 때.
    """
    names = [server_name(key) for key in tool_keys if key.startswith(MCP_PREFIX)]
    if not names:
        return []

    config = load_config(path)
    missing = [name for name in names if name not in config]
    if missing:
        raise MCPConfigError(
            f"MCP servers referenced by the spec but not configured in {path}: {missing}"
        )

    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient({name: config[name] for name in names})

    tools: list[Any] = []
    for name in names:
        tools.extend(await client.get_tools(server_name=name))
    return tools


def load_tools(tool_keys: list[str], *, path: Path = DEFAULT_CONFIG_PATH) -> list[Any]:
    """`load_tools_async`의 동기 래퍼. CLI처럼 이벤트 루프 밖에서 쓴다."""
    return asyncio.run(load_tools_async(tool_keys, path=path))
