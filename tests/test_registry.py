"""레지스트리 테스트 — 화이트리스트가 구현에서 파생되는지 확인한다.

Phase 1에서는 spec.py의 ALLOWED_TOOLS 상수와 factory의 구현 dict가 따로 놀아서
구현 없는 키가 화이트리스트에 남을 수 있었다. Phase 2의 계약은 "등록된 것만 허용"이다.
"""

import pytest

from registry import (
    BUILTIN_FS_TOOLS,
    allowed_tool_keys,
    custom_tool_keys,
    get_custom_tool,
    tool_catalog,
)
from runtime.spec import AgentSpec


def test_custom_tools_are_registered():
    assert set(custom_tool_keys()) == {"web_search", "python_repl"}


def test_allowed_keys_are_registry_derived():
    """허용 키 = 커스텀 구현 + 내장 FS 위임 키. 하드코딩 상수가 아니다."""
    assert allowed_tool_keys() == set(custom_tool_keys()) | set(BUILTIN_FS_TOOLS)


def test_every_allowed_key_is_resolvable():
    """화이트리스트에 있는데 구현이 없는 키는 존재할 수 없다."""
    for key in allowed_tool_keys():
        if key in BUILTIN_FS_TOOLS:
            continue  # deepagents 내장 도구로 위임되므로 구현 조회 대상이 아니다
        assert get_custom_tool(key) is not None


def test_get_unknown_tool_raises():
    with pytest.raises(LookupError, match="not implemented"):
        get_custom_tool("ghost_tool")


def test_spec_validation_uses_registry():
    """스펙 밸리데이터가 레지스트리 키를 그대로 수용한다."""
    spec = AgentSpec(
        name="tool_probe",
        description="모든 등록 도구를 요청하는 검증용 스펙",
        system_prompt="검증용",
        tools=sorted(allowed_tool_keys()),
    )
    assert set(spec.tools) == allowed_tool_keys()


def test_tool_catalog_covers_all_allowed_keys():
    assert {info.key for info in tool_catalog()} == allowed_tool_keys()


def test_tool_catalog_entries_have_descriptions():
    """Builder 프롬프트에 그대로 실리므로 빈 설명이 있으면 안 된다."""
    for info in tool_catalog():
        assert info.description.strip()
