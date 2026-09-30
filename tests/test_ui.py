"""UI 로직 테스트 — Streamlit 없이 판단 부분만 검증한다.

`ui/app.py`는 그리기만 하므로 테스트하지 않는다. 판단이 들어 있는
`ui/state.py`가 대상이다.
"""

from pathlib import Path

import pytest

from builder.prompts import GUARDRAIL_SENTENCE
from runtime.spec import AgentSpec
from ui.state import (
    agent_reply,
    append_turn,
    blocking_problems,
    check_readiness,
    render_history,
    spec_overview,
    team_rows,
)

APP_PATH = Path(__file__).resolve().parent.parent / "ui" / "app.py"

READY_ENV = {
    "ANTHROPIC_API_KEY": "synthetic-key",
    "TAVILY_API_KEY": "synthetic-key",
    "LANGSMITH_TRACING": "true",
    "LANGSMITH_API_KEY": "synthetic-key",
}


def _spec(**over) -> AgentSpec:
    d = dict(
        name="news_agent",
        description="뉴스 요약",
        system_prompt=f"너는 요약가다. {GUARDRAIL_SENTENCE}",
        tools=["web_search"],
    )
    d.update(over)
    return AgentSpec(**d)


class FakeMessage:
    def __init__(self, type_: str, content, tool_calls=None, tool_call_id=None):
        self.type = type_
        self.content = content
        if tool_calls is not None:
            self.tool_calls = tool_calls
        if tool_call_id is not None:
            self.tool_call_id = tool_call_id


class FakeAgent:
    def __init__(self, messages=None, error: Exception | None = None):
        self._messages = messages or []
        self._error = error

    def invoke(self, _payload):
        if self._error is not None:
            raise self._error
        return {"messages": self._messages}


# --- 환경 점검 -------------------------------------------------------------


def test_missing_anthropic_key_blocks_execution():
    items = check_readiness({})

    assert "ANTHROPIC_API_KEY" in blocking_problems(items)


def test_optional_keys_do_not_block():
    """Tavily·트레이싱이 없다고 앱을 막지는 않는다."""
    items = check_readiness({"ANTHROPIC_API_KEY": "synthetic-key"})

    assert blocking_problems(items) == []


def test_ready_environment_has_no_blockers():
    assert blocking_problems(check_readiness(READY_ENV)) == []


def test_readiness_rows_html_covers_three_states():
    """시안 5a의 환경 점검 3단계: 정상 / 경고 / 필수 누락 — 상태 라벨 우측 정렬 그리드."""
    from runtime.readiness import ReadinessItem
    from ui.state import readiness_rows_html

    out = readiness_rows_html(
        [
            ReadinessItem(label="KEY", ok=True, detail="필요한 이유", required=True),
            ReadinessItem(label="OPT", ok=False, detail="", required=False),
            ReadinessItem(label="REQ", ok=False, detail="", required=True),
        ]
    )

    assert out.count('class="dba-env__row"') == 3
    assert "check_circle" in out and "정상" in out
    assert "error" in out and "경고" in out
    assert "cancel" in out and "필수 누락" in out
    assert "필요한 이유" in out


def test_readiness_rows_html_monospaces_only_env_var_names():
    """키 이름(대문자+밑줄)만 고정폭, 한글 라벨은 본문 폰트다 (단계 2 보완)."""
    from runtime.readiness import ReadinessItem
    from ui.state import readiness_rows_html

    out = readiness_rows_html(
        [
            ReadinessItem(label="ANTHROPIC_API_KEY", ok=True, detail="", required=True),
            ReadinessItem(label="LangSmith 트레이싱", ok=True, detail="", required=False),
        ]
    )

    code = 'class="dba-env__label dba-env__label--code">ANTHROPIC_API_KEY<'
    plain = 'class="dba-env__label">LangSmith 트레이싱<'
    assert code in out
    assert plain in out


def test_readiness_rows_html_escapes_labels():
    from runtime.readiness import ReadinessItem
    from ui.state import readiness_rows_html

    out = readiness_rows_html(
        [ReadinessItem(label="<KEY>", ok=True, detail="<detail>", required=True)]
    )

    assert "&lt;KEY&gt;" in out and "<KEY>" not in out
    assert "&lt;detail&gt;" in out


def test_user_card_html_shows_initials_and_plain_email():
    """이메일이 마크다운 자동 링크로 변하면 안 된다 — HTML 일반 텍스트로 그린다."""
    from ui.state import user_card_html

    out = user_card_html("user01@example.com")

    assert 'class="dba-user__avatar">PJ<' in out
    assert "user01@example.com" in out
    assert "Okta · OIDC" in out
    assert "href" not in out


