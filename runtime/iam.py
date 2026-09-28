"""IAM 레이어 (Phase 6) — 사용자 RBAC + 에이전트 권한 경계(permissions boundary).

두 층위를 하나의 정책으로 묶는다:

1. **행위 통제 (RBAC)**: 주체(principal)의 역할(role)이 허용하는 행위만 실행된다.
   행위는 4가지다 — create_agent / revise_agent / run_agent / view.
2. **권한 경계 (boundary)**: 에이전트를 생성·수정할 때, 스펙이 요청한 도구는
   **생성자의 역할이 허용한 도구를 초과할 수 없다** (리더·팀원 전원).
   위임이 권한 상승 경로가 되면 안 된다 — 서브에이전트 도구를 메인과 같은
   화이트리스트로 검증하는 것과 같은 이유다.

의미론 (AWS IAM permissions boundary 개념 이식):
- 경계는 **부여(생성) 시점**에 적용된다. 이미 만들어진 에이전트를 실행하는 것은
  에이전트 자신의 권한을 쓰는 것이므로(assume-role) run_agent 행위 검사만 받는다.
- deny-by-default: 역할에 명시된 행위·도구만 허용된다. 와일드카드는
  `"*"`(전부)와 `"mcp:*"`(모든 MCP 서버)만 인정한다.

기존 동작 보존 (v0.3 `SubAgentSpec.model`과 같은 원칙):
- 주체를 지정하지 않으면 `admin`으로 동작한다. 기존 CLI·UI·테스트가 그대로
  돌아야 하기 때문이다. 운영에서 최소 권한을 원하면 `--as` 또는
  `DEEP_BUILDER_PRINCIPAL`로 주체를 명시한다.

감사 로그:
- 허용·거부 **모두** JSONL로 남긴다 (기본 `logs/audit.jsonl`).
- `workspace/`에 두지 않는다 — 그 안의 파일은 에이전트가 전부 읽는다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field, field_validator, model_validator

from registry import MCP_PREFIX, allowed_tool_keys
from runtime.config import env_or_default
from runtime.spec import AgentSpec

# --- 행위 정의 --------------------------------------------------------------

ACTION_CREATE = "create_agent"
ACTION_REVISE = "revise_agent"
ACTION_RUN = "run_agent"
ACTION_VIEW = "view"

KNOWN_ACTIONS = frozenset({ACTION_CREATE, ACTION_REVISE, ACTION_RUN, ACTION_VIEW})

# 전부 허용 와일드카드. 도구 목록에서는 "mcp:*"(모든 MCP 서버)도 인정한다.
WILDCARD = "*"
MCP_WILDCARD = f"{MCP_PREFIX}*"

# 주체 미지정 시의 기본값. 기존 흐름(테스트 307건 포함)이 그대로 돌아야 한다.
DEFAULT_PRINCIPAL = "admin"

# 정책 파일 위치. 없으면 코드 내 기본 정책으로 동작한다.
DEFAULT_IAM_FILE = Path("iam.json")


class PermissionDeniedError(RuntimeError):
    """주체의 역할이 요청한 행위 또는 도구 경계를 허용하지 않는다."""


# --- 정책 모델 --------------------------------------------------------------


class Role(BaseModel):
    """역할 — 허용 행위와 도구 경계의 묶음. deny-by-default."""

    actions: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)

    @field_validator("actions")
    @classmethod
    def actions_must_be_known(cls, v: list[str]) -> list[str]:
        """오타난 행위명이 조용히 '거부'로 동작하는 것을 막는다.

        deny-by-default에서는 잘못 적은 허용 항목이 에러 없이 사라진다 —
        정책 로드 시점에 명시적으로 실패시켜야 디버깅이 가능하다.
        """
        unknown = sorted(set(v) - KNOWN_ACTIONS - {WILDCARD})
        if unknown:
            raise ValueError(
                f"unknown actions: {unknown} (known: {sorted(KNOWN_ACTIONS)} or '*')"
            )
        return v

    @field_validator("tools")
    @classmethod
    def tools_must_exist_or_be_wildcards(cls, v: list[str]) -> list[str]:
        """정책이 존재하지 않는 도구를 허용하면 죽은 항목이 된다 — 로드 시점에 막는다.

        `mcp:` 접두 키는 형식만 본다. MCP 서버 설정은 실행 시점에 달라질 수
        있고, 미설정 서버 사용은 스펙 검증(`validate_tool_keys`)이 이미 막는다.
        """
        allowed = allowed_tool_keys()
        unknown = sorted(
            t
            for t in v
            if t not in (WILDCARD, MCP_WILDCARD)
            and not t.startswith(MCP_PREFIX)
            and t not in allowed
        )
        if unknown:
            raise ValueError(
                f"unregistered tools in role policy: {unknown} "
                f"(allowed: {sorted(allowed)}, wildcards: '*', 'mcp:*')"
            )
        return v


class Principal(BaseModel):
    """해석이 끝난 주체 — 이름과 역할 실체를 함께 든다."""

    name: str
    role_name: str
    role: Role


class IamConfig(BaseModel):
    """역할 정의 + 주체→역할 매핑. `iam.json`에서 읽거나 기본 정책을 쓴다.

    `groups`는 OIDC 신원용이다 (Phase 7) — IdP(Okta 등)의 그룹 클레임을
    역할로 매핑한다. 여러 그룹에 속한 사용자는 **정책 파일에 선언된 순서**로
    첫 매칭이 이긴다 (선언 순서 = 정책 작성자가 정한 우선순위).
    """

    roles: dict[str, Role]
    principals: dict[str, str]
    groups: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def mappings_must_reference_existing_roles(self) -> IamConfig:
        """없는 역할을 가리키는 주체·그룹은 로그인 자체가 불가능해야 한다."""
        for label, mapping in (("principals", self.principals), ("groups", self.groups)):
            dangling = sorted(
                name for name, role in mapping.items() if role not in self.roles
            )
            if dangling:
                raise ValueError(
                    f"{label} reference undefined roles: {dangling} "
                    f"(defined roles: {sorted(self.roles)})"
                )
        return self

    def resolve(self, name: str | None = None) -> Principal:
        """주체 이름을 역할까지 해석한다.

        우선순위: 인자 > `DEEP_BUILDER_PRINCIPAL` > `admin`(기존 동작 보존).

        Raises:
            PermissionDeniedError: 정책에 없는 주체일 때. 미등록 주체를
                기본 역할로 조용히 받아주면 RBAC이 장식이 된다.
        """
        resolved = name or env_or_default("DEEP_BUILDER_PRINCIPAL", DEFAULT_PRINCIPAL)
        if resolved not in self.principals:
            raise PermissionDeniedError(
                f"unknown principal: {resolved!r} "
                f"(defined: {sorted(self.principals)})"
            )
        role_name = self.principals[resolved]
        return Principal(name=resolved, role_name=role_name, role=self.roles[role_name])

    def resolve_identity(self, email: str, groups: Iterable[str] = ()) -> Principal:
        """OIDC 신원(검증된 이메일 + 그룹 클레임)을 주체로 해석한다 (Phase 7).

        우선순위:
        1. `principals`의 이메일 직접 매핑 (개인 예외 — 그룹보다 구체적이므로 우선)
        2. `groups` 매핑 — 정책 파일 선언 순서로 첫 매칭
        3. 매핑 없음 → 거부. **로그인 성공 ≠ 인가**다. IdP가 신원을 보증해도
           이 시스템에서의 역할은 정책이 명시해야 한다 (deny-by-default).

        주체 이름은 이메일이다 — 감사 로그가 "선택한 이름"이 아니라
        "검증된 신원"을 가리키게 된다.
        """
        user_groups = set(groups)
        if not email:
            _write_audit(
                "(no-email)",
                "(unmapped)",
                "resolve_identity",
                "deny",
                detail={"groups": sorted(user_groups)},
            )
            raise PermissionDeniedError(
                "OIDC identity has no email claim — cannot map to a role"
            )
        if email in self.principals:
            role_name = self.principals[email]
            return Principal(name=email, role_name=role_name, role=self.roles[role_name])

        for group, role_name in self.groups.items():
            if group in user_groups:
                return Principal(
                    name=email, role_name=role_name, role=self.roles[role_name]
                )

        # 거부만 기록한다 — 성공 해석까지 남기면 Streamlit 재실행(위젯 조작마다
        # resolve_identity 호출)이 클릭당 한 줄씩 쌓아 로그가 스팸이 된다.
        # 허용된 행위는 authorize_action이 행위 시점에 이미 기록한다.
        _write_audit(
            email,
            "(unmapped)",
            "resolve_identity",
            "deny",
            detail={
                "groups": sorted(user_groups),
                "mapped_groups": sorted(self.groups),
            },
        )
        raise PermissionDeniedError(
            f"no role mapping for {email!r} "
            f"(groups: {sorted(user_groups)}; mapped groups: {sorted(self.groups)})"
        )


def _default_config() -> IamConfig:
    """`iam.json`이 없을 때 쓰는 기본 정책. 파일과 내용을 일치시켜 둔다."""
    return IamConfig(
        roles={
            "admin": Role(actions=[WILDCARD], tools=[WILDCARD]),
            "builder": Role(
                actions=[ACTION_CREATE, ACTION_REVISE, ACTION_RUN, ACTION_VIEW],
                # python_repl(임의 코드 실행)과 MCP는 admin만 부여할 수 있다.
                tools=["web_search", "calculate", "file_read", "file_write", "file_list"],
            ),
            "operator": Role(actions=[ACTION_RUN, ACTION_VIEW], tools=[]),
            "viewer": Role(actions=[ACTION_VIEW], tools=[]),
        },
        principals={
            "admin": "admin",
            "demo_builder": "builder",
            "demo_operator": "operator",
            "demo_viewer": "viewer",
        },
        # OIDC 그룹 클레임 → 역할. IdP(Okta) 쪽 그룹 이름에 맞춰 수정한다.
        groups={
            "agent-admins": "admin",
            "agent-builders": "builder",
            "agent-operators": "operator",
            "agent-viewers": "viewer",
        },
    )


def load_iam_config(path: Path | None = None) -> IamConfig:
    """정책을 로드한다. 인자 > `DEEP_BUILDER_IAM_FILE` > `iam.json` > 기본 정책.

    명시한 파일(인자 또는 환경변수)이 없거나 깨졌으면 **기본 정책으로 넘어가지
    않고 실패한다** — 정책 파일 오타가 조용히 기본 정책 실행이 되면 감사가
    불가능하다. 루트 `iam.json`은 없을 수 있으므로 그때만 기본 정책을 쓴다.
    """
    explicit = path or (
        Path(p) if (p := env_or_default("DEEP_BUILDER_IAM_FILE", "")) else None
    )
    target = explicit or DEFAULT_IAM_FILE
    if explicit is None and not target.exists():
        return _default_config()
    return IamConfig(**json.loads(target.read_text(encoding="utf-8")))


# --- 판정 -------------------------------------------------------------------


def is_allowed(principal: Principal, action: str) -> bool:
    """행위 허용 여부만 본다 (감사 로그 없음 — UI 위젯 활성/비활성용)."""
    return WILDCARD in principal.role.actions or action in principal.role.actions


def authorize_action(principal: Principal, action: str, *, resource: str = "") -> None:
    """행위를 판정하고 **허용·거부 모두** 감사 로그에 남긴다.

    Raises:
        PermissionDeniedError: 역할이 행위를 허용하지 않을 때.
    """
    allowed = is_allowed(principal, action)
    _audit(principal, action, "allow" if allowed else "deny", resource=resource)
    if not allowed:
        raise PermissionDeniedError(
            f"principal {principal.name!r} (role {principal.role_name!r}) "
            f"is not allowed to {action} "
            f"(allowed actions: {sorted(principal.role.actions)})"
        )


def spec_tool_keys(spec: AgentSpec) -> set[str]:
    """리더와 모든 팀원이 요청한 도구 키 — 경계는 팀 전체에 적용된다."""
    return {*spec.tools, *(t for sub in spec.subagents for t in sub.tools)}


def boundary_violations(requested: Iterable[str], allowed: Iterable[str]) -> list[str]:
    """경계를 초과한 도구 목록을 돌려준다 (순수 함수 — Builder 재시도 루프에서도 쓴다)."""
    allowed_set = set(allowed)
    if WILDCARD in allowed_set:
        return []
    return sorted(
        key
        for key in set(requested)
        if key not in allowed_set
        and not (key.startswith(MCP_PREFIX) and MCP_WILDCARD in allowed_set)
    )


def boundary_error_message(violations: list[str], allowed: Iterable[str]) -> str:
    """경계 위반 메시지 — Builder 재시도 피드백으로 그대로 들어간다.

    무엇이 거부됐고 무엇이 허용되는지를 모두 담아야 LLM이 다음 시도에서
    허용 도구로 대체할 수 있다.
    """
    return (
        f"permissions boundary violation: {violations} 는 현재 사용자에게 "
        f"허용되지 않은 도구다. 허용 도구만 사용해 다시 생성하라: {sorted(set(allowed))}"
    )


def enforce_boundary(principal: Principal, spec: AgentSpec) -> None:
    """스펙(리더+팀원 전원)의 도구가 주체의 경계 안인지 강제한다.

    Raises:
        PermissionDeniedError: 경계를 초과한 도구가 있을 때.
    """
    violations = boundary_violations(spec_tool_keys(spec), principal.role.tools)
    _audit(
        principal,
        "grant_tools",
        "deny" if violations else "allow",
        resource=spec.name,
        detail={"requested": sorted(spec_tool_keys(spec)), "violations": violations},
    )
    if violations:
        raise PermissionDeniedError(
            f"principal {principal.name!r} (role {principal.role_name!r}): "
            + boundary_error_message(violations, principal.role.tools)
        )


# --- 감사 로그 ---------------------------------------------------------------


def audit_log_path() -> Path:
    """감사 로그 경로. `workspace/` 밖에 둔다 — 에이전트가 읽으면 안 된다."""
    return Path(env_or_default("DEEP_BUILDER_AUDIT_LOG", "logs/audit.jsonl"))


def _write_audit(
    principal_name: str,
    role_name: str,
    action: str,
    decision: str,
    *,
    resource: str = "",
    detail: dict | None = None,
) -> None:
    """판정 한 건을 JSONL 한 줄로 남긴다. 쓰기 실패는 숨기지 않는다(OSError 전파).

    이름/역할을 문자열로 받는다 — 신원 해석 **실패**처럼 Principal이
    만들어지기 전의 거부도 기록해야 하기 때문이다 (role은 "(unmapped)").
    """
    path = audit_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "principal": principal_name,
        "role": role_name,
        "action": action,
        "decision": decision,
        "resource": resource,
        "detail": detail or {},
        "pid": os.getpid(),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _audit(
    principal: Principal,
    action: str,
    decision: str,
    *,
    resource: str = "",
    detail: dict | None = None,
) -> None:
    """해석이 끝난 주체의 판정 기록 — `_write_audit`에 위임한다."""
    _write_audit(
        principal.name,
        principal.role_name,
        action,
        decision,
        resource=resource,
        detail=detail,
    )
