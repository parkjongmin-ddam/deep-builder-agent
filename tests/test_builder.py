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


# --- save_spec ------------------------------------------------------------


def test_save_spec_roundtrip(tmp_path):
    spec = AgentSpec(**VALID_SPEC)
    path = save_spec(spec, directory=tmp_path)
    assert path == tmp_path / "news_summarizer.json"
    assert AgentSpec(**json.loads(path.read_text(encoding="utf-8"))) == spec