def test_user_card_html_handles_nameless_local_part():
    from ui.state import user_card_html

    assert 'class="dba-user__avatar">?<' in user_card_html("754@example.com")


def test_eval_case_icon_maps_pass_and_fail():
    """expander icon 파라미터는 색 지시자 없이 아이콘 이름만 받는다 (Phase 8)."""
    from ui.state import eval_case_icon

    assert eval_case_icon(True) == ":material/check_circle:"
    assert eval_case_icon(False) == ":material/cancel:"


def test_readiness_never_exposes_secret_values():
    """화면에 키 값이 새면 안 된다. 존재 여부만 다룬다."""
    rendered = " ".join(
        f"{item.label} {item.detail}" for item in check_readiness(READY_ENV)
    )

    assert "synthetic-key" not in rendered


# --- 배지·칩·요약 (Phase 8 단계 2) ------------------------------------------


def test_badges_html_renders_and_escapes():
    """도구 키를 배지 span으로. 외부 입력이 아니어도 이스케이프는 기본이다."""
    from ui.state import badges_html

    out = badges_html(["web_search", "<b>"])

    assert out.count('class="dba-badge"') == 2
    assert "web_search" in out
    assert "&lt;b&gt;" in out and "<b>" not in out


def test_badges_html_accent_variant():
    from ui.state import badges_html

    assert 'dba-badge--accent' in badges_html(["builder"], accent=True)


def test_chips_html_solid_and_dashed():
    from ui.state import chips_html

    solid = chips_html(["create_agent"])
    dashed = chips_html(["calculate"], dashed=True)

    assert 'class="dba-chip"' in solid and "--dashed" not in solid
    assert 'class="dba-chip dba-chip--dashed"' in dashed


def test_readiness_summary_three_states():
    """사이드바 요약 필: 실행 가능(녹) / 실행 가능·경고 n / 실행 불가 (시안 5a)."""
    from runtime.readiness import ReadinessItem
    from ui.state import readiness_summary

    ok = ReadinessItem(label="A", ok=True, detail="", required=True)
    warn = ReadinessItem(label="B", ok=False, detail="", required=False)
    missing = ReadinessItem(label="C", ok=False, detail="", required=True)

    assert readiness_summary([ok]) == "실행 가능"
    assert readiness_summary([ok, warn, warn]) == "실행 가능 · 경고 2"
    assert readiness_summary([ok, missing]) == "실행 불가"


def test_badge_palette_css_follows_detected_theme():
    """st.context.theme을 읽을 수 있으면 배지 색을 그 테마로 고정한다 (Phase 8 보완).

    감지 불가(None)면 prefers-color-scheme 미디어 쿼리로 폴백한다.
    """
    from ui.style import badge_palette_css

    dark = badge_palette_css("dark")
    light = badge_palette_css("light")
    fallback = badge_palette_css(None)

    assert "#6AA8FF" in dark and "@media" not in dark
    assert "#1F6FD1" in light and "@media" not in light
    assert "prefers-color-scheme" in fallback


def test_denial_reason_names_role_and_action():
    """권한 비활성 버튼 옆 사유 한 줄 (시안 5a) — 행위별 한국어 술어."""
    from runtime.iam import ACTION_CREATE, ACTION_REVISE, ACTION_RUN, load_iam_config
    from ui.state import denial_reason

    viewer = load_iam_config().resolve("demo_viewer")

    assert denial_reason(viewer, ACTION_CREATE) == "viewer 역할은 에이전트를 생성할 수 없습니다"
    assert "수정할 수 없습니다" in denial_reason(viewer, ACTION_REVISE)
    assert "실행할 수 없습니다" in denial_reason(viewer, ACTION_RUN)


# --- 스펙 표시 -------------------------------------------------------------


def test_display_name_maps_templates_and_falls_back():
    """식별자는 그대로 두고 화면 표시 이름만 분리한다 (Phase 8 단계 2 보완)."""
    from ui.state import display_name

    assert display_name("data_analysis_team") == "데이터 분석 팀"
    assert display_name("research_team") == "리서치 팀"
    assert display_name("doc_qa_team") == "문서 Q&A 팀"
    # 매핑 없는 이름은 밑줄을 공백으로
    assert display_name("it_news_summarizer") == "it news summarizer"


def test_with_object_josa_follows_final_consonant():
    """받침이 있으면 '을', 없으면 '를' — 표시 이름 성공 메시지용 (단계 2 보완)."""
    from ui.state import with_object_josa

    assert with_object_josa("리서치 팀") == "리서치 팀을"
    assert with_object_josa("문서 Q&A 팀") == "문서 Q&A 팀을"
    assert with_object_josa("에이전트") == "에이전트를"
    # 한글로 끝나지 않으면 판정 불가 — 병기한다
    assert with_object_josa("summarizer") == "summarizer을(를)"


