"""MCP HTTP transport 실연결 테스트 — `streamable_http`와 `sse`를 실제로 왕복시킨다.

`test_mcp.py`는 설정 파싱만, `test_mcp_integration.py`는 stdio만 본다.
그래서 커넥터가 지원한다고 **선언한** 세 transport 중 둘이 한 번도 실행되지
않은 상태였다 — HTTP 경로가 깨져 있어도 전 테스트가 초록이었다.

여기서는 같은 echo 서버를 HTTP로 띄워 커넥터 전 구간을 확인한다:
설정 로드 → HTTP 접속 → 도구 목록 조회 → 도구 호출 → **헤더 전달**.

헤더를 따로 확인하는 이유: 설정의 `${ENV_VAR}` 치환은 `load_config()`가 돌려주는
dict에 대해서만 단언돼 있었다. 치환된 헤더가 실제로 전송되지 않아도 그 단언은
통과한다. 인증이 필요한 MCP 서버는 전부 이 경로를 탄다.

외부 서비스·자격증명이 필요 없다. 느리므로 `-m "not integration"`으로 제외할 수 있다.
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from registry.mcp import load_tools_async

pytest.importorskip("mcp", reason="MCP 서버 SDK가 없으면 실연결 검증을 건너뛴다")

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# uvicorn 기동을 기다리는 상한. Windows에서 첫 기동이 느릴 수 있어 넉넉히 잡는다.
STARTUP_TIMEOUT_SEC = 30.0
POLL_INTERVAL_SEC = 0.1

# 설정 파일에 직접 쓰지 않고 환경변수로 넣는 값. 실제 자격증명이 아니다.
TOKEN_ENV_VAR = "DEEP_BUILDER_TEST_MCP_TOKEN"
TEST_TOKEN = "test-token-not-a-real-secret"
PROBE_HEADER_VALUE = "probe-value"

# (커넥터가 쓰는 transport 이름, 서버 CLI 인자, FastMCP 기본 마운트 경로)
HTTP_TRANSPORTS = [
    ("streamable_http", "streamable-http", "/mcp"),
    ("sse", "sse", "/sse"),
]


def _free_port() -> int:
    """비어 있는 TCP 포트를 하나 고른다.

    바인드를 풀고 서버가 잡기까지 짧은 경합 구간이 있다. 고정 포트를 쓰면
    개발자 머신에서 상시 충돌하므로 이쪽이 낫다고 판단했다.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_listening(proc: subprocess.Popen, port: int) -> None:
    """서버가 포트를 열 때까지 기다린다. 죽었으면 서버 출력을 그대로 보여준다."""
    deadline = time.monotonic() + STARTUP_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            output = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(
                f"echo server exited with code {proc.returncode} before listening:\n{output}"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(POLL_INTERVAL_SEC)

    proc.kill()
    raise TimeoutError(
        f"echo server did not listen on port {port} within {STARTUP_TIMEOUT_SEC}s"
    )


@pytest.fixture(
    params=HTTP_TRANSPORTS,
    ids=[transport for transport, _, _ in HTTP_TRANSPORTS],
)
def http_echo_url(request) -> tuple[str, str]:
    """echo 서버를 HTTP로 띄우고 (transport, url)을 준다. 끝나면 반드시 죽인다."""
    transport, cli_transport, mount_path = request.param
    port = _free_port()

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "examples.echo_mcp_server",
            "--transport",
            cli_transport,
            "--port",
            str(port),
        ],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        _wait_until_listening(proc, port)
        yield transport, f"http://127.0.0.1:{port}{mount_path}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


@pytest.fixture
def http_config(http_echo_url: tuple[str, str], tmp_path: Path, monkeypatch) -> Path:
    """HTTP echo 서버를 가리키는 설정을 만든다. 토큰은 `${ENV_VAR}` 참조로 적는다."""
    transport, url = http_echo_url
    monkeypatch.setenv(TOKEN_ENV_VAR, TEST_TOKEN)

    config = {
        "echo_http": {
            "transport": transport,
            "url": url,
            "headers": {
                "Authorization": f"Bearer ${{{TOKEN_ENV_VAR}}}",
                "X-Deep-Builder-Probe": PROBE_HEADER_VALUE,
            },
        }
    }
    path = tmp_path / "mcp_servers.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


@pytest.fixture
def http_tools(http_config: Path) -> dict[str, object]:
    """HTTP로 붙어 도구를 이름으로 색인한다."""
    tools = asyncio.run(load_tools_async(["mcp:echo_http"], path=http_config))
    return {tool.name: tool for tool in tools}


def test_http_connector_lists_tools_from_a_live_server(http_tools):
    """서버가 광고하는 도구가 HTTP 경계를 넘어 그대로 올라온다."""
    assert set(http_tools) == {"echo", "add_numbers", "http_request_headers"}


def test_http_connector_invokes_a_live_tool(http_tools):
    """도구 호출 결과가 실제로 HTTP 서버를 거쳐 돌아온다."""
    result = asyncio.run(http_tools["add_numbers"].ainvoke({"a": 19, "b": 23}))

    assert "42" in str(result)


def test_non_ascii_survives_the_http_round_trip(http_tools):
    """한글이 HTTP 경계를 넘어도 깨지지 않는다."""
    result = asyncio.run(http_tools["echo"].ainvoke({"text": "안녕 deep_builder"}))

    assert "안녕 deep_builder" in str(result)


def test_configured_headers_reach_the_server(http_tools):
    """설정에 적은 헤더가 서버까지 실제로 전달된다 — dict 단언으로는 알 수 없던 부분.

    `${ENV_VAR}` 치환 결과가 그대로 전송되는지까지 한 번에 확인한다.
    """
    result = str(asyncio.run(http_tools["http_request_headers"].ainvoke({})))

    assert f"Bearer {TEST_TOKEN}" in result
    assert PROBE_HEADER_VALUE in result


def test_secret_is_not_written_to_the_config_file(http_config: Path):
    """설정 파일에는 토큰이 아니라 환경변수 참조만 남는다 (커밋해도 새지 않는다)."""
    raw = http_config.read_text(encoding="utf-8")

    assert TEST_TOKEN not in raw
    assert TOKEN_ENV_VAR in raw
