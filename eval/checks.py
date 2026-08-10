"""기계적 검증 — LLM 없이 확정적으로 판정할 수 있는 항목 (Phase 4).

심판 LLM을 쓰기 전에 여기서 걸러낸다. 도구를 옳게 골랐는지, 가드레일이 붙었는지,
팀을 과하게 만들지 않았는지는 **판단이 필요 없는 문제**다. LLM에게 물으면
비용만 들고 답이 흔들린다.

각 검사는 통과/실패와 그 이유를 함께 돌려준다 — 실패했을 때 무엇이 어긋났는지
바로 보이지 않으면 회귀를 고칠 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass

from builder.prompts import GUARDRAIL_SENTENCE
from eval.dataset import EvalCase
from runtime.spec import AgentSpec


@dataclass(frozen=True)
class CheckResult:
    """검사 하나의 결과."""

    name: str
    passed: bool
    detail: str


def check_expected_tools(spec: AgentSpec, case: EvalCase) -> CheckResult:
    """요구를 달성하는 데 필요한 도구가 실제로 선택됐는가."""
    missing = [t for t in case.expect_tools if t not in spec.tools]
    return CheckResult(
        name="expected_tools",
        passed=not missing,
        detail=f"누락된 도구: {missing}" if missing else f"선택됨: {spec.tools}",
    )


def check_forbidden_tools(spec: AgentSpec, case: EvalCase) -> CheckResult:
    """필요 없는 도구를 끌어오지 않았는가 (과잉 선택 탐지).

    리더와 팀원 전체를 본다 — 팀원에게 몰래 붙은 도구도 과잉이다.
    """
    used = set(spec.tools)
    for sub in spec.subagents:
        used.update(sub.tools)

    violations = sorted(used & set(case.forbid_tools))
    return CheckResult(
        name="forbidden_tools",
        passed=not violations,
        detail=f"불필요한 도구: {violations}" if violations else "과잉 선택 없음",
    )


def check_team_shape(spec: AgentSpec, case: EvalCase) -> CheckResult:
    """팀이 필요한 요구에만 팀이 생겼는가.

    단일 에이전트로 될 일을 팀으로 만드는 것은 비용·지연 낭비다.
    반대로 역할 분리가 필요한데 혼자 하는 것도 설계 실패다.
    """
    has_team = bool(spec.subagents)
    names = [s.name for s in spec.subagents]

    if has_team == case.expect_team:
        return CheckResult(
            name="team_shape",
            passed=True,
            detail=f"팀 구성: {names}" if has_team else "단일 에이전트",
        )

    detail = (
        "팀이 필요한데 단일 에이전트로 만들었다"
        if case.expect_team
        else f"단일 에이전트로 될 일에 팀을 만들었다: {names}"
    )
    return CheckResult(name="team_shape", passed=False, detail=detail)


def check_guardrail(spec: AgentSpec, case: EvalCase) -> CheckResult:
    """리더와 팀원 전원의 프롬프트에 가드레일 문장이 있는가.

    `ensure_guardrail()`이 코드로 주입하므로 정상 경로에서는 항상 통과해야 한다.
    실패한다면 주입 경로가 깨진 것이다 — 그래서 평가 항목으로 남긴다.
    """
    missing = [
        sub.name
        for sub in spec.subagents
        if GUARDRAIL_SENTENCE not in sub.system_prompt
    ]
    if GUARDRAIL_SENTENCE not in spec.system_prompt:
        missing = ["(leader)", *missing]

    return CheckResult(
        name="guardrail",
        passed=not missing,
        detail=f"가드레일 없음: {missing}" if missing else "리더·팀원 전원 포함",
    )


# 실행 순서대로. 새 검사를 추가하면 여기에만 등록한다.
ALL_CHECKS = (
    check_expected_tools,
    check_forbidden_tools,
    check_team_shape,
    check_guardrail,
)


def run_checks(spec: AgentSpec, case: EvalCase) -> list[CheckResult]:
    """등록된 모든 기계적 검사를 실행한다."""
    return [check(spec, case) for check in ALL_CHECKS]
