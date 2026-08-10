"""deep_builder_agent CLI — 자연어 요구를 에이전트로 만들고 곧바로 대화한다.

사용법:
    python cli.py "IT 뉴스 요약 에이전트 만들어줘"   # Builder로 생성 후 대화
    python cli.py --spec specs/news_summarizer.json  # 저장된 스펙으로 바로 대화
    python cli.py --spec specs/x.json --no-chat      # 생성/검증만 하고 종료
    python cli.py --spec specs/x.json --revise "파일 저장 기능도 넣어줘"

대화 중에도 `/revise <바꾸고 싶은 내용>`으로 명세를 고칠 수 있다.
고치면 변경 내역을 보여주고 에이전트를 다시 만든다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from runtime.config import load_env
from runtime.console import force_utf8_stdio

from builder.builder import (
    SpecGenerationError,
    generate_spec,
    revise_spec,
    save_spec,
)
from registry import MCP_PREFIX
from registry.mcp import MCPConfigError
from registry.mcp import load_tools_by_server as load_mcp_tools_by_server
from runtime.factory import build_agent, resolve_builtin_fs_tools
from runtime.messages import last_text
from runtime.spec import AgentSpec, load_spec_file
from runtime.spec_diff import diff_specs, format_diff
from runtime.tracing import TracingConfigError, configure_tracing

EXIT_COMMANDS = frozenset({"exit", "quit", ":q"})

# 대화 중 명세를 고치는 명령. 뒤에 자연어 요구가 온다.
REVISE_COMMAND = "/revise"


def load_spec(path: Path) -> AgentSpec:
    """JSON 파일을 읽어 검증된 AgentSpec으로 변환한다 (가드레일 보장 포함)."""
    return load_spec_file(path)


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


def build_runtime(spec: AgentSpec):
    """스펙으로 실행 가능한 에이전트를 만든다 (MCP 도구 해석 포함).

    수정 루프가 같은 절차로 **다시** 만들 수 있어야 해서 함수로 분리했다.

    Raises:
        MCPConfigError: MCP 설정이 잘못됐거나 참조한 서버가 없을 때.
        LookupError: 도구를 해석할 수 없을 때.
    """
    # 리더와 팀원이 서로 다른 서버를 참조할 수 있으므로 서버별로 받아 둔다.
    mcp_by_server = load_mcp_tools_by_server(all_tool_keys(spec))
    for server, tools in mcp_by_server.items():
        print(f"[mcp] {server}: 도구 {len(tools)}개 로드 {[t.name for t in tools]}")

    leader_mcp_tools = [
        tool
        for key in spec.tools
        if key.startswith(MCP_PREFIX)
        for tool in mcp_by_server.get(key[len(MCP_PREFIX) :], [])
    ]
    return build_agent(
        spec, extra_tools=leader_mcp_tools, mcp_tools_by_server=mcp_by_server
    )


def apply_revision(spec: AgentSpec, request: str) -> AgentSpec | None:
    """수정 요구를 반영한 새 스펙을 만들고 **무엇이 바뀌었는지 보여준다**.

    실패하면 None을 돌려주고 호출자는 기존 스펙을 그대로 쓴다 —
    수정에 실패했다고 대화가 끊기면 안 된다.
    """
    print("\n[builder] 명세를 수정하는 중...")
    try:
        revised = revise_spec(spec, request)
    except SpecGenerationError as exc:
        print(f"[error] 수정 실패: {exc}")
        print(f"        마지막 원인: {exc.__cause__}\n")
        return None

    diff = diff_specs(spec, revised)
    print("\n[변경 내역]")
    print(format_diff(diff))

    if diff.is_empty:
        # 바뀐 게 없으면 저장도 재구축도 하지 않는다.
        print()
        return None

    saved = save_spec(revised)
    print(f"\n[spec] {saved} 에 저장했습니다")
    print(describe(revised))
    return revised


def chat(agent, spec: AgentSpec) -> None:
    """생성된 에이전트와 멀티턴 대화를 진행한다.

    `/revise <요구>`로 대화 중에 명세를 고칠 수 있다. 고치면 에이전트를 다시
    만들고 **대화 이력은 초기화한다** — 도구가 바뀐 에이전트에게 이전 도구
    호출 기록을 넘기면 맞지 않는다.
    """
    print("\n대화를 시작합니다. 종료하려면 exit / quit / :q 를 입력하세요.")
    print("명세를 고치려면: /revise <바꾸고 싶은 내용>\n")
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

        if user_input.startswith(REVISE_COMMAND):
            request = user_input[len(REVISE_COMMAND) :].strip()
            if not request:
                print("사용법: /revise <바꾸고 싶은 내용>\n")
                continue

            revised = apply_revision(spec, request)
            if revised is None:
                continue
            try:
                agent = build_runtime(revised)
            except (MCPConfigError, LookupError) as exc:
                # 새 스펙으로 못 만들면 **기존 에이전트를 그대로 유지**한다.
                print(f"[error] 수정된 명세로 에이전트를 만들지 못했습니다: {exc}")
                print("        기존 에이전트로 계속합니다.\n")
                continue
            spec = revised
            history = []
            print("\n[runtime] 수정된 명세로 다시 만들었습니다. 대화 이력은 초기화됩니다.\n")
            continue

        history = [*history, {"role": "user", "content": user_input}]
        try:
            result = agent.invoke({"messages": history})
        except Exception as exc:  # noqa: BLE001 - CLI는 어떤 실패도 사용자에게 보여준다
            print(f"[error] 에이전트 실행 실패: {type(exc).__name__}: {exc}\n")
            continue

        history = result["messages"]
        print(f"\nagent> {last_text(history)}\n")


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    load_env()

    parser = argparse.ArgumentParser(prog="deep_builder_agent", description=__doc__)
    parser.add_argument("request", nargs="?", help="에이전트를 설명하는 자연어 요구")
    parser.add_argument("--spec", type=Path, help="기존 AgentSpec JSON 경로")
    parser.add_argument(
        "--no-chat", action="store_true", help="생성/검증만 하고 대화는 건너뛴다"
    )
    parser.add_argument(
        "--revise",
        metavar="요구",
        help="기존 명세를 자연어로 고친다 (--spec과 함께 쓴다)",
    )
    args = parser.parse_args(argv)

    if bool(args.request) == bool(args.spec):
        parser.error("자연어 요구 또는 --spec 중 정확히 하나를 지정하세요.")
    if args.revise and not args.spec:
        parser.error("--revise 는 --spec 과 함께 써야 합니다 (고칠 대상이 필요합니다).")

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

    if args.revise:
        revised = apply_revision(spec, args.revise)
        if revised is None:
            return 1
        spec = revised

    if args.no_chat:
        return 0

    try:
        status = configure_tracing()
    except TracingConfigError as exc:
        print(f"[error] 트레이싱 설정 오류: {exc}", file=sys.stderr)
        return 1
    print(f"[trace] LangSmith {status}")

    print("\n[runtime] 에이전트를 생성하는 중...")
    try:
        agent = build_runtime(spec)
    except MCPConfigError as exc:
        print(f"[error] MCP 도구 로드 실패: {exc}", file=sys.stderr)
        return 1
    except LookupError as exc:
        print(f"[error] 도구 해석 실패: {exc}", file=sys.stderr)
        return 1

    chat(agent, spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
