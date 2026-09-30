"""UI 로직 — Streamlit 위젯과 분리된 순수 함수들 (Phase 4).

`ui/app.py`는 그리기만 하고 판단은 여기서 한다. Streamlit 앱은 자동 테스트가
어렵지만 이 모듈은 평범한 함수라 그대로 테스트할 수 있다.
"""

from __future__ import annotations

import html
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from runtime.messages import last_text, message_text
from runtime.spec_diff import SpecDiff

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


def _readiness_state(item: ReadinessItem) -> tuple[str, str, str]:
    """(아이콘 이름, 톤 클래스, 상태 라벨) — 시안 5a의 환경 점검 3단계."""
    if item.ok:
        return "check_circle", "ok", "정상"
    if item.required:
        return "cancel", "err", "필수 누락"
    return "error", "warn", "경고"


def readiness_rows_html(items: Sequence[ReadinessItem]) -> str:
    """환경 점검 목록을 그리드 HTML로 (Phase 8 단계 2 보완, 시안 1a).

    아이콘 | 이름 | 상태(우측 정렬) 3열 그리드에 설명이 둘째 줄로 붙는다.
    st.markdown+st.caption 나열보다 행 간격이 조밀하다. 클래스는
    ui/style.py의 `.dba-env*`, 아이콘은 Material Symbols 리가처다.
    """
    rows = []
    for item in items:
        icon, tone, status = _readiness_state(item)
        # 환경변수 키(대문자+밑줄)만 고정폭 — 한글 라벨은 본문 폰트로 남긴다.
        label_cls = "dba-env__label"
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", item.label):
            label_cls += " dba-env__label--code"
        detail = (
            f'<span class="dba-env__detail">{html.escape(item.detail)}</span>'
            if item.detail
            else ""
        )
        rows.append(
            '<div class="dba-env__row">'
            f'<span class="dba-env__icon dba-env--{tone}">{icon}</span>'
            f'<span class="{label_cls}">{html.escape(item.label)}</span>'
            f'<span class="dba-env__status dba-env--{tone}">{status}</span>'
            f"{detail}</div>"
        )
    return f'<div class="dba-env">{"".join(rows)}</div>'


def user_card_html(name: str, subtitle: str = "Okta · OIDC") -> str:
    """OIDC 신원 카드 HTML (Phase 8 단계 2 보완, 시안 1a).

    이메일을 마크다운에 넣으면 자동 링크가 걸린다 — HTML 일반 텍스트로
    그리고, 이니셜 아바타(로컬 파트 첫 알파벳 2자)를 붙인다.
    """
    local = name.split("@", 1)[0]
    letters = [ch for ch in local if ch.isalpha()]
    avatar = "".join(letters[:2]).upper() or "?"
    return (
        '<div class="dba-user">'
        f'<span class="dba-user__avatar">{html.escape(avatar)}</span>'
        '<span class="dba-user__meta">'
        f'<span class="dba-user__name">{html.escape(name)}</span>'
        f'<span class="dba-user__sub">{html.escape(subtitle)}</span>'
        "</span></div>"
    )


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


def spec_version(name: str, directory: Path = Path("specs")) -> int:
    """명세의 현재 버전 — 이력 파일(`<directory>/<name>/v*.json`) 개수다.

    이력이 없으면 0. 스키마에 버전 필드를 두지 않는 대신 저장 이력이
    곧 버전이다 (Phase 8 단계 3, builder.save_spec과 같은 규칙).
    """
    history_dir = directory / name
    if not history_dir.is_dir():
        return 0
    return len(list(history_dir.glob("v*.json")))


def version_label(previous: int) -> str:
    """저장 성공 메시지의 버전 표기 — 첫 저장은 "v1", 이후는 "v2 → v3"."""
    if previous <= 0:
        return "v1"
    return f"v{previous} → v{previous + 1}"


