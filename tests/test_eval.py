"""평가 레이어 테스트 — API 키 없이 파이프라인 전체를 돌린다.

스펙 생성기와 심판을 주입해 결정론적으로 검증한다
(builder.generate_spec의 chat_model 주입과 같은 이유).
"""

import json

import pytest
from pydantic import ValidationError

from builder.prompts import GUARDRAIL_SENTENCE
from eval.checks import run_checks
from eval.dataset import EvalCase, load_cases
from eval.judge import JudgeError, JudgeVerdict, build_judge_prompt, judge_spec
from eval.runner import format_report, run_case, run_evaluation
from runtime.spec import AgentSpec

GUARDED = f"너는 도우미다. {GUARDRAIL_SENTENCE}"


def _case(**over) -> EvalCase:
    d = dict(
        id="news_case",
        request="웹 검색으로 뉴스를 요약해줘",
        expect_tools=["web_search"],
        forbid_tools=["python_repl"],
        expect_team=False,
        rubric="검색과 요약 절차가 있는가",
    )
    d.update(over)
    return EvalCase(**d)


def _spec(**over) -> AgentSpec:
    d = dict(
        name="news_agent",
        description="뉴스 요약",
        system_prompt=GUARDED,
        tools=["web_search"],
    )
    d.update(over)
    return AgentSpec(**d)


# --- 데이터셋 --------------------------------------------------------------


def test_shipped_cases_load():
    """배포하는 케이스 파일이 그대로 검증을 통과해야 한다."""
    cases = load_cases()

    assert cases, "케이스가 비어 있다"
    assert len({c.id for c in cases}) == len(cases)


def test_duplicate_case_ids_rejected(tmp_path):
    path = tmp_path / "dup.json"
    entry = {"id": "same_id", "request": "r", "rubric": "b"}
    path.write_text(json.dumps([entry, entry]), encoding="utf-8")

    with pytest.raises(ValueError, match="중복된 케이스 id"):
        load_cases(path)


def test_case_id_pattern_enforced():
    with pytest.raises(ValidationError):
        _case(id="Bad Id With Spaces")


# --- 기계적 검사 -----------------------------------------------------------


def test_all_checks_pass_for_a_good_spec():
    results = run_checks(_spec(), _case())

    assert all(r.passed for r in results), [r for r in results if not r.passed]


def test_missing_expected_tool_fails():
    results = {r.name: r for r in run_checks(_spec(tools=[]), _case())}

    assert not results["expected_tools"].passed
    assert "web_search" in results["expected_tools"].detail


def test_forbidden_tool_in_subagent_is_caught():
    """팀원에게 몰래 붙은 과잉 도구도 잡아야 한다."""
    spec = _spec(
        subagents=[
            {
                "name": "helper",
                "description": "보조",
                "system_prompt": GUARDED,
                "tools": ["python_repl"],
            }
        ]
    )

    results = {r.name: r for r in run_checks(spec, _case(expect_team=True))}

    assert not results["forbidden_tools"].passed
    assert "python_repl" in results["forbidden_tools"].detail


def test_unnecessary_team_fails_team_shape():
    spec = _spec(
        subagents=[
            {
                "name": "helper",
                "description": "보조",
                "system_prompt": GUARDED,
                "tools": [],
            }
        ]
    )

    results = {r.name: r for r in run_checks(spec, _case(expect_team=False))}

    assert not results["team_shape"].passed


def test_toolless_research_team_is_caught():
    """조사 팀에 아무도 검색 도구가 없으면 실패해야 한다.

    `expect_subagent_tools`가 생기기 전에는 이 상황이 **전부 통과**했다.
    도구는 리더가 아니라 팀원에게 붙으므로 `expect_tools`로는 잡히지 않고,
    팀 케이스들이 `expect_tools=[]`로 적혀 도구에 대해 아무 단언도 하지 않았다.
    """
    spec = _spec(
        tools=[],
        subagents=[
            {
                "name": "researcher",
                "description": "조사 담당",
                "system_prompt": GUARDED,
                "tools": [],
            }
        ],
    )
    case = _case(
        expect_tools=[],
        forbid_tools=[],
        expect_team=True,
        expect_subagent_tools=["web_search"],
    )

    results = {r.name: r for r in run_checks(spec, case)}

    assert not results["subagent_tools"].passed
    assert "web_search" in results["subagent_tools"].detail


