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
    ACTION_CREATE,
    ACTION_REVISE,
    ACTION_RUN,
    PermissionDeniedError,
    Principal,
    agent_reply,
    append_turn,
    authorize_action,
    badges_html,
    blocking_problems,
    check_readiness,
    chips_html,
    denial_reason,
    eval_case_icon,
    is_allowed,
    load_iam_config,
    oidc_configured,
    principal_names,
    readiness_rows_html,
    readiness_summary,
    render_history,
    user_card_html,
    user_identity,
    spec_overview,
    team_rows,
)
from ui.style import inject_css  # noqa: E402

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# check_readiness()가 os.environ을 읽기 전에 .env를 올려야 한다.
# 빠뜨리면 키가 있는데도 사이드바가 "미설정"으로 실행을 막는다.
load_env()

st.set_page_config(page_title="deep_builder_agent", layout="wide")
inject_css()


# --- 사이드바: 환경 점검 ---------------------------------------------------


def render_sidebar(
    iam_config, oidc_principal: Principal | None = None
) -> tuple[list[str], Principal]:
    """주체 표시/선택 + 환경 상태를 그리고, (실행 차단 목록, 주체)를 돌려준다.

    두 모드가 있다 (Phase 7):
    - **OIDC 모드**: 로그인된 신원이 곧 주체다 — 선택기가 없다. 인증이 있는데
      주체를 고를 수 있으면 인가가 장식이 된다.
    - **데모 모드**(OIDC 미설정): 기존처럼 주체를 직접 고른다. 인가 로직 자체는
      두 모드가 동일하다.
    """
    st.sidebar.markdown("#### :material/hub: deep_builder")

    st.sidebar.markdown("**사용자 · IAM**")
    if oidc_principal is None:
        st.sidebar.info(
            "**데모 모드** — OIDC가 설정되지 않아 주체를 직접 선택합니다.",
            icon=":material/info:",
        )
    with st.sidebar.container(border=True):
        if oidc_principal is not None:
            principal = oidc_principal
            # 이메일을 마크다운에 넣으면 자동 링크가 걸린다 — HTML 카드로 그린다.
            st.html(user_card_html(principal.name))
        else:
            choice = st.selectbox("주체", principal_names(iam_config))
            principal = iam_config.resolve(choice)
        st.caption("역할")
        st.html(badges_html([principal.role_name], accent=True))
        st.caption("허용 행위")
        st.html(chips_html(sorted(principal.role.actions)))
        st.caption("도구 경계")
        boundary = sorted(principal.role.tools)
        if boundary:
            st.html(chips_html(boundary, dashed=True))
        else:
            st.caption("없음 — 도구를 직접 실행하지 않는 역할")
        if oidc_principal is not None:
            st.button("로그아웃", icon=":material/logout:", on_click=st.logout)

    items = check_readiness()
    summary = readiness_summary(items)
    pill_color = "red" if summary == "실행 불가" else "green"
    st.sidebar.markdown(f"**환경 점검** · :{pill_color}[{summary}]")

    st.sidebar.html(readiness_rows_html(items))

    blockers = blocking_problems(items)
    if blockers:
        st.sidebar.error(
            f"실행 불가: {', '.join(blockers)} 미설정", icon=":material/cancel:"
        )

    try:
        configure_tracing()
    except TracingConfigError as exc:
        st.sidebar.error(str(exc))

    return blockers, principal


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