def diff_as_diff_text(diff: SpecDiff) -> str:
    """SpecDiff를 diff 문법 텍스트로 — `st.code(language="diff")`용.

    format_diff의 들여쓴 `~`/`+ 도구` 형식은 diff 하이라이터가 색을 못
    입힌다(+/−가 줄 머리에 와야 한다). 필드 변경은 −이전/+이후 두 줄로,
    팀원 변경은 문맥 줄 아래 들여쓴 +/− 상세로 편다.
    """
    lines: list[str] = []
    for change in diff.fields:
        lines.append(f"- {change.name}: {change.before}")
        lines.append(f"+ {change.name}: {change.after}")
    for key in diff.tools_added:
        lines.append(f"+ 도구 {key}")
    for key in diff.tools_removed:
        lines.append(f"- 도구 {key}")
    for name in diff.members_added:
        lines.append(f"+ 팀원 {name}")
    for name in diff.members_removed:
        lines.append(f"- 팀원 {name}")
    for member in diff.members_changed:
        lines.append(f"  팀원 {member.name}")
        for change in member.fields:
            lines.append(f"-   {change.name}: {change.before}")
            lines.append(f"+   {change.name}: {change.after}")
        for key in member.tools_added:
            lines.append(f"+   도구 {key}")
        for key in member.tools_removed:
            lines.append(f"-   도구 {key}")
    return "\n".join(lines)


# --- 평가 대시보드 (Phase 8 단계 5) -----------------------------------------
# eval 레이어의 실제 검사 5종(eval/checks.py)과 화면 표기 라벨.
# dict 순서가 곧 대시보드 표시 순서다.
_CHECK_LABELS = {
    "expected_tools": "기대 도구 선택",
    "forbidden_tools": "금지 도구 회피",
    "team_shape": "팀 필요 판단",
    "subagent_tools": "팀원 도구",
    "guardrail": "가드레일 문장",
}


def check_label(name: str) -> str:
    """검사 이름의 한글 라벨. 모르는 이름은 그대로 돌려준다."""
    return _CHECK_LABELS.get(name, name)


def check_pass_rates(report) -> list[tuple[str, int, int]]:
    """EvalReport → 검사 이름별 (이름, 통과 수, 전체 수) 목록.

    생성 실패로 checks가 빈 케이스는 분모에 넣지 않는다 — 검사가 돌지
    않은 것이지 실패한 것이 아니다. 순서는 _CHECK_LABELS 선언 순서,
    모르는 검사 이름은 나온 순서대로 뒤에 붙는다.
    """
    counts: dict[str, list[int]] = {}
    for result in report.results:
        for check in result.checks:
            passed, total = counts.setdefault(check.name, [0, 0])
            counts[check.name] = [passed + (1 if check.passed else 0), total + 1]

    ordered = [name for name in _CHECK_LABELS if name in counts]
    ordered += [name for name in counts if name not in _CHECK_LABELS]
    return [(name, counts[name][0], counts[name][1]) for name in ordered]


def failed_first(results: Sequence) -> list:
    """케이스 결과를 실패 먼저로 정렬한다 (안정 정렬 — 그룹 내 원래 순서 유지)."""
    return sorted(results, key=lambda r: r.passed)


def case_title(case_id: str, request: str, limit: int = 40) -> str:
    """케이스 expander 제목 — 요구가 길어도 한 줄로 남게 앞 40자에서 자른다.

    전체 요구는 expander 안쪽에 따로 보여준다.
    """
    return f"{case_id} · {_truncate(request, limit)}"


def format_duration(seconds: float) -> str:
    """소요시간을 "1분 48초" / "48초"로."""
    whole = int(round(seconds))
    minutes, secs = divmod(whole, 60)
    return f"{minutes}분 {secs}초" if minutes else f"{secs}초"


# 화면 표시용 이름 — 식별자(name)는 파일명·IAM 리소스·감사 로그·CLI에서
# 그대로 쓰므로 바꾸지 않는다. 표시만 분리한다 (Phase 8 단계 2 보완).
_DISPLAY_NAMES = {
    "data_analysis_team": "데이터 분석 팀",
    "research_team": "리서치 팀",
    "doc_qa_team": "문서 Q&A 팀",
}