def test_team_rows_show_placeholder_for_toolless_member():
    """도구 없는 팀원은 빈 칸이 아니라 '(없음)'으로 보인다."""
    spec = _spec(
        subagents=[
            {
                "name": "writer",
                "description": "글 작성",
                "system_prompt": f"써라. {GUARDRAIL_SENTENCE}",
                "tools": [],
            }
        ]
    )

    assert team_rows(spec)[0]["tools"] == ["(없음)"]


def test_spec_overview_flattens_fields():
    overview = spec_overview(_spec())

    assert overview["name"] == "news_agent"
    assert overview["tools"] == "web_search"
    assert overview["subagents"] == "(none)"


def test_team_rows_empty_for_solo_agent():
    assert team_rows(_spec()) == []


def test_team_rows_list_members():
    spec = _spec(
        subagents=[
            {
                "name": "researcher",
                "description": "조사",
                "system_prompt": f"조사하라. {GUARDRAIL_SENTENCE}",
                "tools": ["web_search"],
            }
        ]
    )

    rows = team_rows(spec)

    assert rows[0]["name"] == "researcher"
    # Phase 8: ListColumn(배지 표시)용으로 문자열이 아니라 목록을 준다
    assert rows[0]["tools"] == ["web_search"]


# --- 명세 버전 이력 (Phase 8 단계 3) -----------------------------------------


def test_spec_version_counts_history_files(tmp_path):
    """버전 번호는 이력 파일 개수다 — 스키마 필드를 추가하지 않는다."""
    from ui.state import spec_version

    assert spec_version("ghost", directory=tmp_path) == 0

    history = tmp_path / "my_agent"
    history.mkdir()
    (history / "v1.json").write_text("{}", encoding="utf-8")
    (history / "v2.json").write_text("{}", encoding="utf-8")

    assert spec_version("my_agent", directory=tmp_path) == 2


def test_version_label_first_save_and_increment():
    from ui.state import version_label

    assert version_label(0) == "v1"
    assert version_label(2) == "v2 → v3"


def test_diff_as_diff_text_uses_plus_minus_prefixes():
    """st.code(language="diff")가 색을 입히려면 +/−가 줄 머리에 와야 한다.

    format_diff는 들여쓴 `~`/`+ 도구` 형식이라 diff 문법과 맞지 않는다 —
    SpecDiff에서 직접 diff 텍스트를 만든다 (UI_REDESIGN 단계 3).
    """
    from runtime.spec_diff import FieldChange, MemberChange, SpecDiff
    from ui.state import diff_as_diff_text

    diff = SpecDiff(
        fields=[FieldChange("description", "3줄 요약", "5줄 요약")],
        tools_added=["file_write"],
        tools_removed=["python_repl"],
        members_added=["writer"],
        members_changed=[
            MemberChange(
                "researcher",
                fields=[FieldChange("system_prompt", "(292자)", "(414자)")],
                tools_added=["web_search"],
            )
        ],
    )

    lines = diff_as_diff_text(diff).splitlines()

    assert "- description: 3줄 요약" in lines
    assert "+ description: 5줄 요약" in lines
    assert "+ 도구 file_write" in lines
    assert "- 도구 python_repl" in lines
    assert "+ 팀원 writer" in lines
    # 팀원 변경은 문맥 줄(공백 접두) 아래에 +/− 상세가 붙는다
    assert "  팀원 researcher" in lines
    assert "-   system_prompt: (292자)" in lines
    assert "+   system_prompt: (414자)" in lines
    assert "+   도구 web_search" in lines


# --- 스트리밍 실행 (Phase 8 단계 7) ------------------------------------------


def _ns(uuid: str) -> tuple:
    return (f"tools:{uuid}",)


def _stream_events():
    """실측 형태 그대로의 이벤트 대본 — 위임 1회(내부 echo 1회) + 리더 최종 답.

    (ns, mode, chunk) 3튜플, updates chunk는 {노드: {"messages": [...]}} 형태.
    미들웨어 노드 이벤트도 섞어 필터를 검증한다 (주의사항 ③).
    """
    task_call = FakeMessage(
        "ai",
        "",
        tool_calls=[
            {
                "name": "task",
                "args": {"subagent_type": "researcher", "description": "뉴스 수집"},
                "id": "call_t1",
            }
        ],
    )
    inner_call = FakeMessage(
        "ai",
        "",
        tool_calls=[{"name": "echo", "args": {"text": "안녕"}, "id": "call_e1"}],
    )
    inner_result = FakeMessage("tool", "echo:안녕", tool_call_id="call_e1")
    task_result = FakeMessage("tool", "수집 완료", tool_call_id="call_t1")
    final = FakeMessage("ai", "최종 보고입니다")
    ns1 = _ns("aaaa")
    return [
        ((), "updates", {"PatchToolCallsMiddleware.before_agent": None}),
        ((), "updates", {"model": {"messages": [task_call]}}),
        (ns1, "updates", {"PatchToolCallsMiddleware.before_agent": None}),
        (ns1, "updates", {"model": {"messages": [inner_call]}}),
        (ns1, "updates", {"tools": {"messages": [inner_result]}}),
        ((), "updates", {"tools": {"messages": [task_result]}}),
        ((), "updates", {"model": {"messages": [final]}}),
        ((), "values", {"messages": [task_call, task_result, final]}),
    ]


