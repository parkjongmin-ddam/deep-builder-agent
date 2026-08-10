"""팀 템플릿 검증 — 배포하는 템플릿이 실제로 로드·검증·기동되는지 확인한다.

템플릿은 Builder를 거치지 않고 `cli.py --spec`으로 바로 들어온다. 즉
`ensure_guardrail()`의 자동 주입을 받지 못한다 — 가드레일 문장이 파일에
직접 적혀 있어야 하고, 그것을 여기서 강제한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from builder.prompts import GUARDRAIL_SENTENCE
from runtime.factory import resolve_subagents
from runtime.spec import AgentSpec

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
TEMPLATE_PATHS = sorted(TEMPLATES_DIR.glob("*.json"))


def _load(path: Path) -> AgentSpec:
    return AgentSpec(**json.loads(path.read_text(encoding="utf-8")))


def test_templates_directory_is_not_empty():
    """템플릿이 사라지면 이 테스트가 먼저 알려준다."""
    assert TEMPLATE_PATHS, f"{TEMPLATES_DIR} 에 템플릿이 없다"


@pytest.mark.parametrize("path", TEMPLATE_PATHS, ids=lambda p: p.stem)
def test_template_passes_spec_validation(path: Path):
    """배포하는 템플릿은 그대로 로드돼야 한다."""
    spec = _load(path)

    assert spec.name == path.stem


@pytest.mark.parametrize("path", TEMPLATE_PATHS, ids=lambda p: p.stem)
def test_template_declares_a_team(path: Path):
    """팀 템플릿인데 팀이 없으면 템플릿이 아니다."""
    spec = _load(path)

    assert spec.subagents, "subagents가 비어 있다"


@pytest.mark.parametrize("path", TEMPLATE_PATHS, ids=lambda p: p.stem)
def test_every_prompt_carries_the_guardrail(path: Path):
    """리더와 팀원 전원의 프롬프트에 가드레일 문장이 있어야 한다.

    템플릿은 Builder를 거치지 않으므로 자동 주입을 기대할 수 없다.
    """
    spec = _load(path)

    missing = [
        sub.name for sub in spec.subagents if GUARDRAIL_SENTENCE not in sub.system_prompt
    ]
    assert GUARDRAIL_SENTENCE in spec.system_prompt, "리더 프롬프트에 가드레일이 없다"
    assert not missing, f"가드레일 없는 팀원: {missing}"


@pytest.mark.parametrize("path", TEMPLATE_PATHS, ids=lambda p: p.stem)
def test_leader_prompt_mentions_every_member(path: Path):
    """리더가 팀원 이름을 모르면 위임할 수 없다."""
    spec = _load(path)

    unmentioned = [
        sub.name for sub in spec.subagents if sub.name not in spec.system_prompt
    ]
    assert not unmentioned, f"리더 프롬프트가 언급하지 않는 팀원: {unmentioned}"


@pytest.mark.parametrize("path", TEMPLATE_PATHS, ids=lambda p: p.stem)
def test_template_subagents_resolve_to_tools(path: Path):
    """템플릿이 참조한 도구가 실제 구현으로 해석된다."""
    spec = _load(path)

    payloads = resolve_subagents(spec)

    assert len(payloads) == len(spec.subagents)


@pytest.mark.parametrize("path", TEMPLATE_PATHS, ids=lambda p: p.stem)
def test_template_builds_a_real_agent(path: Path, monkeypatch):
    """스펙이 통과하는 것과 deepagents가 기동되는 것은 다른 문제다."""
    pytest.importorskip("deepagents")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    from runtime.factory import build_agent

    agent = build_agent(_load(path))

    assert agent is not None
