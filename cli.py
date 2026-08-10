"""deep_builder_agent CLI — 자연어 요구를 에이전트로 만들고 곧바로 대화한다.

사용법:
    python cli.py "IT 뉴스 요약 에이전트 만들어줘"   # Builder로 생성 후 대화
    python cli.py --spec specs/news_summarizer.json  # 저장된 스펙으로 바로 대화
    python cli.py --spec specs/x.json --no-chat      # 생성/검증만 하고 종료
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from builder.builder import SpecGenerationError, generate_spec, save_spec
from registry import MCP_PREFIX
from registry.mcp import MCPConfigError
from registry.mcp import load_tools_by_server as load_mcp_tools_by_server
from runtime.factory import build_agent, resolve_builtin_fs_tools
from runtime.spec import AgentSpec

EXIT_COMMANDS = frozenset({"exit", "quit", ":q"})


def _force_utf8_stdio() -> None:
    """표준 입출력을 UTF-8로 고정한다.

    Windows 기본 콘솔 코덱(cp949)에서는 출력 시 이모지가 UnicodeEncodeError를 내고,
    파이프 입력 시 한글이 서로게이트로 디코딩되어 이후 인코딩이 실패한다.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def load_spec(path: Path) -> AgentSpec:
    """JSON 파일을 읽어 검증된 AgentSpec으로 변환한다."""
    return AgentSpec(**json.loads(path.read_text(encoding="utf-8")))


def all_tool_keys(spec: AgentSpec) -> list[str]:
    """리더와 모든 팀원이 참조하는 도구 키를 한데 모은다 (중복 제거)."""
    keys = list(spec.tools)
    for sub in spec.subagents:
        keys.extend(sub.tools)
    return sorted(set(keys))


def describe(spec: AgentSpec) -> str:
    """생성 결과를 사람이 확인할 수 있게 요약한다."""
    fs_tools = ", ".join(resolve_builtin_fs_tools(spec))
    mcp_servers = [t for t in all_tool_keys(spec) if t.startswith(MCP_PREFIX)]
    team = "\n".join(
        f"                - {sub.name}: {sub.tools or '(no tools)'}"
        for sub in spec.subagents
    ) or "                (none — 단일 에이전트)"
    return (
        f"  name        : {spec.name}\n"
        f"  description : {spec.description}\n"
        f"  model       : {spec.model}\n"
        f"  spec tools  : {spec.tools or '(none)'}\n"
        f"  mcp servers : {mcp_servers or '(none)'}\n"
        f"  builtin fs  : {fs_tools}  (+ task; deepagents가 항상 주입)\n"
        f"  subagents   :\n{team}"
    )


def last_text(messages: list) -> str:
    """에이전트 응답 메시지 목록에서 마지막 텍스트 응답을 뽑는다."""
    for message in reversed(messages):
        if getattr(message, "type", None) != "ai":
            continue
        content = message.content
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            text = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
            if text.strip():
                return text
    return "(에이전트가 텍스트 응답을 내지 않았습니다)"


def chat(agent) -> None:
    """생성된 에이전트와 멀티턴 대화를 진행한다."""
    print("\n대화를 시작합니다. 종료하려면 exit / quit / :q 를 입력하세요.\n")
    history: list = []
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not user_input:
            continue
        if user_input.lower() in EXIT_COMMANDS:
            return

        history = [*history, {"role": "user", "content": user_input}]
        try:
            result = agent.invoke({"messages": history})
        except Exception as exc:  # noqa: BLE001 - CLI는 어떤 실패도 사용자에게 보여준다
            print(f"[error] 에이전트 실행 실패: {type(exc).__name__}: {exc}\n")
            continue

        history = result["messages"]
        print(f"\nagent> {last_text(history)}\n")


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    load_dotenv()

    parser = argparse.ArgumentParser(prog="deep_builder_agent", description=__doc__)
    parser.add_argument("request", nargs="?", help="에이전트를 설명하는 자연어 요구")
    parser.add_argument("--spec", type=Path, help="기존 AgentSpec JSON 경로")
    parser.add_argument(
        "--no-chat", action="store_true", help="생성/검증만 하고 대화는 건너뛴다"
    )
    args = parser.parse_args(argv)

    if bool(args.request) == bool(args.spec):
        parser.error("자연어 요구 또는 --spec 중 정확히 하나를 지정하세요.")

    if args.spec:
        spec = load_spec(args.spec)
        print(f"[spec] {args.spec} 로드 완료")
    else:
        print("[builder] 명세를 생성하는 중...")
        try:
            spec = generate_spec(args.request)
        except SpecGenerationError as exc:
            print(f"[error] 명세 생성 실패: {exc}", file=sys.stderr)
            print(f"        마지막 원인: {exc.__cause__}", file=sys.stderr)
            return 1
        saved = save_spec(spec)
        print(f"[spec] {saved} 에 저장했습니다")

    print(describe(spec))

    if args.no_chat:
        return 0

    print("\n[runtime] 에이전트를 생성하는 중...")
    try:
        # 리더와 팀원이 서로 다른 서버를 참조할 수 있으므로 서버별로 받아 둔다.
        mcp_by_server = load_mcp_tools_by_server(all_tool_keys(spec))
    except MCPConfigError as exc:
        print(f"[error] MCP 도구 로드 실패: {exc}", file=sys.stderr)
        return 1

    for server, tools in mcp_by_server.items():
        print(f"[mcp] {server}: 도구 {len(tools)}개 로드 {[t.name for t in tools]}")

    leader_mcp_tools = [
        tool
        for key in spec.tools
        if key.startswith(MCP_PREFIX)
        for tool in mcp_by_server.get(key[len(MCP_PREFIX) :], [])
    ]

    try:
        agent = build_agent(
            spec, extra_tools=leader_mcp_tools, mcp_tools_by_server=mcp_by_server
        )
    except LookupError as exc:
        print(f"[error] 도구 해석 실패: {exc}", file=sys.stderr)
        return 1

    chat(agent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
