"""AgentSpec v0 — Builder가 생성하고 Runtime이 소비하는 에이전트 명세.

설계 원칙:
- subagents 필드는 Phase 1부터 스키마에 존재하되, Phase 1~2에서는 빈 리스트만 허용.
- 도구는 문자열 참조(레지스트리 키)로만 지정. 임의 코드/임포트 경로 금지(하네스 가드레일).
- 스키마 변경 시 SPEC_VERSION을 올리고 BUILD_SPEC.md에 변경 사유를 기록한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from registry import MCP_PREFIX, allowed_tool_keys
from registry.mcp import configured_server_names

SPEC_VERSION = "0.1"


class SubAgentSpec(BaseModel):
    """서브에이전트 명세. Phase 3부터 실제 사용."""

    name: str = Field(..., pattern=r"^[a-z][a-z0-9_]{1,30}$")
    description: str = Field(..., min_length=1, max_length=500)
    prompt: str = Field(..., min_length=1)
    tools: list[str] = Field(default_factory=list)


class AgentSpec(BaseModel):
    """단일 에이전트(팀 리더 포함) 명세."""

    spec_version: str = SPEC_VERSION
    name: str = Field(..., pattern=r"^[a-z][a-z0-9_]{1,30}$")
    description: str = Field(..., min_length=1, max_length=500)
    system_prompt: str = Field(..., min_length=1)
    model: str = "claude-sonnet-4-6"
    tools: list[str] = Field(default_factory=list)
    subagents: list[SubAgentSpec] = Field(default_factory=list)

    @field_validator("tools")
    @classmethod
    def tools_must_be_registered(cls, v: list[str]) -> list[str]:
        """레지스트리에 없는 도구 참조를 차단한다(제품 층위 하네스 가드레일).

        허용 목록은 하드코딩이 아니라 registry에서 파생된다 —
        구현되지 않은 도구가 화이트리스트에 남아 있을 수 없다.
        """
        allowed = allowed_tool_keys()
        for t in v:
            if t.startswith(MCP_PREFIX):
                configured = configured_server_names()
                if t[len(MCP_PREFIX) :] not in configured:
                    raise ValueError(
                        f"unconfigured MCP server: {t!r} "
                        f"(configured: {sorted(configured)})"
                    )
                continue
            if t not in allowed:
                raise ValueError(
                    f"unregistered tool: {t!r} (allowed: {sorted(allowed)})"
                )
        return v

    @field_validator("subagents")
    @classmethod
    def subagents_disabled_before_phase3(
        cls, v: list[SubAgentSpec]
    ) -> list[SubAgentSpec]:
        """Phase 1~2 게이트: 스키마에는 존재하되 값은 비어 있어야 한다.

        Phase 3 착수 시 이 밸리데이터를 제거하고 BUILD_SPEC.md에 기록한다.
        """
        if v:
            raise ValueError("subagents are disabled until Phase 3")
        return v