class FakeStreamAgent:
    def __init__(self, events, invoke_messages=None, fail_after=None):
        self._events = events
        self._invoke_messages = invoke_messages or []
        self._fail_after = fail_after
        self.invoke_calls = 0  # 재실행 여부를 호출 횟수로 검증한다

    def stream(self, _payload, subgraphs=False, stream_mode=None):
        for index, event in enumerate(self._events):
            if self._fail_after is not None and index >= self._fail_after:
                raise RuntimeError("스트림 끊김")
            yield event

    def invoke(self, _payload):
        self.invoke_calls += 1
        return {"messages": self._invoke_messages}


def test_stream_agent_reply_collects_delegation_and_inner_steps():
    """위임·내부 도구가 순서대로 수집되고, 내부 단계는 depth=1 + 소요시간이 붙는다."""
    from ui.state import stream_agent_reply

    agent = FakeStreamAgent(_stream_events())

    history, reply, steps, streamed = stream_agent_reply(agent, [])

    assert streamed is True
    assert reply == "최종 보고입니다"
    assert len(history) == 3  # values 마지막 상태 그대로
    assert [(s.kind, s.name, s.depth) for s in steps] == [
        ("delegate", "researcher", 0),
        ("tool", "echo", 1),
    ]
    assert "뉴스 수집" in steps[0].args_summary
    assert steps[0].result_summary == "수집 완료"
    assert steps[0].duration is not None and steps[0].duration >= 0
    assert steps[1].result_summary == "echo:안녕"
    assert steps[1].duration is not None


def test_stream_agent_reply_filters_middleware_nodes():
    """model·tools 외 노드(미들웨어)는 단계로 잡히지 않는다 (주의사항 ③)."""
    from ui.state import stream_agent_reply

    agent = FakeStreamAgent(_stream_events())

    _, _, steps, _ = stream_agent_reply(agent, [])

    assert all(s.name in {"researcher", "echo"} for s in steps)


def test_stream_agent_reply_maps_namespaces_in_call_order():
    """병렬 위임 시 네임스페이스는 호출 순서로 배정된다 (주의사항 ①)."""
    from ui.state import stream_agent_reply

    call_a = FakeMessage(
        "ai",
        "",
        tool_calls=[
            {"name": "task", "args": {"subagent_type": "a", "description": "일"}, "id": "t_a"},
            {"name": "task", "args": {"subagent_type": "b", "description": "이"}, "id": "t_b"},
        ],
    )
    inner_a = FakeMessage(
        "ai", "", tool_calls=[{"name": "calc_a", "args": {}, "id": "i_a"}]
    )
    inner_b = FakeMessage(
        "ai", "", tool_calls=[{"name": "calc_b", "args": {}, "id": "i_b"}]
    )
    final = FakeMessage("ai", "끝")
    events = [
        ((), "updates", {"model": {"messages": [call_a]}}),
        (_ns("na"), "updates", {"model": {"messages": [inner_a]}}),
        (_ns("nb"), "updates", {"model": {"messages": [inner_b]}}),
        ((), "updates", {"model": {"messages": [final]}}),
        ((), "values", {"messages": [final]}),
    ]

    _, _, steps, _ = stream_agent_reply(FakeStreamAgent(events), [])

    # a 위임 블록 뒤에 a 내부, b 위임 블록 뒤에 b 내부
    assert [(s.kind, s.name) for s in steps] == [
        ("delegate", "a"),
        ("tool", "calc_a"),
        ("delegate", "b"),
        ("tool", "calc_b"),
    ]


def test_stream_agent_reply_falls_back_when_stream_is_missing():
    """stream이 없는 에이전트는 기존 invoke 경로로 폴백한다."""
    from ui.state import stream_agent_reply

    agent = FakeAgent([FakeMessage("ai", "인보크 응답")])

    history, reply, steps, streamed = stream_agent_reply(agent, [])

    assert streamed is False
    assert reply == "인보크 응답"
    assert steps == []


