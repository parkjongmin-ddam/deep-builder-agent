"""스펙 diff 테스트 — 수정 루프의 신뢰가 여기에 달려 있다.

수정의 주된 실패 모드는 "요청하지 않은 것까지 바뀌는 것"이다. diff가 그것을
놓치면 사용자는 조용한 변경을 알 수 없다. 그러므로 이 테스트의 초점은
"변경을 잡아내는가"이고, **놓치는 경우**를 우선 확인한다.
"""

from __future__ import annotations

from runtime.guardrail import GUARDRAIL_SENTENCE
from runtime.spec import AgentSpec
from runtime.spec_diff import diff_specs, format_diff

GUARDED = f"너는 도우미다. {GUARDRAIL_SENTENCE}"


def _spec(**over) -> AgentSpec:
    data = dict(
        name="news_agent",
        description="뉴스 요약 에이전트",
        system_prompt=GUARDED,
        tools=["web_search"],
    )
    data.update(over)
    return AgentSpec(**data)


def _member(name="researcher", **over) -> dict:
    data = dict(
        name=name,
        description="조사 담당",
        system_prompt=GUARDED,
        tools=["web_search"],
    )
    data.update(over)
    return data


# --- 변경 없음 --------------------------------------------------------------


def test_identical_specs_have_no_diff():
    diff = diff_specs(_spec(), _spec())

    assert diff.is_empty
    assert "변경 없음" in format_diff(diff)


# --- 도구 -------------------------------------------------------------------


def test_added_tool_is_reported():
    diff = diff_specs(_spec(), _spec(tools=["web_search", "file_write"]))

    assert diff.tools_added == ["file_write"]
    assert diff.tools_removed == []
    assert "+ 도구 file_write" in format_diff(diff)


def test_removed_tool_is_reported():
    diff = diff_specs(_spec(), _spec(tools=[]))

    assert diff.tools_removed == ["web_search"]
    assert "- 도구 web_search" in format_diff(diff)


# --- 조용한 변경 잡기 (이 diff의 존재 이유) ---------------------------------


def test_unrequested_prompt_edit_is_visible():
    """도구만 바꿔달라고 했는데 프롬프트도 다듬어진 경우를 보여줘야 한다.

    이게 안 잡히면 사용자는 자기가 쓴 문장이 바뀐 줄 모른다.
    """
    after = _spec(
        tools=["web_search", "file_write"],
        system_prompt=GUARDED + " 항상 정중하게 답한다.",
    )

    diff = diff_specs(_spec(), after)

    assert any(c.name == "system_prompt" for c in diff.fields), (
        "프롬프트가 조용히 바뀌었는데 diff가 놓쳤다"
    )


def test_unrequested_description_change_is_visible():
    diff = diff_specs(_spec(), _spec(description="완전히 다른 설명"))

    assert "description" in {c.name for c in diff.fields}


def test_model_change_is_visible():
    diff = diff_specs(_spec(), _spec(model="claude-haiku-4-5"))

    assert any(c.name == "model" for c in diff.fields)


# --- 팀원 -------------------------------------------------------------------


def test_added_member_is_reported():
    diff = diff_specs(_spec(), _spec(tools=[], subagents=[_member()]))

    assert diff.members_added == ["researcher"]
    assert "+ 팀원 researcher" in format_diff(diff)


def test_removed_member_is_reported():
    before = _spec(tools=[], subagents=[_member()])

    diff = diff_specs(before, _spec())

    assert diff.members_removed == ["researcher"]


def test_member_tool_change_is_reported():
    before = _spec(tools=[], subagents=[_member()])
    after = _spec(tools=[], subagents=[_member(tools=["web_search", "calculate"])])

    diff = diff_specs(before, after)

    assert [m.name for m in diff.members_changed] == ["researcher"]
    assert diff.members_changed[0].tools_added == ["calculate"]
    assert "      + 도구 calculate" in format_diff(diff)


def test_member_model_change_is_reported():
    before = _spec(tools=[], subagents=[_member()])
    after = _spec(tools=[], subagents=[_member(model="claude-haiku-4-5")])

    diff = diff_specs(before, after)

    assert [c.name for c in diff.members_changed[0].fields] == ["model"]


def test_renamed_member_shows_as_add_and_remove():
    """이름은 리더가 위임에 쓰는 식별자다 — 바뀌면 다른 팀원이다."""
    before = _spec(tools=[], subagents=[_member(name="researcher")])
    after = _spec(tools=[], subagents=[_member(name="investigator")])

    diff = diff_specs(before, after)

    assert diff.members_added == ["investigator"]
    assert diff.members_removed == ["researcher"]


def test_untouched_member_is_not_reported():
    """바뀌지 않은 팀원이 목록에 뜨면 진짜 변경이 묻힌다 (대조군)."""
    before = _spec(
        tools=[], subagents=[_member(name="researcher"), _member(name="writer")]
    )
    after = _spec(
        tools=[],
        subagents=[
            _member(name="researcher", tools=["web_search", "calculate"]),
            _member(name="writer"),
        ],
    )

    diff = diff_specs(before, after)

    assert [m.name for m in diff.members_changed] == ["researcher"]


# --- 표시 형식 --------------------------------------------------------------


def test_long_text_is_summarized_not_dumped():
    """긴 프롬프트 전문을 찍으면 나머지 변경이 묻힌다."""
    long_prompt = GUARDED + "\n" + ("설명 " * 200)

    output = format_diff(diff_specs(_spec(), _spec(system_prompt=long_prompt)))

    assert "설명 설명" not in output, "긴 프롬프트가 그대로 쏟아졌다"
    assert "자" in output, "길이 정보가 보이지 않는다"