def render_builder_panel(blocked: bool, principal: Principal) -> None:
    st.subheader("① 에이전트 만들기")

    can_create = is_allowed(principal, ACTION_CREATE)
    can_run = is_allowed(principal, ACTION_RUN)
    templates = sorted(TEMPLATES_DIR.glob("*.json"))

    with st.form("build"):
        request = st.text_area(
            "무엇을 하는 에이전트가 필요한가요?",
            placeholder="웹 검색으로 최신 IT 뉴스를 찾아 3줄로 요약해주는 에이전트 만들어줘",
            height=110,
        )
        # 시안 1a — 생성 · "또는" · 템플릿 선택 · 불러오기를 한 줄에 배치한다.
        col_gen, col_or, col_tpl, col_load = st.columns(
            [0.9, 0.35, 1.5, 1.4], vertical_alignment="center"
        )
        with col_gen:
            submitted = st.form_submit_button(
                "생성",
                type="primary",
                icon=":material/auto_awesome:" if can_create else ":material/lock:",
                disabled=blocked or not can_create,
                help=None if can_create else denial_reason(principal, ACTION_CREATE),
            )
        with col_or:
            st.caption("또는")
        with col_tpl:
            template_choice = (
                st.selectbox(
                    "템플릿",
                    [p.stem for p in templates],
                    label_visibility="collapsed",
                )
                if templates
                else None
            )
        with col_load:
            load_template = st.form_submit_button(
                "템플릿 불러오기",
                icon=":material/download:" if can_run else ":material/lock:",
                disabled=blocked or not can_run or not templates,
                help=None if can_run else denial_reason(principal, ACTION_RUN),
            )
    if not can_create:
        st.caption(
            f":material/shield_person: {denial_reason(principal, ACTION_CREATE)}"
        )
    if not can_run:
        st.caption(f":material/shield_person: {denial_reason(principal, ACTION_RUN)}")

    if load_template and template_choice:
        # 템플릿 활성화는 '기존 에이전트 실행'이다 — 경계는 부여(생성) 시점에만
        # 적용되므로 run_agent 행위 검사만 받는다 (runtime/iam.py 의미론 참조).
        try:
            authorize_action(principal, ACTION_RUN, resource=template_choice)
        except PermissionDeniedError as exc:
            st.error(f"**IAM 거부.** {exc}", icon=":material/block:")
            return
        activate(load_spec_file(TEMPLATES_DIR / f"{template_choice}.json"))
        st.success(
            f"**{template_choice} 를 불러왔습니다.**", icon=":material/check_circle:"
        )

    if submitted and request.strip():
        # 위젯 비활성은 UX일 뿐이다 — 인가는 여기서 다시 판정하고 감사에 남긴다.
        try:
            authorize_action(principal, ACTION_CREATE)
        except PermissionDeniedError as exc:
            st.error(f"**IAM 거부.** {exc}", icon=":material/block:")
            return
        with st.spinner("명세를 생성하는 중..."):
            try:
                spec = generate_spec(
                    request.strip(), allowed_tools=principal.role.tools
                )
            except SpecGenerationError as exc:
                st.error(
                    f"**명세 생성에 실패했습니다.** {exc}\n\n마지막 원인: {exc.__cause__}",
                    icon=":material/cancel:",
                )
                return
        saved = save_spec(spec)
        st.success(f"**명세를 저장했습니다.** {saved}", icon=":material/check_circle:")
        activate(spec)

    spec = st.session_state.get("spec")
    if spec is None:
        return

    st.divider()
    render_spec_card(spec)
    render_revision_form(spec, blocked, principal)


def render_spec_card(spec: AgentSpec) -> None:
    """현재 명세를 카드형으로 그린다 (시안 1a — st.table 대체)."""
    overview = spec_overview(spec)
    with st.container(border=True):
        st.caption("현재 명세")
        st.markdown(f"**`{overview['name']}`**")
        st.caption(spec.description)

        col_model, col_tools, col_team = st.columns(3)
        with col_model:
            st.caption("모델")
            st.markdown(f"`{overview['model']}`")
        with col_tools:
            st.caption("도구")
            if spec.tools:
                st.html(badges_html(spec.tools))
            else:
                st.caption("(없음)")
        with col_team:
            st.caption("서브에이전트")
            st.markdown(f"**{len(spec.subagents)}개**")

        rows = team_rows(spec)
        if rows:
            st.dataframe(
                rows,
                hide_index=True,
                column_config={
                    "name": st.column_config.TextColumn("서브에이전트"),
                    "tools": st.column_config.TextColumn("도구"),
                    "description": st.column_config.TextColumn(
                        "설명", width="large"
                    ),
                },
            )


def render_revision_form(spec: AgentSpec, blocked: bool, principal: Principal) -> None:
    """현재 명세를 자연어로 고친다.

    **변경 내역을 반드시 함께 보여준다.** 전체 명세를 다시 받는 방식이라
    요청하지 않은 문장이 다듬어질 수 있고, 그것이 보이지 않으면 사용자는
    자기가 쓴 프롬프트가 바뀐 줄 모른다.
    """
    st.divider()
    st.subheader("② 명세 고치기")

    can_revise = is_allowed(principal, ACTION_REVISE)
    with st.form("revise"):
        request = st.text_area(
            "어떻게 고칠까요?",
            placeholder="결과를 파일로 저장하는 기능도 넣어줘",
            height=80,
        )
        submitted = st.form_submit_button(
            "수정 적용",
            icon=":material/edit:" if can_revise else ":material/lock:",
            disabled=blocked or not can_revise,
            help=None if can_revise else denial_reason(principal, ACTION_REVISE),
        )
    if not can_revise:
        st.caption(
            f":material/shield_person: {denial_reason(principal, ACTION_REVISE)}"
        )

    if not (submitted and request.strip()):
        return

    try:
        authorize_action(principal, ACTION_REVISE, resource=spec.name)
    except PermissionDeniedError as exc:
        st.error(f"**IAM 거부.** {exc}", icon=":material/block:")
        return

    with st.spinner("명세를 수정하는 중..."):
        try:
            revised = revise_spec(
                spec, request.strip(), allowed_tools=principal.role.tools
            )
        except SpecGenerationError as exc:
            st.error(
                f"**수정에 실패했습니다.** {exc}\n\n마지막 원인: {exc.__cause__}",
                icon=":material/cancel:",
            )
            return

    diff = diff_specs(spec, revised)
    st.markdown("**변경 내역**")
    st.code(format_diff(diff), language="text")

    if diff.is_empty:
        st.info("**바뀐 것이 없어 저장하지 않았습니다.**", icon=":material/info:")
        return

    saved = save_spec(revised)
    st.success(f"**명세를 저장했습니다.** {saved}", icon=":material/check_circle:")
    activate(revised)

    with st.expander("system_prompt 전문", icon=":material/description:"):
        st.code(spec.system_prompt, language="markdown")
        for sub in spec.subagents:
            st.markdown(f"— **{sub.name}**")
            st.code(sub.system_prompt, language="markdown")


