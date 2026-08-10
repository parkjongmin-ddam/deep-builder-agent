"""AgentSpec v0.2 — Builder가 생성하고 Runtime이 소비하는 에이전트 명세.

설계 원칙:
- 도구는 문자열 참조(레지스트리 키)로만 지정. 임의 코드/임포트 경로 금지(하네스 가드레일).
- 스키마 변경 시 SPEC_VERSION을 올리고 BUILD_SPEC.md에 변경 사유를 기록한다.

v0.2 (Phase 3, 2026-08-10):
- subagents 비활성화 밸리데이터 제거. 이제 실제 팀을 선언할 수 있다.
- `SubAgentSpec.prompt` → `system_prompt`로 개명. AgentSpec과 용어를 맞추고
  deepagents `SubAgent` TypedDict의 키와 1:1 대응시켜 번역 실수를 없앤다.
- 서브에이전트 도구도 메인과 **동일한 화이트리스트 검증**을 받는다.
  위임이 가드레일 우회 경로가 되면 안 된다.
- 계층 깊이는 1로 고정한다 — SubAgentSpec에 subagents 필드가 없으므로
  구조적으로 강제된다(무한 위임 트리 방지).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from registry import MCP_PREFIX, allowed_tool_keys
from registry.mcp import configured_server_names
from runtime.guardrail import ensure_guardrail

SPEC_VERSION = "0.3"

# 팀 규모 상한. deepagents는 서브에이전트마다 별도 그래프를 컴파일하므로
# 무제한 허용하면 생성 비용·토큰이 조용히 폭증한다.
MAX_SUBAGENTS = 5


def validate_tool_keys(keys: list[str]) -> list[str]:
    """도구 참조가 레지스트리(또는 설정된 MCP 서버)에 존재하는지 검증한다.

    메인 에이전트와 서브에이전트가 같은 함수를 쓴다 — 위임 경로에만
    느슨한 검증이 적용되는 일이 없도록.

    Raises:
        ValueError: 등록되지 않은 도구이거나 설정되지 않은 MCP 서버일 때.
    """
    allowed = allowed_tool_keys()
    for t in keys:
        if t.startswith(MCP_PREFIX):
            configured = configured_server_names()
            if t[len(MCP_PREFIX) :] not in configured:
                raise ValueError(
                    f"unconfigured MCP server: {t!r} "
                    f"(configured: {sorted(configured)})"
                )
            continue
        if t not in allowed:
            raise ValueError(f"unregistered tool: {t!r} (allowed: {sorted(allowed)})")
    return keys


class SubAgentSpec(BaseModel):
    """서브에이전트 명세.

    `subagents` 필드가 없다 — 서브에이전트는 다시 팀을 거느릴 수 없다.
    """

    name: str = Field(..., pattern=r"^[a-z][a-z0-9_]{1,30}$")
    description: str = Field(..., min_length=1, max_length=500)
    system_prompt: str = Field(..., min_length=1)
    tools: list[str] = Field(default_factory=list)

    # 이 팀원만 다른 모델로 돌린다. 비우면 **리더 모델을 상속**한다.
    #
    # 왜 필요한가 (v0.3): 실측상 2인 팀은 단일 대비 출력 토큰을 10배 이상 쓰고,
    # 그 대부분이 팀원 쪽에서 나온다. 조사·추출처럼 판단이 단순한 역할을 값싼
    # 모델로 돌리면 비용이 직접 줄어든다.
    #
    # 기본값을 None으로 두는 이유는 **기존 스펙 파일이 그대로 돌아야** 하기 때문이다.
    # 빈 문자열은 미지정으로 취급한다 — `.env`에서 겪은 것과 같은 함정을 막는다.
    model: str | None = Field(default=None, max_length=100)

    @field_validator("tools")
    @classmethod
    def tools_must_be_registered(cls, v: list[str]) -> list[str]:
        """서브에이전트 도구도 메인과 동일한 화이트리스트를 통과해야 한다."""
        return validate_tool_keys(v)

    @field_validator("model")
    @classmethod
    def blank_model_means_inherit(cls, v: str | None) -> str | None:
        """공백뿐인 모델 ID를 미지정으로 바꾼다.

        `"model": ""`을 그대로 넘기면 deepagents가 빈 모델 ID를 해석하려다
        런타임에 죽는다. 스펙 단계에서 상속으로 정규화하는 편이 낫다.
        """
        return v.strip() or None if isinstance(v, str) else v


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
        return validate_tool_keys(v)

    @field_validator("subagents")
    @classmethod
    def subagents_must_be_sane(cls, v: list[SubAgentSpec]) -> list[SubAgentSpec]:
        """팀 구성이 실행 가능한 형태인지 확인한다.

        이름 중복은 특히 위험하다 — 리더는 `task(subagent_type=<name>)`로
        위임하므로, 이름이 겹치면 어느 쪽이 호출될지 알 수 없다.
        """
        if len(v) > MAX_SUBAGENTS:
            raise ValueError(f"too many subagents: {len(v)} (max {MAX_SUBAGENTS})")

        names = [sub.name for sub in v]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"duplicate subagent names: {duplicates}")

        return v


def load_spec_file(path: Path) -> AgentSpec:
    """스펙 JSON 파일을 읽어 **가드레일이 보장된** AgentSpec으로 만든다.

    Builder 루프는 `ensure_guardrail()`을 거치지만, 손으로 쓴 스펙을 넣는
    `cli.py --spec`과 UI 템플릿 로드는 그 경로를 타지 않아 가드레일 없는 스펙이
    그대로 통과했다. 게다가 두 진입점이 로드 코드를 각자 복제하고 있었다 —
    `.env` 로드·콘솔 인코딩과 같은 실패 방식이다.

    주입은 멱등이다. 문장이 이미 있으면 파일 내용이 그대로 쓰인다.
    """
    return AgentSpec(**ensure_guardrail(json.loads(path.read_text(encoding="utf-8"))))
