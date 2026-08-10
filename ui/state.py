"""UI 로직 — Streamlit 위젯과 분리된 순수 함수들 (Phase 4).

`ui/app.py`는 그리기만 하고 판단은 여기서 한다. Streamlit 앱은 자동 테스트가
어렵지만 이 모듈은 평범한 함수라 그대로 테스트할 수 있다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from registry.mcp import configured_server_names
from runtime.messages import last_text, message_text
from runtime.spec import AgentSpec
from runtime.tracing import tracing_status


@dataclass(frozen=True)
class ReadinessItem:
    """환경 점검 항목 하나."""

    label: str
    ok: bool
    detail: str
    required: bool = False


def check_readiness(env: Mapping[str, str] | None = None) -> list[ReadinessItem]:
    """실행 전에 무엇이 준비됐는지 점검한다.

    비밀값은 **존재 여부만** 본다. 값을 읽어 화면에 흘리지 않는다.
    """
    env = os.environ if env is None else env

    trace = tracing_status(env)
    servers = sorted(configured_server_names())

    return [
        ReadinessItem(
            label="ANTHROPIC_API_KEY",
            ok=bool(env.get("ANTHROPIC_API_KEY")),
            detail="Builder와 생성된 에이전트 실행에 필요",
            required=True,
        ),
        ReadinessItem(
            label="TAVILY_API_KEY",
            ok=bool(env.get("TAVILY_API_KEY")),
            detail="web_search 도구용. 없으면 도구가 명확한 에러를 반환한다",
        ),
        ReadinessItem(
            label="LangSmith 트레이싱",
            ok=trace.enabled,
            detail=str(trace),
        ),
        ReadinessItem(
            label="MCP 서버",
            ok=bool(servers),
            detail=", ".join(servers) if servers else "mcp_servers.json 없음",
        ),
    ]


def blocking_problems(items: list[ReadinessItem]) -> list[str]:
    """실행을 막는 항목만 추린다. 선택 항목은 경고일 뿐 차단하지 않는다."""
    return [item.label for item in items if item.required and not item.ok]


def spec_overview(spec: AgentSpec) -> dict[str, str]:
    """스펙을 표로 보여주기 위한 납작한 요약."""
    return {
        "name": spec.name,
        "model": spec.model,
        "tools": ", ".join(spec.tools) or "(none)",
        "subagents": ", ".join(s.name for s in spec.subagents) or "(none)",
        "spec_version": spec.spec_version,
    }


def team_rows(spec: AgentSpec) -> list[dict[str, str]]:
    """팀 구성을 표 형태로. 팀이 없으면 빈 목록."""
    return [
        {
            "name": sub.name,
            "tools": ", ".join(sub.tools) or "(none)",
            "description": sub.description,
        }
        for sub in spec.subagents
    ]


def append_turn(history: list, user_input: str) -> list:
    """사용자 발화를 대화 이력에 덧붙인 **새 목록**을 만든다.

    원본을 변경하지 않는다 — Streamlit은 재실행될 때마다 상태를 다시 읽으므로
    제자리 변경은 추적하기 어려운 버그가 된다.
    """
    return [*history, {"role": "user", "content": user_input}]


def agent_reply(agent, history: list) -> tuple[list, str]:
    """에이전트를 한 턴 호출하고 (새 이력, 표시할 텍스트)를 돌려준다.

    실패를 예외로 올리지 않는다 — UI는 오류도 대화에 표시해야 한다.
    """
    try:
        result = agent.invoke({"messages": history})
    except Exception as exc:  # noqa: BLE001 - UI는 어떤 실패도 사용자에게 보여준다
        return history, f"[error] 에이전트 실행 실패: {type(exc).__name__}: {exc}"

    messages = result["messages"]
    return messages, last_text(messages)


def render_history(history: list) -> list[tuple[str, str]]:
    """대화 이력을 (역할, 텍스트) 목록으로 납작하게 만든다.

    dict(사용자 입력)과 LangChain 메시지 객체가 섞여 있으므로 둘 다 처리한다.
    텍스트 없이 도구만 호출한 턴은 건너뛴다 — 화면에는 사람과 에이전트의 말만 남긴다.
    """
    rows: list[tuple[str, str]] = []
    for message in history:
        if isinstance(message, dict):
            rows.append((message.get("role", "user"), message.get("content", "")))
            continue

        kind = getattr(message, "type", None)
        if kind not in {"human", "ai"}:
            continue

        text = message_text(message)
        if not text.strip():
            continue  # 텍스트 없이 도구만 호출한 턴
        rows.append(("user" if kind == "human" else "assistant", text))
    return rows
