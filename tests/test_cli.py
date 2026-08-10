"""CLI 계층 테스트 — 스펙 로딩과 응답 추출을 API 호출 없이 검증한다."""

import json

import pytest

from cli import describe, last_text, load_spec, main
from runtime.guardrail import GUARDRAIL_SENTENCE
from runtime.spec import AgentSpec

SPEC_DATA = {
    "spec_version": "0.1",
    "name": "news_summarizer",
    "description": "IT 뉴스 요약 에이전트",
    "system_prompt": "너는 IT 뉴스 요약 에이전트다.",
    "model": "claude-sonnet-4-6",
    "tools": ["python_repl"],
    "subagents": [],
}


class FakeMessage:
    def __init__(self, type_: str, content):
        self.type = type_
        self.content = content


def test_load_spec(tmp_path):
    """파일의 내용이 그대로 스펙이 된다 (가드레일 주입분 제외)."""
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(SPEC_DATA), encoding="utf-8")

    spec = load_spec(path)

    assert spec.name == SPEC_DATA["name"]
    assert spec.tools == SPEC_DATA["tools"]
    assert SPEC_DATA["system_prompt"] in spec.system_prompt


def test_load_spec_injects_the_guardrail(tmp_path):
    """손으로 쓴 스펙도 가드레일을 받는다.

    `ensure_guardrail()`이 Builder 루프 안에만 있던 동안 `--spec` 경로는
    가드레일 문장 없는 스펙을 그대로 통과시켰다. 배포 템플릿은 별도 테스트로
    막아 두었지만 **사용자가 직접 쓴 스펙은 아무도 막지 않았다.**
    """
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(SPEC_DATA), encoding="utf-8")

    assert GUARDRAIL_SENTENCE not in SPEC_DATA["system_prompt"], "픽스처 전제가 깨졌다"
    assert GUARDRAIL_SENTENCE in load_spec(path).system_prompt


def test_load_spec_does_not_duplicate_an_existing_guardrail(tmp_path):
    """이미 있으면 그대로 둔다 — 반복 로드로 문장이 쌓이지 않는다."""
    data = {
        **SPEC_DATA,
        "system_prompt": f"{SPEC_DATA['system_prompt']}\n\n{GUARDRAIL_SENTENCE}",
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    assert load_spec(path).system_prompt.count(GUARDRAIL_SENTENCE) == 1


def test_load_spec_guards_subagents_too(tmp_path):
    """팀원 프롬프트에도 주입된다 — 위임된 팀원만 무방비인 구멍을 막는다."""
    data = {
        **SPEC_DATA,
        "tools": [],
        "subagents": [
            {
                "name": "helper",
                "description": "보조 담당",
                "system_prompt": "너는 보조다.",
                "tools": [],
            }
        ],
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    spec = load_spec(path)

    assert GUARDRAIL_SENTENCE in spec.subagents[0].system_prompt


def test_last_text_picks_final_ai_message():
    messages = [
        FakeMessage("human", "안녕"),
        FakeMessage("ai", "첫 응답"),
        FakeMessage("ai", "마지막 응답"),
    ]
    assert last_text(messages) == "마지막 응답"


def test_last_text_reads_block_content():
    messages = [FakeMessage("ai", [{"type": "text", "text": "블록 응답"}])]
    assert last_text(messages) == "블록 응답"


def test_last_text_skips_empty_ai_turns():
    """도구 호출만 담긴 AI 메시지(content 빈 문자열)는 건너뛴다."""
    messages = [FakeMessage("ai", "실제 답변"), FakeMessage("ai", "")]
    assert last_text(messages) == "실제 답변"


def test_last_text_without_ai_message():
    assert "텍스트 응답을 내지 않았습니다" in last_text([FakeMessage("human", "안녕")])


def test_describe_reports_builtin_tools():
    text = describe(AgentSpec(**SPEC_DATA))
    assert "news_summarizer" in text
    assert "read_file" in text  # 라이브러리가 강제하는 도구를 사용자에게 숨기지 않는다


def test_main_rejects_both_request_and_spec(tmp_path):
    with pytest.raises(SystemExit):
        main(["요구사항", "--spec", str(tmp_path / "x.json")])


def test_main_rejects_neither():
    with pytest.raises(SystemExit):
        main([])


def test_main_no_chat_validates_only(tmp_path, capsys):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(SPEC_DATA), encoding="utf-8")

    assert main(["--spec", str(path), "--no-chat"]) == 0
    assert "news_summarizer" in capsys.readouterr().out