def display_name(identifier: str) -> str:
    """식별자의 화면 표시 이름. 매핑이 없으면 밑줄을 공백으로 바꾼다."""
    return _DISPLAY_NAMES.get(identifier, identifier.replace("_", " "))


_HANGUL_START, _HANGUL_END = 0xAC00, 0xD7A3


def with_object_josa(word: str) -> str:
    """단어 뒤에 목적격 조사(을/를)를 붙인다.

    한글 음절은 받침 유무로 판정하고(받침 있으면 '을'), 한글이 아니면
    판정할 수 없으므로 '을(를)'로 병기한다.
    """
    last = word[-1] if word else ""
    code = ord(last) if last else 0
    if _HANGUL_START <= code <= _HANGUL_END:
        josa = "을" if (code - _HANGUL_START) % 28 else "를"
        return f"{word}{josa}"
    return f"{word}을(를)"


def spec_overview(spec: AgentSpec) -> dict[str, str]:
    """스펙을 표로 보여주기 위한 납작한 요약."""
    return {
        "name": spec.name,
        "model": spec.model,
        "tools": ", ".join(spec.tools) or "(none)",
        "subagents": ", ".join(s.name for s in spec.subagents) or "(none)",
        "spec_version": spec.spec_version,
    }


def team_rows(spec: AgentSpec) -> list[dict[str, object]]:
    """팀 구성을 표 형태로. 팀이 없으면 빈 목록.

    tools는 목록 그대로 준다 — st.dataframe의 ListColumn이 배지로 그린다.
    도구가 없으면 빈 칸 대신 "(없음)"을 보여준다.
    """
    return [
        {
            "name": sub.name,
            "tools": list(sub.tools) or ["(없음)"],
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


# 단계 하나: (종류, 이름, 인자 요약, 결과 요약).
# 종류는 "delegate"(task 도구 위임) 또는 "tool"(일반 도구 호출)이다.
Step = tuple[str, str, str, str]

_SUMMARY_LIMIT = 60

# deepagents의 위임 도구 이름과 인자 키 — 설치본 0.7.5
# middleware/subagents.py의 StructuredTool(name="task")·TaskToolSchema
# (description, subagent_type)로 확인했다. 추측이 아니다.
_TASK_TOOL = "task"


def _truncate(value: object, limit: int = _SUMMARY_LIMIT) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def extract_steps(messages: Sequence) -> list[Step]:
    """메시지 목록에서 리더 수준의 실행 단계를 뽑는다 (Phase 8 단계 4).

    AIMessage.tool_calls를 순서대로 읽고, ToolMessage(tool_call_id)로 결과를
    맞춘다. `task` 호출은 위임으로 분류해 대상(subagent_type)과 작업 내용
    (description)을 보여준다. 서브에이전트 내부 단계는 이 이력에 없다 —
    스트리밍·내부 단계는 단계 7 조사 대상이다.
    """
    results: dict[str, str] = {}
    for message in messages:
        if getattr(message, "type", None) == "tool":
            call_id = getattr(message, "tool_call_id", None)
            if call_id:
                results[call_id] = message_text(message)

    steps: list[Step] = []
    for message in messages:
        if getattr(message, "type", None) != "ai":
            continue
        for call in getattr(message, "tool_calls", None) or []:
            name = call.get("name", "?")
            args = call.get("args") or {}
            result = _truncate(results.get(call.get("id"), ""))
            if name == _TASK_TOOL:
                steps.append(
                    (
                        "delegate",
                        str(args.get("subagent_type", "?")),
                        _truncate(args.get("description", "")),
                        result,
                    )
                )
            else:
                args_text = ", ".join(f"{k}={v!r}" for k, v in args.items())
                steps.append(("tool", name, _truncate(args_text), result))
    return steps


def render_turns(history: list) -> list[tuple[str, str, list[Step]]]:
    """대화 이력을 (역할, 텍스트, 단계 목록)으로 편다 (Phase 8 단계 4).

    사용자 발화가 턴 경계다. 턴 안의 단계는 마지막 에이전트 응답에 붙는다 —
    UI가 응답 위에 st.status로 그린다. 텍스트 없이 도구만 호출한 턴도
    단계가 있으면 남긴다 (기존 render_history는 그 턴을 통째로 버렸다).
    """
    rows: list[tuple[str, str, list[Step]]] = []
    segment: list = []

    def flush() -> None:
        if not segment:
            return
        steps = extract_steps(segment)
        texts = [
            text
            for message in segment
            if getattr(message, "type", None) == "ai"
            and (text := message_text(message)).strip()
        ]
        for text in texts[:-1]:
            rows.append(("assistant", text, []))
        if texts:
            rows.append(("assistant", texts[-1], steps))
        elif steps:
            rows.append(("assistant", "", steps))
        segment.clear()

    for message in history:
        if isinstance(message, dict):
            flush()
            rows.append((message.get("role", "user"), message.get("content", ""), []))
            continue
        if getattr(message, "type", None) == "human":
            flush()
            rows.append(("user", message_text(message), []))
            continue
        segment.append(message)
    flush()
    return rows


@dataclass
class LiveStep:
    """스트리밍 중 수집되는 실행 단계 (Phase 8 단계 7).

    depth 0은 리더 수준(위임·리더 도구), 1은 서브에이전트 내부 도구다.
    duration은 결과가 도착한 뒤에야 채워진다 — 이벤트 도착 시각의 델타라
    근사값이다 (LangGraph는 시각을 주지 않는다).
    """

    kind: str  # "delegate" | "tool"
    name: str
    args_summary: str
    depth: int = 0
    result_summary: str = ""
    duration: float | None = None
    call_id: str | None = None


_STREAM_NODES = {"model", "tools"}  # 그 외(미들웨어 훅)는 단계가 아니다


def _leader_step(call: dict) -> LiveStep:
    args = call.get("args") or {}
    if call.get("name") == _TASK_TOOL:
        return LiveStep(
            "delegate",
            str(args.get("subagent_type", "?")),
            _truncate(args.get("description", "")),
            call_id=call.get("id"),
        )
    args_text = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return LiveStep(
        "tool", call.get("name", "?"), _truncate(args_text), call_id=call.get("id")
    )


def _insert_inner(steps: list[LiveStep], delegate: LiveStep | None, step: LiveStep) -> None:
    """내부 단계를 해당 위임 블록의 끝에 끼운다. 위임을 모르면 맨 뒤에."""
    if delegate is None or delegate not in steps:
        steps.append(step)
        return
    index = steps.index(delegate) + 1
    while index < len(steps) and steps[index].depth == 1:
        index += 1
    steps.insert(index, step)


def _stream_reply(
    agent, history: list, on_update: Callable[[list[LiveStep]], None] | None
) -> tuple[list, str, list[LiveStep]]:
    steps: list[LiveStep] = []
    started: dict[str, float] = {}
    pending_delegations: list[LiveStep] = []  # 네임스페이스 미배정 위임 (호출 순)
    ns_to_delegate: dict[tuple, LiveStep] = {}
    final_state: dict | None = None

    def notify() -> None:
        if on_update is not None:
            on_update(list(steps))

    for namespace, mode, chunk in agent.stream(
        {"messages": history}, subgraphs=True, stream_mode=["updates", "values"]
    ):
        now = time.perf_counter()
        if mode == "values":
            if namespace == ():
                final_state = chunk  # 마지막 루트 values가 최종 대화 상태다
            continue
        for node, payload in chunk.items():
            if node not in _STREAM_NODES:
                continue  # 미들웨어 이벤트 필터 (조사 주의사항 ③)
            messages = (payload or {}).get("messages") or []
            if namespace == ():
                _apply_leader_event(node, messages, steps, started, pending_delegations, now)
            else:
                delegate = ns_to_delegate.get(namespace)
                if delegate is None and pending_delegations:
                    # uuid는 tool_call_id와 다르다 — 호출 순서로 배정한다 (주의사항 ①)
                    delegate = pending_delegations.pop(0)
                    ns_to_delegate[namespace] = delegate
                _apply_inner_event(
                    node, messages, steps, started, delegate, namespace, now
                )
            notify()

    if not isinstance(final_state, dict) or "messages" not in final_state:
        raise RuntimeError("스트리밍이 최종 상태(values)를 돌려주지 않았다")
    messages = final_state["messages"]
    return messages, last_text(messages), steps


def _apply_leader_event(
    node: str,
    messages: Sequence,
    steps: list[LiveStep],
    started: dict[str, float],
    pending_delegations: list[LiveStep],
    now: float,
) -> None:
    if node == "model":
        for message in messages:
            for call in getattr(message, "tool_calls", None) or []:
                step = _leader_step(call)
                if step.kind == "delegate":
                    pending_delegations.append(step)
                if step.call_id:
                    started[step.call_id] = now
                steps.append(step)
        return
    for message in messages:  # node == "tools" — 결과를 call_id로 맞춘다
        call_id = getattr(message, "tool_call_id", None)
        for step in steps:
            if step.depth == 0 and step.call_id == call_id:
                step.result_summary = _truncate(message_text(message))
                step.duration = now - started.get(call_id, now)


def _apply_inner_event(
    node: str,
    messages: Sequence,
    steps: list[LiveStep],
    started: dict[str, float],
    delegate: LiveStep | None,
    namespace: tuple,
    now: float,
) -> None:
    if node == "model":
        for message in messages:
            for call in getattr(message, "tool_calls", None) or []:
                key = f"{namespace}:{call.get('id')}"
                args = call.get("args") or {}
                args_text = ", ".join(f"{k}={v!r}" for k, v in args.items())
                step = LiveStep(
                    "tool",
                    call.get("name", "?"),
                    _truncate(args_text),
                    depth=1,
                    call_id=key,
                )
                started[key] = now
                _insert_inner(steps, delegate, step)
        return
    for message in messages:
        key = f"{namespace}:{getattr(message, 'tool_call_id', None)}"
        for step in steps:
            if step.call_id == key:
                step.result_summary = _truncate(message_text(message))
                step.duration = now - started.get(key, now)


def stream_agent_reply(
    agent,
    history: list,
    on_update: Callable[[list[LiveStep]], None] | None = None,
) -> tuple[list, str, list[LiveStep], bool]:
    """스트리밍으로 한 턴 실행 — (새 이력, 표시 텍스트, 단계, 스트리밍 여부).

    단계가 도착할 때마다 on_update(steps)를 불러 UI가 실시간 갱신하게 한다.
    스트리밍이 어떤 이유로든 실패하면(미지원·중간 예외·최종 상태 미수신 —
    주의사항 ②) **기존 invoke 경로(agent_reply)로 처음부터 다시 실행**한다.
    부분 스트림 상태를 신뢰해 이어붙이지 않는다 — 폴백 시 단계는 빈다.
    """
    try:
        history_out, reply, steps = _stream_reply(agent, history, on_update)
    except Exception:  # noqa: BLE001 - 스트리밍 실패로 대화가 끊기면 안 된다
        history_out, reply = agent_reply(agent, history)
        return history_out, reply, [], False
    return history_out, reply, steps, True


def render_history(history: list) -> list[tuple[str, str]]:
    """대화 이력을 (역할, 텍스트) 목록으로 납작하게 만든다.

    render_turns의 텍스트 투영이다 — 단계가 필요 없는 곳(테스트·간단 표시)용.
    텍스트가 빈 행(도구만 호출한 턴)은 여기서는 뺀다.
    """
    return [
        (role, text) for role, text, _steps in render_turns(history) if text.strip()
    ]
