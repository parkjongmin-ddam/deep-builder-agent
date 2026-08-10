"""UI 로직 — Streamlit 위젯과 분리된 순수 함수들 (Phase 4).

`ui/app.py`는 그리기만 하고 판단은 여기서 한다. Streamlit 앱은 자동 테스트가
어렵지만 이 모듈은 평범한 함수라 그대로 테스트할 수 있다.
"""

from __future__ import annotations

from runtime.messages import last_text, message_text

# 환경 점검은 UI만의 관심사가 아니다 — CLI도 같은 판정을 써야 한다.
# `cli`가 `ui`를 임포트하는 것은 레이어가 거꾸로라 runtime/으로 내렸고,
# 여기서는 재수출만 한다 (기존 `from ui.state import check_readiness`가 그대로 동작).
from runtime.readiness import (  # noqa: F401
    ReadinessItem,
    blocking_problems,
    check_readiness,
)
from runtime.spec import AgentSpec


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
