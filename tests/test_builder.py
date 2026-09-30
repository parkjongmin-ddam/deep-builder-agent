"""Builder 루프 테스트 — LLM 없이 파싱·주입·재시도 하네스를 검증한다.

실제 API 호출 없이 FakeChatModel을 주입해 결정론적으로 돌린다.
"""

import json

import pytest

from builder.builder import (
    SpecGenerationError,
    ensure_guardrail,
    extract_json,
    generate_spec,
    revise_spec,
    save_spec,
)
from builder.prompts import GUARDRAIL_SENTENCE, build_system_prompt, render_tool_list
from registry import allowed_tool_keys
from runtime.spec import AgentSpec

VALID_SPEC = {
    "spec_version": "0.1",
    "name": "news_summarizer",
    "description": "IT 뉴스 수집·요약 에이전트",
    "system_prompt": f"너는 IT 뉴스 요약 에이전트다. {GUARDRAIL_SENTENCE}",
    "model": "claude-sonnet-4-6",
    "tools": ["web_search"],
    "subagents": [],
}


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeChatModel:
    """미리 정해둔 응답을 순서대로 돌려주는 스텁."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list = []

    def invoke(self, messages):
        self.calls.append(messages)
        return FakeResponse(self._responses.pop(0))


# --- 프롬프트 렌더링 (도구 자동 선택) --------------------------------------


def test_prompt_lists_every_registered_tool():
    """프롬프트가 광고하는 도구와 밸리데이터가 허용하는 도구는 어긋날 수 없다."""
    rendered = render_tool_list()
    for key in allowed_tool_keys():
        assert f"`{key}`" in rendered


def test_prompt_includes_guardrail_and_tools():
    prompt = build_system_prompt()
    assert GUARDRAIL_SENTENCE in prompt
    assert "## 사용 가능한 도구" in prompt
    assert "web_search" in prompt


def test_prompt_has_no_unrendered_placeholder():
    assert "{tool_list}" not in build_system_prompt()


# --- extract_json ---------------------------------------------------------


def test_extract_json_plain():
    assert extract_json(json.dumps(VALID_SPEC))["name"] == "news_summarizer"


def test_extract_json_strips_code_fence():
    raw = "```json\n" + json.dumps(VALID_SPEC) + "\n```"
    assert extract_json(raw)["name"] == "news_summarizer"


def test_extract_json_ignores_surrounding_prose():
    raw = f"알겠습니다. 아래가 명세입니다:\n{json.dumps(VALID_SPEC)}\n확인해 주세요."
    assert extract_json(raw)["tools"] == ["web_search"]


def test_extract_json_handles_braces_inside_strings():
    payload = {**VALID_SPEC, "description": "출력 형식은 {a: 1} 처럼 쓴다"}
    assert extract_json(json.dumps(payload))["description"] == "출력 형식은 {a: 1} 처럼 쓴다"


def test_extract_json_without_object_raises():
    with pytest.raises(ValueError, match="no JSON object"):
        extract_json("죄송합니다, 만들 수 없습니다.")


# --- ensure_guardrail -----------------------------------------------------


def test_guardrail_injected_when_missing():
    result = ensure_guardrail({"system_prompt": "너는 요약가다."})
    assert GUARDRAIL_SENTENCE in result["system_prompt"]


def test_guardrail_not_duplicated():
    result = ensure_guardrail({"system_prompt": f"역할. {GUARDRAIL_SENTENCE}"})
    assert result["system_prompt"].count(GUARDRAIL_SENTENCE) == 1


def test_guardrail_does_not_mutate_input():
    original = {"system_prompt": "너는 요약가다."}
    ensure_guardrail(original)
    assert original == {"system_prompt": "너는 요약가다."}


# --- generate_spec --------------------------------------------------------


def test_generate_spec_succeeds_first_try():
    llm = FakeChatModel([json.dumps(VALID_SPEC)])
    spec = generate_spec("IT 뉴스 요약 에이전트", chat_model=llm)
    assert isinstance(spec, AgentSpec)
    assert spec.name == "news_summarizer"
    assert len(llm.calls) == 1


def test_generate_spec_retries_on_unregistered_tool():
    bad = {**VALID_SPEC, "tools": ["shell_exec"]}
    llm = FakeChatModel([json.dumps(bad), json.dumps(VALID_SPEC)])
    spec = generate_spec("...", chat_model=llm)

    assert spec.tools == ["web_search"]
    assert len(llm.calls) == 2
    # 두 번째 호출에 실패 원인이 피드백으로 실려야 한다.
    assert "unregistered tool" in llm.calls[1][-1][1]


def test_generate_spec_injects_guardrail_when_llm_omits_it():
    without = {**VALID_SPEC, "system_prompt": "너는 IT 뉴스 요약 에이전트다."}
    llm = FakeChatModel([json.dumps(without)])
    spec = generate_spec("...", chat_model=llm)
    assert GUARDRAIL_SENTENCE in spec.system_prompt


def test_generate_spec_raises_after_retries_exhausted():
    bad = json.dumps({**VALID_SPEC, "tools": ["shell_exec"]})
    llm = FakeChatModel([bad, bad, bad])
    with pytest.raises(SpecGenerationError):
        generate_spec("...", chat_model=llm, max_retries=2)
    assert len(llm.calls) == 3


def test_generate_spec_reads_block_style_content():
    llm = FakeChatModel([[{"type": "text", "text": json.dumps(VALID_SPEC)}]])
    assert generate_spec("...", chat_model=llm).name == "news_summarizer"


# --- revise_spec ----------------------------------------------------------


def test_revise_spec_applies_the_change():
    before = AgentSpec(**VALID_SPEC)
    revised_json = json.dumps({**VALID_SPEC, "tools": ["web_search", "file_write"]})
    llm = FakeChatModel([revised_json])

    after = revise_spec(before, "결과를 파일로 저장하는 기능도 넣어줘", chat_model=llm)

    assert after.tools == ["web_search", "file_write"]


def test_revise_spec_does_not_mutate_the_original():
    """호출자가 전후를 비교해야 하므로 원본이 살아 있어야 한다."""
    before = AgentSpec(**VALID_SPEC)
    llm = FakeChatModel([json.dumps({**VALID_SPEC, "tools": []})])

    revise_spec(before, "도구 다 빼줘", chat_model=llm)

    assert before.tools == ["web_search"], "원본이 변경됐다"


def test_revise_spec_shows_the_current_spec_to_the_model():
    """지금 명세를 보여주지 않으면 '고치는' 게 아니라 새로 만드는 것이다."""
    before = AgentSpec(**VALID_SPEC)
    llm = FakeChatModel([json.dumps(VALID_SPEC)])

    revise_spec(before, "파일 저장 추가", chat_model=llm)

    user_message = llm.calls[0][-1][1]
    assert "news_summarizer" in user_message, "현재 명세가 전달되지 않았다"
    assert "파일 저장 추가" in user_message, "수정 요구가 전달되지 않았다"


def test_revise_spec_injects_the_guardrail():
    """수정 경로에도 가드레일 보장이 걸린다 — 생성 경로와 같은 하네스를 탄다."""
    before = AgentSpec(**VALID_SPEC)
    stripped = {**VALID_SPEC, "system_prompt": "가드레일 없는 프롬프트"}
    llm = FakeChatModel([json.dumps(stripped)])

    after = revise_spec(before, "프롬프트 바꿔줘", chat_model=llm)

    assert GUARDRAIL_SENTENCE in after.system_prompt


def test_revise_spec_rejects_a_tool_outside_the_whitelist():
    """수정으로 화이트리스트를 우회할 수 없다."""
    before = AgentSpec(**VALID_SPEC)
    bad = json.dumps({**VALID_SPEC, "tools": ["shell_exec"]})
    llm = FakeChatModel([bad, bad, bad])

    with pytest.raises(SpecGenerationError):
        revise_spec(before, "셸 도구 붙여줘", chat_model=llm, max_retries=2)


# --- IAM 권한 경계 (Phase 6) ------------------------------------------------


def test_generate_spec_retries_when_boundary_is_exceeded():
    """경계 밖 도구는 검증 실패와 같은 재시도 피드백을 받는다.

    LLM이 정책을 지키리라 신뢰하지 않는다 — 첫 시도가 python_repl을 요청하면
    에러 피드백을 받고, 두 번째 시도에서 허용 도구로 대체해야 통과한다.
    """
    over = {**VALID_SPEC, "tools": ["python_repl"]}
    llm = FakeChatModel([json.dumps(over), json.dumps(VALID_SPEC)])

    spec = generate_spec("계산 에이전트", chat_model=llm, allowed_tools=["web_search"])

    assert spec.tools == ["web_search"]
    assert len(llm.calls) == 2
    feedback = llm.calls[1][-1][1]
    assert "permissions boundary" in feedback
    assert "python_repl" in feedback, "무엇이 거부됐는지 알려줘야 대체할 수 있다"
    assert "web_search" in feedback, "무엇이 허용되는지 알려줘야 대체할 수 있다"


def test_generate_spec_without_boundary_keeps_old_behavior():
    """allowed_tools=None(기본값)이면 경계 검사가 없다 — 기존 호출자 무영향."""
    over = {**VALID_SPEC, "tools": ["python_repl"]}
    llm = FakeChatModel([json.dumps(over)])
    assert generate_spec("...", chat_model=llm).tools == ["python_repl"]


def test_generate_spec_boundary_covers_subagent_tools():
    """팀원 도구도 경계를 받는다 — 위임이 권한 상승 통로가 되면 안 된다."""
    team = {
        **VALID_SPEC,
        "tools": [],
        "subagents": [
            {
                "name": "coder",
                "description": "코드 실행 담당",
                "system_prompt": "너는 코더다.",
                "tools": ["python_repl"],
            }
        ],
    }
    llm = FakeChatModel([json.dumps(team)] * 3)

    with pytest.raises(SpecGenerationError):
        generate_spec("...", chat_model=llm, allowed_tools=["web_search"], max_retries=2)


def test_revise_spec_enforces_the_same_boundary():
    """수정 경로에만 경계가 빠지면 /revise가 우회로가 된다."""
    before = AgentSpec(**VALID_SPEC)
    over = json.dumps({**VALID_SPEC, "tools": ["web_search", "python_repl"]})
    llm = FakeChatModel([over, over, over])

    with pytest.raises(SpecGenerationError):
        revise_spec(
            before, "코드 실행 붙여줘", chat_model=llm,
            allowed_tools=["web_search"], max_retries=2,
        )


# --- save_spec ------------------------------------------------------------


def test_save_spec_roundtrip(tmp_path):
    spec = AgentSpec(**VALID_SPEC)
    path = save_spec(spec, directory=tmp_path)
    assert path == tmp_path / "news_summarizer.json"
    assert AgentSpec(**json.loads(path.read_text(encoding="utf-8"))) == spec


def test_save_spec_accumulates_version_history(tmp_path):
    """연속 저장이 v1→v2→v3 이력을 쌓고, 최신본 경로는 CLI 호환으로 유지된다 (Phase 8)."""
    spec = AgentSpec(**VALID_SPEC)

    save_spec(spec, directory=tmp_path)
    save_spec(spec.model_copy(update={"description": "2판"}), directory=tmp_path)
    latest = save_spec(
        spec.model_copy(update={"description": "3판"}), directory=tmp_path
    )

    history = sorted(p.name for p in (tmp_path / "news_summarizer").glob("v*.json"))
    assert history == ["v1.json", "v2.json", "v3.json"]
    # 최신본은 기존 경로에 그대로 — cli.py --spec specs/<name>.json 이 계속 돈다
    assert latest == tmp_path / "news_summarizer.json"
    assert "3판" in latest.read_text(encoding="utf-8")


def test_unique_spec_name_appends_numeric_suffix(tmp_path):
    """생성(create)은 기존 명세를 잇지 않는다 — 충돌하면 _2, _3으로 분리 (Phase 8).

    수정(revise)은 같은 이름에 버전을 누적하므로 이 함수를 타지 않는다.
    """
    from builder.builder import unique_spec_name

    # 아무것도 없으면 그대로
    assert unique_spec_name("news_summarizer", directory=tmp_path) == "news_summarizer"

    save_spec(AgentSpec(**VALID_SPEC), directory=tmp_path)
    assert unique_spec_name("news_summarizer", directory=tmp_path) == "news_summarizer_2"

    save_spec(
        AgentSpec(**{**VALID_SPEC, "name": "news_summarizer_2"}), directory=tmp_path
    )
    assert unique_spec_name("news_summarizer", directory=tmp_path) == "news_summarizer_3"


def test_unique_spec_name_treats_history_dir_as_conflict(tmp_path):
    """최신본이 지워졌어도 이력 디렉터리가 남아 있으면 충돌이다 — 이력이 섞이면 안 된다."""
    from builder.builder import unique_spec_name

    (tmp_path / "news_summarizer").mkdir()

    assert unique_spec_name("news_summarizer", directory=tmp_path) == "news_summarizer_2"


def test_save_spec_never_overwrites_history(tmp_path):
    """이력 파일은 불변이다 — v1은 두 번째 저장 후에도 처음 내용 그대로다."""
    spec = AgentSpec(**VALID_SPEC)

    save_spec(spec, directory=tmp_path)
    history_dir = tmp_path / "news_summarizer"
    v1_before = (history_dir / "v1.json").read_text(encoding="utf-8")
    save_spec(spec.model_copy(update={"description": "2판"}), directory=tmp_path)

    assert (history_dir / "v1.json").read_text(encoding="utf-8") == v1_before
    assert "2판" in (history_dir / "v2.json").read_text(encoding="utf-8")