def test_subagent_tools_satisfied_by_any_member():
    """어느 팀원이 들고 있는지는 묻지 않는다 — 역할 배분은 Builder 재량이다."""
    spec = _spec(
        tools=[],
        subagents=[
            {
                "name": "searcher",
                "description": "조사 담당",
                "system_prompt": GUARDED,
                "tools": ["web_search"],
            },
            {
                "name": "writer",
                "description": "집필 담당",
                "system_prompt": GUARDED,
                "tools": [],
            },
        ],
    )
    case = _case(
        expect_tools=[],
        forbid_tools=[],
        expect_team=True,
        expect_subagent_tools=["web_search"],
    )

    results = {r.name: r for r in run_checks(spec, case)}

    assert results["subagent_tools"].passed


def test_leader_tools_do_not_satisfy_subagent_expectation():
    """리더가 들고 있어도 팀원 기대를 채우지 못한다 — 위임받는 쪽이 못 쓴다.

    대조군이다. 이게 없으면 `check_subagent_tools`가 리더 도구까지 세는
    구현으로 바뀌어도 위 두 테스트는 그대로 통과한다.
    """
    spec = _spec(
        tools=["web_search"],
        subagents=[
            {
                "name": "writer",
                "description": "집필 담당",
                "system_prompt": GUARDED,
                "tools": [],
            }
        ],
    )
    case = _case(
        expect_tools=[],
        forbid_tools=[],
        expect_team=True,
        expect_subagent_tools=["web_search"],
    )

    results = {r.name: r for r in run_checks(spec, case)}

    assert not results["subagent_tools"].passed


def test_team_cases_declare_the_tools_their_members_need():
    """배포 케이스에서 도구가 필요한 팀 요구는 팀원 도구를 단언해야 한다.

    팀 케이스를 늘릴 때 `expect_subagent_tools`를 빠뜨리면 도구에 대해
    아무것도 확인하지 않는 케이스가 조용히 다시 생긴다. 도구 이름이
    요구문에 드러나는 케이스만 대상으로 한다.
    """
    tool_words = {"web_search": ("웹", "검색", "web", "search")}

    undeclared = [
        case.id
        for case in load_cases()
        if case.expect_team
        and not case.expect_subagent_tools
        and any(w in case.request.lower() for w in tool_words["web_search"])
    ]

    assert not undeclared, f"팀원 도구를 단언하지 않은 팀 케이스: {undeclared}"


def test_missing_guardrail_is_caught():
    results = {
        r.name: r for r in run_checks(_spec(system_prompt="가드레일 없음"), _case())
    }

    assert not results["guardrail"].passed


# --- 심판 ------------------------------------------------------------------


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeJudgeModel:
    def __init__(self, content):
        self._content = content

    def invoke(self, messages):
        return FakeResponse(self._content)


def test_judge_parses_score_and_reason():
    model = FakeJudgeModel('{"score": 5, "reason": "절차가 구체적이다"}')

    verdict = judge_spec(_spec(), _case(), chat_model=model)

    assert verdict.score == 5
    assert verdict.passed


def test_judge_below_threshold_does_not_pass():
    model = FakeJudgeModel('{"score": 3, "reason": "절차가 빠졌다"}')

    assert not judge_spec(_spec(), _case(), chat_model=model).passed


def test_judge_rejects_out_of_range_score():
    model = FakeJudgeModel('{"score": 9, "reason": "이상한 점수"}')

    with pytest.raises(JudgeError, match="범위"):
        judge_spec(_spec(), _case(), chat_model=model)


def test_judge_requires_a_reason():
    """이유 없는 점수는 회귀를 고치는 데 쓸 수 없다."""
    model = FakeJudgeModel('{"score": 5, "reason": ""}')

    with pytest.raises(JudgeError, match="근거"):
        judge_spec(_spec(), _case(), chat_model=model)


def test_judge_reports_unparseable_output():
    model = FakeJudgeModel("점수를 못 매기겠습니다")

    with pytest.raises(JudgeError, match="JSON"):
        judge_spec(_spec(), _case(), chat_model=model)


def test_judge_prompt_carries_request_and_rubric():
    prompt = build_judge_prompt(_spec(), _case())

    assert "웹 검색으로 뉴스를 요약해줘" in prompt
    assert "검색과 요약 절차가 있는가" in prompt


