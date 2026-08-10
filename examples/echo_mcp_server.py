"""MCP 커넥터 검증용 최소 서버 (stdio / streamable-http / sse).

registry/mcp.py가 실제 MCP 서버와 말이 통하는지 확인하기 위한 것이다.
외부 서비스에 의존하지 않고 커넥터 경로 전체
(설정 로드 → 서버 기동 → 도구 목록 조회 → 도구 호출)를 검증한다.

**transport를 인자로 받는 이유**: 커넥터는 `stdio`·`streamable_http`·`sse`를
모두 지원한다고 선언하는데, 예전에는 `stdio`만 실연결로 검증됐다. HTTP 경로가
깨져 있어도 테스트가 알려주지 않는 상태였다. 같은 서버를 세 transport로 띄워
양쪽을 다 덮는다.

**로컬 검증 전용이다.** `http_request_headers`가 요청 헤더를 그대로 되돌려주므로
루프백 밖으로 노출하면 안 된다. 기본 바인드 주소가 127.0.0.1인 이유다.

실행:
    python -m examples.echo_mcp_server                              # stdio (기본)
    python -m examples.echo_mcp_server --transport streamable-http --port 8931
    python -m examples.echo_mcp_server --transport sse --port 8932

mcp_servers.json 설정 예:
    {"echo": {"transport": "stdio", "command": ".venv/Scripts/python.exe",
              "args": ["-m", "examples.echo_mcp_server"], "cwd": "."}}
    {"echo_http": {"transport": "streamable_http", "url": "http://127.0.0.1:8931/mcp"}}

`command`를 그냥 "python"으로 적으면 PATH의 전역 인터프리터가 잡혀
mcp 패키지를 못 찾고 서버가 즉시 죽는다. venv 인터프리터를 명시한다.
"""

from __future__ import annotations

import argparse

from mcp.server.fastmcp import Context, FastMCP

# HTTP 요청에서 되돌려줄 헤더. 전부 흘리지 않고 검증에 필요한 것만 고른다.
REPORTED_HEADERS = ("authorization", "x-deep-builder-probe")

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


@server.tool()
def http_request_headers(ctx: Context) -> dict[str, str]:
    """이번 요청에서 관측된 헤더를 되돌려준다 (검증용).

    커넥터 설정의 `headers`가 실제로 서버까지 도달하는지 확인하는 용도다.
    설정 파일에 적은 `${ENV_VAR}` 치환 결과가 dict 안에만 들어있고 실제로는
    전송되지 않아도, 헤더를 보지 않으면 알 수 없다.

    stdio로 띄우면 HTTP 요청 자체가 없으므로 빈 dict를 돌려준다.
    """
    request = getattr(ctx.request_context, "request", None)
    headers = getattr(request, "headers", None)
    if headers is None:
        return {}
    return {name: headers[name] for name in REPORTED_HEADERS if name in headers}


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP 커넥터 검증용 echo 서버")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http", "sse"),
        default="stdio",
        help="전송 방식 (기본: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP 바인드 주소")
    parser.add_argument("--port", type=int, default=8931, help="HTTP 포트")
    args = parser.parse_args()

    if args.transport != "stdio":
        # 루프백에만 바인드한다. 헤더를 되비추는 서버를 외부에 열 이유가 없다.
        server.settings.host = args.host
        server.settings.port = args.port

    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