def test_stream_agent_reply_falls_back_before_first_event_only():
    """첫 이벤트 수신 전 실패는 아무것도 실행되지 않았으므로 invoke 폴백이 안전하다."""
    from ui.state import stream_agent_reply

    agent = FakeStreamAgent(
        _stream_events(),
        invoke_messages=[FakeMessage("ai", "폴백 응답")],
        fail_after=0,  # 첫 이벤트를 내기 전에 죽는다
    )

    _, reply, steps, streamed = stream_agent_reply(agent, [])

    assert streamed is False
    assert reply == "폴백 응답"
    assert steps == []
    assert agent.invoke_calls == 1


def test_stream_agent_reply_does_not_rerun_after_first_event():
    """이벤트가 도착한 뒤의 실패는 재실행하지 않는다 — 도구가 이미 실행됐을 수 있다.

    invoke로 다시 돌리면 file_write·web_search·위임이 중복 실행된다.
    지금까지 수집한 단계와 함께 오류로 보고한다.
    """
    from ui.state import stream_agent_reply

    agent = FakeStreamAgent(
        _stream_events(),
        invoke_messages=[FakeMessage("ai", "재실행되면 안 되는 응답")],
        fail_after=2,  # 위임 단계(이벤트 2개)까지 나간 뒤 죽는다
    )

    history, reply, steps, streamed = stream_agent_reply(agent, ["원래 이력"])

    assert agent.invoke_calls == 0, "이벤트 수신 후에는 invoke로 재실행하면 안 된다"
    assert streamed is True
    assert reply.startswith("[error]")
    assert [s.kind for s in steps] == ["delegate"]  # 그때까지의 단계는 남긴다
    assert history == ["원래 이력"]  # 이력은 원본 그대로


def test_stream_agent_reply_missing_final_values_is_not_rerun():
    """루트 values 미수신도 이벤트 수신 후 실패다 — 재실행 없이 오류로 보고 (주의사항 ②)."""
    from ui.state import stream_agent_reply

    events = [e for e in _stream_events() if e[1] != "values"]
    agent = FakeStreamAgent(events, invoke_messages=[FakeMessage("ai", "금지")])

    _, reply, steps, streamed = stream_agent_reply(agent, [])

    assert agent.invoke_calls == 0
    assert streamed is True
    assert reply.startswith("[error]")
    assert steps, "그때까지 수집한 단계가 남아야 한다"


# --- 평가 대시보드 (Phase 8 단계 5) ------------------------------------------


def _case_result(case_id="c01", passed_checks=(True, True), error=None, score=None):
    from eval.checks import CheckResult
    from eval.judge import JudgeVerdict
    from eval.runner import CaseResult

    names = ["expected_tools", "team_shape"]
    checks = [
        CheckResult(name=names[i], passed=ok, detail="")
        for i, ok in enumerate(passed_checks)
    ]
    verdict = JudgeVerdict(score=score, reason="") if score is not None else None
    return CaseResult(
        case_id=case_id,
        request="요구",
        checks=[] if error else checks,
        verdict=verdict,
        error=error,
    )


def test_check_pass_rates_aggregates_by_check_name():
    """검사 이름별 (통과 수, 전체 수) — 표시 순서는 실제 검사 5종 순서다."""
    from eval.runner import EvalReport
    from ui.state import check_pass_rates

    report = EvalReport(
        results=[
            _case_result("c01", (True, True)),
            _case_result("c02", (False, True)),
        ]
    )

    rates = check_pass_rates(report)

    assert rates[0] == ("expected_tools", 1, 2)
    assert rates[1] == ("team_shape", 2, 2)


def test_check_pass_rates_skips_errored_cases():
    """생성 실패로 checks가 빈 케이스는 분모에 넣지 않는다."""
    from eval.runner import EvalReport
    from ui.state import check_pass_rates

    report = EvalReport(
        results=[
            _case_result("c01", (True, True)),
            _case_result("c02", error="생성 실패"),
        ]
    )

    assert check_pass_rates(report) == [
        ("expected_tools", 1, 1),
        ("team_shape", 1, 1),
    ]


def test_check_pass_rates_empty_report():
    from eval.runner import EvalReport
    from ui.state import check_pass_rates

    assert check_pass_rates(EvalReport(results=[])) == []


def test_check_label_covers_all_five_checks():
    """화면 라벨은 실제 검사 5종을 전부 안다 — 모르는 이름은 그대로 보여준다."""
    from ui.state import check_label

    for name in (
        "expected_tools",
        "forbidden_tools",
        "team_shape",
        "subagent_tools",
        "guardrail",
    ):
        assert check_label(name) != name  # 한글 라벨이 있다
    assert check_label("unknown_check") == "unknown_check"


