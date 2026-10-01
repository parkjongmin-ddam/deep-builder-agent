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
def test_template_descriptions_mention_only_granted_tools(path: Path):
    """설명이 그 팀원에게 없는 도구를 말하면 안 된다 (Phase 8에서 실측된 불일치).

    data_analysis_team의 analyst 설명에 python_repl이 남아 있었다 — 5-1에서
    도구를 calculate로 바꾸며 설명을 놓쳤다. 설명은 위임 판단의 근거라
    실제 도구와 어긋나면 리더가 잘못 위임한다.
    """
    from registry import allowed_tool_keys

    spec = _load(path)
    members = [
        (spec.name, spec.tools, spec.description),
        *((s.name, s.tools, s.description) for s in spec.subagents),
    ]

    for member_name, tools, description in members:
        for key in allowed_tool_keys():
            if key in description:
                assert key in tools, (
                    f"{path.stem}/{member_name}: 설명이 '{key}'를 언급하지만 "
                    f"tools에는 없다 ({tools})"
                )


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
def test_calculate_members_know_how_to_handle_tool_errors(path: Path):
    """calculate를 쓰는 팀원은 Error 응답 시 대처를 프롬프트로 알아야 한다.

    실측(2026-09-30): data_analysis_team 팀원이 미허용 함수(all)를 반복
    시도해 한 턴이 28단계까지 늘었다. 허용 목록·대안은 도구 설명과 오류
    메시지가 알려주므로, 프롬프트에는 '같은 식을 그대로 재시도하지 않는다'는
    행동 규칙만 둔다 (중복 금지).
    """
    spec = _load(path)

    for sub in spec.subagents:
        if "calculate" not in sub.tools:
            continue
        assert "Error" in sub.system_prompt and "재시도" in sub.system_prompt, (
            f"{path.stem}/{sub.name}: calculate 오류 대처 규칙이 프롬프트에 없다"
        )


@pytest.mark.parametrize("path", TEMPLATE_PATHS, ids=lambda p: p.stem)
def test_template_subagents_resolve_to_tools(path: Path):
    """템플릿이 참조한 도구가 실제 구현으로 해석된다."""
    spec = _load(path)

    payloads = resolve_subagents(spec)

    assert len(payloads) == len(spec.subagents)


def test_recommended_profile_templates_exist():
    """프로필이 추천하는 템플릿 4종이 실제 파일로 존재한다 (Phase 9 단계 3).

    단계 2까지는 '없으면 조용히 건너뛰기'가 맞는 동작이었지만, 단계 3부터
    없는 추천은 결함이다 — 추천 목록과 배포 파일이 어긋나면 그 프로필
    사용자는 추천을 영영 못 본다.
    """
    from runtime.teams import PROFILES

    missing = [
        stem
        for profile in PROFILES.values()
        for stem in profile.recommended_templates
        if not (TEMPLATES_DIR / f"{stem}.json").exists()
    ]
    assert not missing, f"추천 목록에 있지만 파일이 없는 템플릿: {missing}"


@pytest.mark.parametrize("path", TEMPLATE_PATHS, ids=lambda p: p.stem)
def test_every_template_has_a_display_name(path: Path):
    """드롭다운에 식별자 그대로 노출되지 않도록 표시 이름 매핑을 강제한다."""
    from ui.state import _DISPLAY_NAMES

    assert path.stem in _DISPLAY_NAMES, f"{path.stem}: _DISPLAY_NAMES 매핑이 없다"


SAMPLES_DIR = TEMPLATES_DIR.parent / "workspace" / "samples"
SAMPLE_FILES = [
    "README.md",
    "adfs_events.csv",
    "sync_result_2026-09.csv",
    "dotnet_oidc_exception.txt",
    "python_sync_traceback.txt",
]


@pytest.mark.parametrize("name", SAMPLE_FILES)
def test_sample_workspace_files_are_shipped(name: str):
    """프로필 템플릿의 실행 재료인 샘플이 배포본에 있어야 한다.

    템플릿 프롬프트가 /samples/<파일명>을 기본 경로로 안내하므로, 파일이
    빠지면 clone 직후의 실대화가 '파일 없음'으로 끝난다.
    """
    assert (SAMPLES_DIR / name).exists(), f"workspace/samples/{name} 이 없다"


@pytest.mark.parametrize("name", SAMPLE_FILES)
def test_sample_files_use_only_synthetic_identifiers(name: str):
    """샘플은 contoso 가상 값만 쓴다 — 실제 사내 호스트·계정 유출 방지.

    완전한 검출은 불가능하므로 성질로 검사한다: 등장하는 이메일·UPN 형식
    문자열은 전부 contoso.com 도메인이어야 한다.
    """
    import re

    text = (SAMPLES_DIR / name).read_text(encoding="utf-8")
    addresses = re.findall(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+)", text)
    foreign = sorted(
        {d for d in addresses if d.rstrip(".") not in ("contoso", "contoso.com")}
    )
    assert not foreign, f"{name}: contoso 밖 도메인 발견 {foreign}"


@pytest.mark.parametrize("path", TEMPLATE_PATHS, ids=lambda p: p.stem)
def test_template_builds_a_real_agent(path: Path, monkeypatch):
    """스펙이 통과하는 것과 deepagents가 기동되는 것은 다른 문제다."""
    pytest.importorskip("deepagents")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    from runtime.factory import build_agent

    agent = build_agent(_load(path))

    assert agent is not None