def test_judge_prompt_shows_subagent_tools_and_prompts():
    """심판은 팀원의 도구와 프롬프트까지 봐야 한다.

    예전에는 팀원 **이름만** 넘겼다. 그래서 (1) 팀원 프롬프트가 채점 대상에서
    통째로 빠져 있었고 — 리더보다 빈틈이 생기기 쉬운 쪽인데도 — (2) 도구 배분을
    묻는 rubric에 대해 심판이 보이지 않는 것을 근거로 감점했다.
    """
    spec = _spec(
        tools=[],
        subagents=[
            {
                "name": "searcher",
                "description": "웹 조사 담당",
                "system_prompt": f"너는 조사 담당이다. 출처를 반드시 남긴다. {GUARDRAIL_SENTENCE}",
                "tools": ["web_search"],
            }
        ],
    )

    prompt = build_judge_prompt(spec, _case(expect_team=True))

    assert "searcher" in prompt
    assert "web_search" in prompt, "팀원 도구가 심판에게 보이지 않는다"
    assert "출처를 반드시 남긴다" in prompt, "팀원 프롬프트가 심판에게 보이지 않는다"
    assert "웹 조사 담당" in prompt


def test_judge_prompt_marks_absent_team_explicitly():
    """팀이 없을 때 빈 값이 아니라 (none)으로 보여준다 — 대조군.

    이게 없으면 `_render_subagents`가 항상 빈 문자열을 돌려주는 구현으로 바뀌어도
    위 테스트만 통과하는 상태를 못 잡는다.
    """
    prompt = build_judge_prompt(_spec(), _case())

    assert "(none)" in prompt


# --- 실행 ------------------------------------------------------------------


def test_generation_failure_becomes_a_result_not_an_exception():
    """10개 중 3번째가 죽어서 나머지를 못 보는 것이 최악이다."""

    def broken(_request):
        raise RuntimeError("모델이 죽었다")

    result = run_case(_case(), spec_generator=broken)

    assert not result.passed
    assert "모델이 죽었다" in result.error


def test_repeats_surface_an_intermittent_failure():
    """간헐적 실패는 통과로 뭉개지 않는다.

    Builder는 결정적이지 않다 — 실측에서 같은 케이스가 같은 모델로 한 번은
    단일 에이전트, 한 번은 4인 팀을 냈다. 1회만 돌리고 "통과"라 하면
    **간헐적 실패를 통과로 착각한다.**
    """
    attempts = iter([_spec(), _spec(tools=[]), _spec()])  # 2번째만 도구 누락

    report = run_evaluation([_case()], spec_generator=lambda r: next(attempts), repeats=3)

    assert not report.results[0].passed, "실패한 실행이 통과에 가려졌다"
    assert report.passed == 0


def test_repeats_default_runs_each_case_once():
    """기본값은 1 — 평소 평가 비용이 조용히 늘지 않는다 (대조군)."""
    calls = []

    def generator(request):
        calls.append(request)
        return _spec()

    run_evaluation([_case()], spec_generator=generator)

    assert len(calls) == 1


def test_repeats_all_passing_stays_passing():
    """전부 통과하면 통과다 — 반복이 거짓 실패를 만들지 않는다."""
    report = run_evaluation([_case()], spec_generator=lambda r: _spec(), repeats=3)

    assert report.passed == 1


def test_repeats_below_one_is_rejected():
    """0회 반복은 '전부 통과'로 보이는 무의미한 리포트를 만든다."""
    with pytest.raises(ValueError, match="repeats"):
        run_evaluation([_case()], spec_generator=lambda r: _spec(), repeats=0)


def test_judge_is_skipped_when_checks_fail():
    """도구를 잘못 고른 명세의 문장력을 채점하는 것은 돈 낭비다."""
    calls = []

    def judge(spec, case):
        calls.append(case.id)
        return JudgeVerdict(score=5, reason="ok")

    result = run_case(_case(), spec_generator=lambda r: _spec(tools=[]), judge=judge)

    assert calls == []
    assert result.verdict is None


def test_judge_runs_when_checks_pass():
    result = run_case(
        _case(),
        spec_generator=lambda r: _spec(),
        judge=lambda spec, case: JudgeVerdict(score=5, reason="좋다"),
    )

    assert result.verdict.score == 5
    assert result.passed


def test_report_aggregates_pass_rate_and_mean_score():
    cases = [_case(id="case_one"), _case(id="case_two")]
    scores = iter([5, 3])

    report = run_evaluation(
        cases,
        spec_generator=lambda r: _spec(),
        judge=lambda spec, case: JudgeVerdict(score=next(scores), reason="r"),
    )

    assert report.total == 2
    assert report.passed == 1  # 3점은 임계값 미만
    assert report.mean_score == 4.0


def test_empty_report_does_not_divide_by_zero():
    report = run_evaluation([], spec_generator=lambda r: _spec())

    assert report.pass_rate == 0.0
    assert report.mean_score is None


def test_format_report_names_failed_checks():
    report = run_evaluation([_case()], spec_generator=lambda r: _spec(tools=[]))

    text = format_report(report)

    assert "FAIL" in text
    assert "expected_tools" in text