def test_failed_first_puts_failures_before_passes():
    """케이스별 상세는 실패 먼저 — 안정 정렬이라 같은 그룹은 원래 순서다."""
    from ui.state import failed_first

    ok1 = _case_result("c01", (True, True))
    bad = _case_result("c02", (False, True))
    ok2 = _case_result("c03", (True, True))

    ordered = failed_first([ok1, bad, ok2])

    assert [r.case_id for r in ordered] == ["c02", "c01", "c03"]


def test_case_title_truncates_long_requests():
    """expander 제목은 id + 요구 앞 40자 — 길어도 한 줄이다. 전체는 안쪽에 보인다."""
    from ui.state import case_title

    short = case_title("c01", "짧은 요구")
    long = case_title("c04", "가" * 50)

    assert short == "c01 · 짧은 요구"
    assert long == f"c04 · {'가' * 39}…"
    assert len(long) <= len("c04 · ") + 40


def test_format_duration_minutes_and_seconds():
    from ui.state import format_duration

    assert format_duration(48.2) == "48초"
    assert format_duration(108.0) == "1분 48초"


# --- 대화 상태 -------------------------------------------------------------


def test_append_turn_does_not_mutate_history():
    """Streamlit은 매 실행마다 상태를 다시 읽는다. 제자리 변경은 버그가 된다."""
    original: list = []

    updated = append_turn(original, "안녕")

    assert original == []
    assert updated == [{"role": "user", "content": "안녕"}]


def test_agent_reply_returns_text():
    agent = FakeAgent([FakeMessage("ai", "안녕하세요")])

    history, reply = agent_reply(agent, [])

    assert reply == "안녕하세요"
    assert len(history) == 1


def test_agent_failure_becomes_a_message_not_an_exception():
    agent = FakeAgent(error=RuntimeError("모델 오류"))

    history, reply = agent_reply(agent, [{"role": "user", "content": "안녕"}])

    assert reply.startswith("[error]")
    assert "모델 오류" in reply
    assert history == [{"role": "user", "content": "안녕"}]


def test_render_history_handles_dicts_and_messages():
    history = [
        {"role": "user", "content": "안녕"},
        FakeMessage("ai", "반갑습니다"),
    ]

    assert render_history(history) == [
        ("user", "안녕"),
        ("assistant", "반갑습니다"),
    ]


def test_render_history_skips_tool_only_turns():
    """도구만 호출하고 텍스트가 없는 턴은 화면에 띄우지 않는다."""
    history = [
        FakeMessage("ai", [{"type": "tool_use", "name": "web_search"}]),
        FakeMessage("tool", "검색 결과"),
        FakeMessage("ai", [{"type": "text", "text": "찾았습니다"}]),
    ]

    assert render_history(history) == [("assistant", "찾았습니다")]


def test_render_history_reads_human_messages():
    """human 메시지도 텍스트가 나와야 한다 (ai 전용 추출을 쓰면 깨진다)."""
    assert render_history([FakeMessage("human", "질문입니다")]) == [
        ("user", "질문입니다")
    ]


# --- 위임·도구 호출 단계 (Phase 8 단계 4) ------------------------------------


def _delegation_turn():
    """위임 1회 + 리더 도구 호출 1회 + 최종 응답으로 이루어진 한 턴."""
    return [
        FakeMessage(
            "ai",
            "",
            tool_calls=[
                {
                    "name": "task",
                    "args": {
                        "subagent_type": "researcher",
                        "description": "최신 IT 뉴스 수집",
                    },
                    "id": "c1",
                }
            ],
        ),
        FakeMessage("tool", "기사 8건 수집", tool_call_id="c1"),
        FakeMessage(
            "ai",
            "",
            tool_calls=[
                {"name": "file_write", "args": {"path": "/out.md"}, "id": "c2"}
            ],
        ),
        FakeMessage("tool", "저장됨", tool_call_id="c2"),
        FakeMessage("ai", "요약을 저장했습니다."),
    ]


def test_extract_steps_reads_delegation_and_tool_calls():
    """`task` 호출은 위임(subagent_type·description), 나머지는 일반 도구다.

    인자명은 설치본 deepagents 0.7.5 middleware/subagents.py의
    TaskToolSchema(description, subagent_type)로 확인했다.
    """
    from ui.state import extract_steps

    steps = extract_steps(_delegation_turn())

    assert steps[0][0] == "delegate"
    assert steps[0][1] == "researcher"
    assert "뉴스 수집" in steps[0][2]
    assert "8건" in steps[0][3]
    assert steps[1][0] == "tool"
    assert steps[1][1] == "file_write"
    assert "/out.md" in steps[1][2]
    assert steps[1][3] == "저장됨"


