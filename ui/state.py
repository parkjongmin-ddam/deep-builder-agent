"""UI 로직 — Streamlit 위젯과 분리된 순수 함수들 (Phase 4).

`ui/app.py`는 그리기만 하고 판단은 여기서 한다. Streamlit 앱은 자동 테스트가
어렵지만 이 모듈은 평범한 함수라 그대로 테스트할 수 있다.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

from runtime.messages import last_text, message_text

# 환경 점검은 UI만의 관심사가 아니다 — CLI도 같은 판정을 써야 한다.
# `cli`가 `ui`를 임포트하는 것은 레이어가 거꾸로라 runtime/으로 내렸고,
# 여기서는 재수출만 한다 (기존 `from ui.state import check_readiness`가 그대로 동작).
from runtime.readiness import (  # noqa: F401
    ReadinessItem,
    blocking_problems,
    check_readiness,
)

# IAM도 같은 이유로 runtime/에 산다 — CLI와 UI가 같은 판정을 써야 한다.
from runtime.iam import (  # noqa: F401
    ACTION_CREATE,
    ACTION_REVISE,
    ACTION_RUN,
    ACTION_VIEW,
    DEFAULT_PRINCIPAL,
    IamConfig,
    PermissionDeniedError,
    Principal,
    authorize_action,
    is_allowed,
    load_iam_config,
)
from runtime.spec import AgentSpec


def oidc_configured(secrets) -> bool:
    """OIDC 모드 여부 — `[auth]` 설정에 client_id가 있어야 한다 (Phase 7).

    secrets.toml이 아예 없으면 Streamlit이 접근 시점에 FileNotFoundError를
    던진다 — 그것은 '미설정(데모 모드)'이지 오류가 아니다. 그 외 예외는
    숨기지 않는다.
    """
    try:
        auth = secrets.get("auth")
    except FileNotFoundError:
        return False
    return bool(auth) and bool(auth.get("client_id"))


def user_identity(claims: dict) -> tuple[str, list[str]]:
    """ID 토큰 클레임에서 (이메일, 그룹 목록)을 뽑는다.

    그룹 클레임은 IdP 설정에 따라 없을 수도, 문자열 하나일 수도 있다 —
    없으면 빈 목록으로 정규화한다 (매핑 실패는 resolve_identity가 거부한다).
    """
    email = claims.get("email") or ""
    groups = claims.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]
    return email, list(groups)


def readiness_icon(item: ReadinessItem) -> str:
    """환경 점검 항목의 Material 아이콘 마크다운 (Phase 8 — 이모지 대체).

    시안 5a의 환경 점검 3단계를 따른다: 정상(check_circle·녹) /
    경고(error·주황) / 필수 누락(cancel·적).
    """
    if item.ok:
        return ":green[:material/check_circle:]"
    if item.required:
        return ":red[:material/cancel:]"
    return ":orange[:material/error:]"


def eval_case_icon(passed: bool) -> str:
    """평가 케이스 expander의 icon 파라미터 값 (Phase 8 — 이모지 대체).

    `st.expander(icon=...)`은 색 지시자를 받지 않으므로 아이콘 이름만 준다.
    """
    return ":material/check_circle:" if passed else ":material/cancel:"


def badges_html(keys: Sequence[str], accent: bool = False) -> str:
    """도구 키 목록을 배지 span HTML로 (Phase 8 단계 2, 시안 1a).

    클래스는 ui/style.py가 주입하는 `.dba-badge`다. 입력이 레지스트리 키라
    통제되어 있어도 이스케이프한다 — 시스템 경계에서는 신뢰하지 않는다.
    """
    cls = "dba-badge dba-badge--accent" if accent else "dba-badge"
    return "".join(
        f'<span class="{cls}">{html.escape(key)}</span>' for key in keys
    )


def chips_html(items: Sequence[str], dashed: bool = False) -> str:
    """행위·도구 경계 칩 HTML (Phase 8 단계 2, 시안 1a).

    dashed=True는 도구 경계용 점선 테두리 변형(`.dba-chip--dashed`)이다.
    """
    cls = "dba-chip dba-chip--dashed" if dashed else "dba-chip"
    return "".join(
        f'<span class="{cls}">{html.escape(item)}</span>' for item in items
    )


def readiness_summary(items: Sequence[ReadinessItem]) -> str:
    """사이드바 환경 점검 요약 필 텍스트 (시안 5a).

    실행 가능(전부 정상) / 실행 가능 · 경고 n(선택 항목만 결측) /
    실행 불가(필수 결측).
    """
    if blocking_problems(list(items)):
        return "실행 불가"
    warnings = sum(1 for item in items if not item.ok)
    return f"실행 가능 · 경고 {warnings}" if warnings else "실행 가능"


_ACTION_VERBS = {
    ACTION_CREATE: "에이전트를 생성할",
    ACTION_REVISE: "명세를 수정할",
    ACTION_RUN: "에이전트를 실행할",
}


def denial_reason(principal: Principal, action: str) -> str:
    """권한 비활성 버튼 옆에 붙일 사유 한 줄 (시안 5a).

    "{역할} 역할은 {행위} 수 없습니다" — 행위별 한국어 술어로 풀어 쓴다.
    """
    verb = _ACTION_VERBS.get(action, f"'{action}' 행위를 수행할")
    return f"{principal.role_name} 역할은 {verb} 수 없습니다"


def principal_names(config: IamConfig) -> list[str]:
    """사이드바 selectbox에 올릴 주체 목록.

    기본 주체(admin)를 맨 앞에 둔다 — selectbox의 기본 선택이 첫 항목이라,
    주체를 고르지 않은 사용자는 CLI와 똑같이 admin으로 동작해야 한다.
    """
    names = sorted(config.principals)
    if DEFAULT_PRINCIPAL in names:
        names.remove(DEFAULT_PRINCIPAL)
        names.insert(0, DEFAULT_PRINCIPAL)
    return names


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
