"""MCP 커넥터 검증용 최소 stdio 서버.

registry/mcp.py가 실제 MCP 서버와 말이 통하는지 확인하기 위한 것이다.
외부 서비스(aibrief 등)에 의존하지 않고 커넥터 경로 전체
(설정 로드 → 프로세스 기동 → 도구 목록 조회 → 도구 호출)를 검증한다.

실행:
    python -m examples.echo_mcp_server

mcp_servers.json 설정 예:
    {"echo": {"transport": "stdio", "command": ".venv/Scripts/python.exe",
              "args": ["-m", "examples.echo_mcp_server"], "cwd": "."}}

`command`를 그냥 "python"으로 적으면 PATH의 전역 인터프리터가 잡혀
mcp 패키지를 못 찾고 서버가 즉시 죽는다. venv 인터프리터를 명시한다.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

server = FastMCP("deep-builder-echo")


@server.tool()
def echo(text: str) -> str:
    """입력받은 문자열을 그대로 되돌려준다.

    Args:
        text: 되돌려줄 문자열.
    """
    return f"echo: {text}"


@server.tool()
def add_numbers(a: int, b: int) -> int:
    """두 정수를 더한다.

    Args:
        a: 첫 번째 정수.
        b: 두 번째 정수.
    """
    return a + b


if __name__ == "__main__":
    server.run(transport="stdio")
