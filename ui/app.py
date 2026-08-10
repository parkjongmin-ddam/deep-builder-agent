"""Streamlit 2패널 UI (Phase 4).

    streamlit run ui/app.py

구성:
- 사이드바: 환경 점검 (키·트레이싱·MCP). 비밀값은 존재 여부만 표시한다
- 탭 "빌더": 왼쪽에서 자연어로 에이전트를 만들고, 오른쪽에서 바로 대화한다
- 탭 "평가": 케이스를 돌려 Builder 회귀를 확인한다

이 파일은 **그리기만** 한다. 판단은 ui/state.py, 실행은 builder/·runtime/·eval/에 있다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

# `streamlit run ui/app.py`는 프로젝트 루트를 sys.path에 넣어주지 않는다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from builder.builder import (  # noqa: E402
    SpecGenerationError,
    generate_spec,
    revise_spec,
    save_spec,
)
from eval.dataset import load_cases  # noqa: E402
from eval.judge import judge_spec  # noqa: E402
from eval.runner import format_report, run_evaluation  # noqa: E402
from registry import MCP_PREFIX  # noqa: E402
from registry.mcp import MCPConfigError, load_tools_by_server  # noqa: E402
from runtime.config import load_env  # noqa: E402
from runtime.factory import build_agent  # noqa: E402
from runtime.spec import AgentSpec, load_spec_file  # noqa: E402
from runtime.spec_diff import diff_specs, format_diff  # noqa: E402
from runtime.tracing import TracingConfigError, configure_tracing  # noqa: E402
from ui.state import (  # noqa: E402
    agent_reply,
    append_turn,
    blocking_problems,
    check_readiness,
    render_history,
    spec_overview,
    team_rows,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# check_readiness()가 os.environ을 읽기 전에 .env를 올려야 한다.
# 빠뜨리면 키가 있는데도 사이드바가 "미설정"으로 실행을 막는다.
load_env()

st.set_page_config(page_title="deep_builder_agent", layout="wide")


# --- 사이드바: 환경 점검 ---------------------------------------------------


def render_sidebar() -> list[str]:
    """환경 상태를 그리고, 실행을 막는 항목 목록을 돌려준다."""
    st.sidebar.header("환경")

    items = check_readiness()
    for item in items:
        icon = "✅" if item.ok else ("❌" if item.required else "⚠️")
        st.sidebar.markdown(f"{icon} **{item.label}**")
        st.sidebar.caption(item.detail)

    blockers = blocking_problems(items)
    if blockers:
        st.sidebar.error(f"실행 불가: {', '.join(blockers)} 미설정")

    try:
        configure_tracing()
    except TracingConfigError as exc:
        st.sidebar.error(str(exc))

    return blockers


# --- 에이전트 생성 ---------------------------------------------------------


def instantiate(spec: AgentSpec):
    """스펙으로 실행 가능한 에이전트를 만든다. 실패하면 (None, 오류문)."""
    keys = sorted({*spec.tools, *(t for s in spec.subagents for t in s.tools)})
    try:
        by_server = load_tools_by_server(keys)
    except MCPConfigError as exc:
        return None, f"MCP 도구 로드 실패: {exc}"

    leader_mcp = [
        tool
        for key in spec.tools
        if key.startswith(MCP_PREFIX)
        for tool in by_server.get(key[len(MCP_PREFIX) :], [])
    ]
    try:
        agent = build_agent(spec, extra_tools=leader_mcp, mcp_tools_by_server=by_server)
    except LookupError as exc:
        return None, f"도구 해석 실패: {exc}"
    return agent, ""


def activate(spec: AgentSpec) -> None:
    """스펙을 현재 대화 대상으로 올린다."""
    agent, error = instantiate(spec)
    if agent is None:
        st.error(error)
        return
    st.session_state.spec = spec
    st.session_state.agent = agent
    st.session_state.history = []


# --- 탭 1: 빌더 ------------------------------------------------------------


def render_builder_panel(blocked: bool) -> None:
    st.subheader("① 에이전트 만들기")

    with st.form("build"):
        request = st.text_area(
            "무엇을 하는 에이전트가 필요한가요?",
            placeholder="웹 검색으로 최신 IT 뉴스를 찾아 3줄로 요약해주는 에이전트 만들어줘",
            height=110,
        )
        submitted = st.form_submit_button("생성", disabled=blocked)

    if submitted and request.strip():
        with st.spinner("명세를 생성하는 중..."):
            try:
                spec = generate_spec(request.strip())
            except SpecGenerationError as exc:
                st.error(f"명세 생성 실패: {exc}\n\n마지막 원인: {exc.__cause__}")
                return
        saved = save_spec(spec)
        st.success(f"{saved} 에 저장했습니다")
        activate(spec)

    st.divider()
    st.caption("또는 준비된 팀 템플릿으로 시작하기")

    templates = sorted(TEMPLATES_DIR.glob("*.json"))
    if templates:
        choice = st.selectbox("템플릿", [p.stem for p in templates])
        if st.button("템플릿 불러오기", disabled=blocked):
            path = TEMPLATES_DIR / f"{choice}.json"
            activate(load_spec_file(path))
            st.success(f"{choice} 를 불러왔습니다")

    spec = st.session_state.get("spec")
    if spec is None:
        return

    st.divider()
    st.markdown("**현재 명세**")
    st.table(spec_overview(spec))

    rows = team_rows(spec)
    if rows:
        st.markdown("**팀 구성**")
        st.table(rows)

    render_revision_form(spec, blocked)


def render_revision_form(spec: AgentSpec, blocked: bool) -> None:
    """현재 명세를 자연어로 고친다.

    **변경 내역을 반드시 함께 보여준다.** 전체 명세를 다시 받는 방식이라
    요청하지 않은 문장이 다듬어질 수 있고, 그것이 보이지 않으면 사용자는
    자기가 쓴 프롬프트가 바뀐 줄 모른다.
    """
    st.divider()
    st.markdown("**② 명세 고치기**")

    with st.form("revise"):
        request = st.text_area(
            "무엇을 바꿀까요?",
            placeholder="결과를 파일로 저장하는 기능도 넣어줘",
            height=80,
        )
        submitted = st.form_submit_button("수정", disabled=blocked)

    if not (submitted and request.strip()):
        return

    with st.spinner("명세를 수정하는 중..."):
        try:
            revised = revise_spec(spec, request.strip())
        except SpecGenerationError as exc:
            st.error(f"수정 실패: {exc}\n\n마지막 원인: {exc.__cause__}")
            return

    diff = diff_specs(spec, revised)
    st.markdown("**변경 내역**")
    st.code(format_diff(diff), language="text")

    if diff.is_empty:
        st.info("바뀐 것이 없어 저장하지 않았습니다.")
        return

    saved = save_spec(revised)
    st.success(f"{saved} 에 저장했습니다")
    activate(revised)

    with st.expander("system_prompt 전문"):
        st.code(spec.system_prompt, language="markdown")
        for sub in spec.subagents:
            st.markdown(f"— **{sub.name}**")
            st.code(sub.system_prompt, language="markdown")


def render_chat_panel(blocked: bool) -> None:
    st.subheader("② 대화하기")

    agent = st.session_state.get("agent")
    if agent is None:
        st.info("왼쪽에서 에이전트를 만들거나 템플릿을 불러오세요.")
        return

    for role, text in render_history(st.session_state.get("history", [])):
        with st.chat_message(role):
            st.markdown(text)

    user_input = st.chat_input("메시지를 입력하세요", disabled=blocked)
    if not user_input:
        return

    history = append_turn(st.session_state.get("history", []), user_input)
    with st.spinner("에이전트가 작업 중..."):
        history, reply = agent_reply(agent, history)

    st.session_state.history = history
    # 정상 응답은 history에 들어 있어 rerun 후 그려진다. 오류는 history에 없으므로 여기서 띄운다.
    if reply.startswith("[error]"):
        st.error(reply)
    else:
        st.rerun()


# --- 탭 2: 평가 ------------------------------------------------------------


def render_eval_tab(blocked: bool) -> None:
    st.subheader("평가 — Builder 회귀 검사")
    st.caption(
        "케이스마다 자연어 요구로 명세를 생성한 뒤, 도구·팀·가드레일을 기계적으로 "
        "검사하고 통과한 것만 LLM 심판이 채점합니다."
    )

    try:
        cases = load_cases()
    except (ValueError, OSError) as exc:
        st.error(f"케이스를 읽지 못했습니다: {exc}")
        return

    st.write(f"등록된 케이스 **{len(cases)}건**")
    with st.expander("케이스 보기"):
        st.table(
            [
                {
                    "id": c.id,
                    "요구": c.request,
                    "기대 도구": ", ".join(c.expect_tools) or "(none)",
                    "팀": "필요" if c.expect_team else "불필요",
                }
                for c in cases
            ]
        )

    use_judge = st.checkbox("LLM 심판 사용 (비용 발생)", value=False)
    if not st.button("평가 실행", disabled=blocked):
        return

    with st.spinner("평가를 실행하는 중... 케이스마다 LLM을 호출합니다"):
        report = run_evaluation(cases, judge=judge_spec if use_judge else None)

    st.metric("통과율", f"{report.pass_rate:.0%}", f"{report.passed}/{report.total}")
    if report.mean_score is not None:
        st.metric("심판 평균", f"{report.mean_score:.2f} / 5")

    for result in report.results:
        icon = "✅" if result.passed else "❌"
        with st.expander(f"{icon} {result.case_id}"):
            st.caption(result.request)
            if result.error:
                st.error(result.error)
            for check in result.checks:
                (st.success if check.passed else st.error)(
                    f"{check.name}: {check.detail}"
                )
            if result.verdict is not None:
                st.info(f"심판 {result.verdict.score}/5 — {result.verdict.reason}")

    with st.expander("텍스트 리포트"):
        st.code(format_report(report))


# --- 진입 ------------------------------------------------------------------


def main() -> None:
    st.title("deep_builder_agent")
    st.caption("자연어로 AI 에이전트를 만들고, 실행하고, 평가한다")

    blockers = render_sidebar()
    blocked = bool(blockers)

    build_tab, eval_tab = st.tabs(["빌더", "평가"])

    with build_tab:
        left, right = st.columns(2, gap="large")
        with left:
            render_builder_panel(blocked)
        with right:
            render_chat_panel(blocked)

    with eval_tab:
        render_eval_tab(blocked)


main()