def test_extract_steps_tool_only_history():
    """위임 없이 도구만 부른 턴도 단계로 나온다."""
    from ui.state import extract_steps

    steps = extract_steps(
        [
            FakeMessage(
                "ai",
                "",
                tool_calls=[{"name": "calculate", "args": {"expr": "1+1"}, "id": "x"}],
            ),
            FakeMessage("tool", "2", tool_call_id="x"),
        ]
    )

    assert steps == [("tool", "calculate", "expr='1+1'", "2")]


def test_extract_steps_text_only_history_is_empty():
    from ui.state import extract_steps

    assert extract_steps([FakeMessage("ai", "안녕하세요")]) == []


def test_render_turns_attaches_steps_to_final_reply():
    """단계는 그 턴의 마지막 응답에 붙는다 — 응답 위에 st.status로 그려진다."""
    from ui.state import render_turns

    history = [{"role": "user", "content": "IT 뉴스 요약해줘"}, *_delegation_turn()]

    turns = render_turns(history)

    assert turns[0] == ("user", "IT 뉴스 요약해줘", [])
    role, text, steps = turns[1]
    assert (role, text) == ("assistant", "요약을 저장했습니다.")
    assert len(steps) == 2


def test_render_turns_keeps_tool_only_turn():
    """텍스트 없이 도구만 호출한 턴도 단계가 있으면 버리지 않는다.

    기존 render_history는 이 턴을 통째로 버렸다 (단계 4의 출발점).
    """
    from ui.state import render_turns

    history = [
        FakeMessage(
            "ai",
            "",
            tool_calls=[{"name": "web_search", "args": {"query": "IT"}, "id": "c"}],
        ),
        FakeMessage("tool", "결과 8건", tool_call_id="c"),
    ]

    turns = render_turns(history)

    assert len(turns) == 1
    role, text, steps = turns[0]
    assert role == "assistant" and text == ""
    assert steps == [("tool", "web_search", "query='IT'", "결과 8건")]


# --- 앱 렌더링 -------------------------------------------------------------


def demo_mode_apptest(AppTest, timeout: int = 60):
    """개발자 로컬 `.streamlit/secrets.toml`(OIDC 설정)에 오염되지 않는 AppTest.

    AppTest는 secrets가 **비어 있으면** 실제 secrets 파일을 그대로 읽는다
    (설치본 streamlit/testing/v1/app_test.py의 `if self.secrets:` 분기 실측).
    Phase 7 실측 후 실제 secrets.toml이 생기자 UI 테스트 전건이 OIDC 로그인
    게이트를 렌더링하며 깨졌다 — 비어 있지 않은 더미를 넣어 st.secrets를
    대체시키면 [auth]가 없으므로 앱은 데모 모드로 뜬다.
    """
    app = AppTest.from_file(str(APP_PATH), default_timeout=timeout)
    app.secrets["_isolated_from_local_secrets"] = True
    return app


@pytest.mark.integration
def test_streamlit_app_renders_without_exceptions(monkeypatch):
    """`streamlit run ui/app.py`가 실제로 뜨는지 확인한다.

    state.py 단위 테스트가 전부 통과해도 app.py의 위젯 호출이 깨져 있으면
    앱은 열리지 않는다. 느려서 integration 마커로 분리한다.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = demo_mode_apptest(AppTest).run()

    assert not app.exception, [e.value for e in app.exception]
    assert app.title[0].value == "deep_builder_agent"
    assert len(app.tabs) == 2  # 빌더 / 평가


@pytest.mark.integration
def test_loading_a_template_opens_the_chat_panel(monkeypatch):
    """템플릿을 불러오면 대화 패널이 떠야 한다.

    다른 렌더링 테스트는 **키 없는 차단 상태**만 덮는다 — 그 경로에서는
    agent가 None이라 `render_chat_panel`이 조기 반환하고, 컬럼 안의
    `st.chat_input`은 한 번도 실행되지 않는다. 사용자가 실제로 밟는 경로다.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    pytest.importorskip("deepagents")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    app = demo_mode_apptest(AppTest, timeout=90).run()
    # AppTest는 본문 요소를 사이드바보다 먼저 인덱싱한다 —
    # selectbox[0]이 템플릿, 사이드바 IAM 주체는 app.sidebar.selectbox[0]이다.
    app.selectbox[0].set_value("data_analysis_team").run()
    loaded = [b for b in app.button if "불러오기" in b.label][0].click().run()

    assert not loaded.exception, [e.value for e in loaded.exception]
    assert loaded.chat_input, "대화 입력창이 렌더링되지 않았다"
    # Phase 8: 성공 메시지는 식별자가 아니라 표시 이름 + 을/를 조사다
    assert any("데이터 분석 팀을" in s.value for s in loaded.success)