def render_chat_panel(blocked: bool, principal: Principal) -> None:
    st.subheader(":material/forum: 대화하기")

    agent = st.session_state.get("agent")
    if agent is None:
        st.info(
            "**아직 에이전트가 없습니다.** 왼쪽에서 만들거나 템플릿을 불러오세요.",
            icon=":material/info:",
        )
        return

    can_run = is_allowed(principal, ACTION_RUN)
    if not can_run:
        st.caption(f":material/shield_person: {denial_reason(principal, ACTION_RUN)}")

    # 시안 1a — 대화 이력은 고정 높이 카드 안에서 독립 스크롤한다.
    with st.container(height=640, border=True):
        for role, text in render_history(st.session_state.get("history", [])):
            with st.chat_message(role):
                st.markdown(text)

    user_input = st.chat_input(
        "에이전트에게 메시지 보내기", disabled=blocked or not can_run
    )
    if not user_input:
        return

    history = append_turn(st.session_state.get("history", []), user_input)
    with st.spinner("에이전트가 작업 중..."):
        history, reply = agent_reply(agent, history)

    st.session_state.history = history
    # 정상 응답은 history에 들어 있어 rerun 후 그려진다. 오류는 history에 없으므로 여기서 띄운다.
    if reply.startswith("[error]"):
        st.error(f"**에이전트 실행에 실패했습니다.** {reply}", icon=":material/cancel:")
    else:
        st.rerun()


# --- 탭 2: 평가 ------------------------------------------------------------


def render_eval_tab(blocked: bool, principal: Principal) -> None:
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

    # 평가는 케이스마다 Builder(create_agent)를 호출하므로 같은 인가를 받는다.
    can_eval = is_allowed(principal, ACTION_CREATE)
    if not can_eval:
        st.info(f"역할 {principal.role_name} 은 평가(Builder 호출)를 실행할 수 없습니다.")

    use_judge = st.checkbox("LLM 심판 사용 (비용 발생)", value=False)
    if not st.button("평가 실행", disabled=blocked or not can_eval):
        return

    with st.spinner("평가를 실행하는 중... 케이스마다 LLM을 호출합니다"):
        report = run_evaluation(cases, judge=judge_spec if use_judge else None)

    st.metric("통과율", f"{report.pass_rate:.0%}", f"{report.passed}/{report.total}")
    if report.mean_score is not None:
        st.metric("심판 평균", f"{report.mean_score:.2f} / 5")

    for result in report.results:
        with st.expander(result.case_id, icon=eval_case_icon(result.passed)):
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
    # 시안 1a — 제목 옆에 부제를 같은 베이스라인으로 놓는다.
    col_title, col_sub = st.columns([0.32, 0.68], vertical_alignment="bottom")
    with col_title:
        st.title("deep_builder_agent")
    with col_sub:
        st.caption("자연어로 AI 에이전트를 만들고, 실행하고, 평가한다")

    # 정책 파일이 깨졌으면 여기서 멈춘다 — 기본 정책으로 조용히 넘어가지 않는다.
    try:
        iam_config = load_iam_config()
    except (ValueError, OSError) as exc:
        st.error(f"IAM 정책 오류: {exc}")
        st.stop()

    # OIDC 인증 게이트 (Phase 7). `.streamlit/secrets.toml`의 [auth]가 있으면
    # 로그인 없이는 아무 화면도 그리지 않는다. 미설정이면 데모 모드로 폴백해
    # "clone 후 5분" 경로와 오프라인 테스트가 그대로 유지된다.
    oidc_principal = None
    if oidc_configured(st.secrets):
        if not st.user.is_logged_in:
            st.info("OIDC 인증이 설정된 앱입니다. IdP(Okta 등)로 로그인하세요.")
            st.button("🔐 로그인", on_click=st.login)
            st.stop()
        email, groups = user_identity(st.user.to_dict())
        try:
            # 로그인 성공 ≠ 인가 — 역할 매핑이 없으면 여기서 거부된다.
            oidc_principal = iam_config.resolve_identity(email, groups)
        except PermissionDeniedError as exc:
            st.error(f"IAM 거부: {exc}")
            st.caption("관리자에게 iam.json의 groups/principals 매핑 추가를 요청하세요.")
            st.button("로그아웃", on_click=st.logout)
            st.stop()

    blockers, principal = render_sidebar(iam_config, oidc_principal)
    blocked = bool(blockers)

    build_tab, eval_tab = st.tabs(
        [":material/construction: 빌더", ":material/fact_check: 평가"]
    )

    with build_tab:
        left, right = st.columns(2, gap="large")
        with left:
            # 시안 1a — 좌측 패널은 고정 높이 컨테이너에서 독립 스크롤한다.
            with st.container(height=700, border=False):
                render_builder_panel(blocked, principal)
        with right:
            render_chat_panel(blocked, principal)

    with eval_tab:
        render_eval_tab(blocked, principal)


main()