@pytest.mark.integration
def test_revision_form_appears_once_a_spec_is_active(monkeypatch):
    """명세를 올린 뒤에야 수정 폼이 뜬다 — 고칠 대상이 없으면 의미가 없다.

    LLM은 호출하지 않는다. 폼이 실제로 렌더링되는지만 본다 —
    `render_revision_form`이 호출되지 않으면 CLI에만 있는 기능이 된다.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    pytest.importorskip("deepagents")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    app = demo_mode_apptest(AppTest, timeout=90).run()
    before = [b for b in app.button if "수정" in b.label]
    assert not before, "명세가 없는데 수정 폼이 떠 있다"

    app.selectbox[0].set_value("data_analysis_team").run()
    loaded = [b for b in app.button if "불러오기" in b.label][0].click().run()

    assert not loaded.exception, [e.value for e in loaded.exception]
    assert [b for b in loaded.button if "수정" in b.label], "수정 폼이 렌더링되지 않았다"


@pytest.mark.integration
def test_viewer_principal_disables_creation_in_the_ui(monkeypatch, tmp_path):
    """viewer를 고르면 생성이 비활성화되고 그 이유가 화면에 보인다 (Phase 6).

    위젯 비활성은 UX이고 강제는 authorize_action이 맡지만, 사용자가 '왜 안
    되는지'를 화면에서 알 수 없으면 그것대로 결함이다.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")
    monkeypatch.setenv("DEEP_BUILDER_AUDIT_LOG", str(tmp_path / "audit.jsonl"))

    app = demo_mode_apptest(AppTest).run()
    app.sidebar.selectbox[0].set_value("demo_viewer").run()

    assert not app.exception, [e.value for e in app.exception]
    # Phase 8: 사유는 st.info가 아니라 비활성 버튼 옆 caption 한 줄이다 (시안 5a).
    captions = [c.value for c in app.caption]
    assert any("생성할 수 없습니다" in m for m in captions), captions


def test_principal_names_puts_the_default_first():
    """selectbox 기본 선택(첫 항목)이 admin이어야 CLI와 기본 동작이 같다."""
    from ui.state import load_iam_config, principal_names

    names = principal_names(load_iam_config())
    assert names[0] == "admin"
    assert set(names) == {"admin", "demo_builder", "demo_operator", "demo_viewer"}


# --- OIDC 헬퍼 (Phase 7) -----------------------------------------------------


def test_oidc_configured_requires_a_client_id():
    from ui.state import oidc_configured

    assert not oidc_configured({})
    assert not oidc_configured({"auth": {}})
    assert oidc_configured({"auth": {"client_id": "abc"}})


def test_oidc_configured_treats_missing_secrets_file_as_demo_mode():
    """secrets.toml이 없는 클린 클론에서 앱이 죽으면 안 된다 — 데모 모드다."""
    from ui.state import oidc_configured

    class NoSecretsFile:
        def get(self, key):
            raise FileNotFoundError("No secrets files found")

    assert not oidc_configured(NoSecretsFile())


def test_user_identity_normalizes_missing_and_scalar_groups():
    from ui.state import user_identity

    assert user_identity({"email": "a@b.c", "groups": ["g1", "g2"]}) == (
        "a@b.c",
        ["g1", "g2"],
    )
    assert user_identity({"email": "a@b.c"}) == ("a@b.c", [])
    # IdP에 따라 그룹이 문자열 하나로 올 수 있다
    assert user_identity({"email": "a@b.c", "groups": "solo"}) == ("a@b.c", ["solo"])
    assert user_identity({}) == ("", [])


@pytest.mark.integration
def test_oidc_gate_renders_login_card(monkeypatch):
    """[auth]가 설정되면 로그인 카드가 뜨고 앱 본문은 그리지 않는다 (단계 6).

    게이트 흐름(st.stop 위치)은 Phase 7 그대로고 화면만 카드형이다.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    app = AppTest.from_file(str(APP_PATH), default_timeout=60)
    app.secrets["auth"] = {"client_id": "synthetic-client"}
    app.run()

    assert not app.exception, [e.value for e in app.exception]
    assert [b for b in app.button if "Okta로 로그인" in b.label], [
        b.label for b in app.button
    ]
    assert not app.chat_input, "게이트가 본문을 막지 못했다"


@pytest.mark.integration
def test_app_blocks_execution_without_api_key(monkeypatch):
    """키가 없으면 실행을 막고 그 사실을 화면에 알려야 한다.

    앱은 시작 시 `.env`를 로드하므로, 개발자 머신의 실제 키가 새어 들어오지
    않도록 로더를 no-op으로 막는다. 이 격리가 없으면 테스트가 환경에 따라
    통과했다 실패했다 한다.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

    monkeypatch.setattr("runtime.config.load_env", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = demo_mode_apptest(AppTest).run()

    messages = [e.value for e in app.sidebar.error]
    assert any("ANTHROPIC_API_KEY" in m for m in messages), messages
