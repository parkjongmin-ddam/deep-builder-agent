"""평가 실행 — 케이스를 돌려 리포트를 만든다 (Phase 4).

파이프라인:
    EvalCase → Builder로 스펙 생성 → 기계적 검사 → (통과 시) LLM 심판 → 집계

설계상 주의:
- **생성 실패도 결과다.** 예외로 중단하지 않고 케이스 결과에 담아 계속 돈다.
  10개 중 3번째가 죽어서 나머지를 못 보는 것이 최악이다.
- **기계적 검사가 실패하면 심판을 부르지 않는다.** 도구를 잘못 고른 명세의
  프롬프트 문장력을 채점하는 것은 돈 낭비다.
- `spec_generator`와 `judge`를 주입 가능하게 둔다. API 키 없이 전체 파이프라인을
  테스트할 수 있어야 한다 (builder.generate_spec의 chat_model 주입과 같은 이유).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from eval.checks import CheckResult, run_checks
from eval.dataset import EvalCase, load_cases
from eval.judge import JudgeError, JudgeVerdict, judge_spec
from runtime.config import load_env
from runtime.console import force_utf8_stdio
from runtime.spec import AgentSpec

SpecGenerator = Callable[[str], AgentSpec]
Judge = Callable[[AgentSpec, EvalCase], JudgeVerdict]


@dataclass(frozen=True)
class CaseResult:
    """케이스 하나의 평가 결과."""

    case_id: str
    request: str
    spec: AgentSpec | None = None
    checks: list[CheckResult] = field(default_factory=list)
    verdict: JudgeVerdict | None = None
    error: str | None = None

    @property
    def checks_passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    @property
    def passed(self) -> bool:
        """생성 성공 + 기계적 검사 전부 통과 + (심판이 돌았다면) 심판 통과."""
        if self.error is not None or not self.checks_passed:
            return False
        return self.verdict.passed if self.verdict is not None else True

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


@dataclass(frozen=True)
class EvalReport:
    """전체 실행 결과."""

    results: list[CaseResult]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def pass_rate(self) -> float:
        """통과율 (0.0~1.0). 케이스가 없으면 0.0."""
        return self.passed / self.total if self.total else 0.0

    @property
    def errors(self) -> list[CaseResult]:
        """생성 자체가 실패한 케이스."""
        return [r for r in self.results if r.error is not None]

    @property
    def mean_score(self) -> float | None:
        """심판 점수 평균. 심판이 한 번도 안 돌았으면 None."""
        scores = [r.verdict.score for r in self.results if r.verdict is not None]
        return sum(scores) / len(scores) if scores else None

    def summary_line(self) -> str:
        """한 줄 요약."""
        score = f", 평균 {self.mean_score:.2f}점" if self.mean_score is not None else ""
        return f"{self.passed}/{self.total} 통과 ({self.pass_rate:.0%}){score}"


def _default_spec_generator(request: str) -> AgentSpec:
    """지연 임포트 — 평가 모듈을 임포트만 해도 LangChain이 딸려오지 않도록."""
    from builder.builder import generate_spec

    return generate_spec(request)


def run_case(
    case: EvalCase,
    *,
    spec_generator: SpecGenerator | None = None,
    judge: Judge | None = None,
) -> CaseResult:
    """케이스 하나를 평가한다. 예외를 밖으로 내보내지 않는다.

    Args:
        case: 평가 케이스.
        spec_generator: 자연어 → AgentSpec. 기본값은 Builder.
        judge: 심판. None이면 심판 단계를 건너뛴다(기계적 검사만).
    """
    generate = spec_generator or _default_spec_generator

    try:
        spec = generate(case.request)
    except Exception as exc:  # 생성 실패도 결과로 남긴다
        return CaseResult(
            case_id=case.id,
            request=case.request,
            error=f"{type(exc).__name__}: {exc}",
        )

    checks = run_checks(spec, case)

    # 기계적 검사가 깨졌으면 심판을 부르지 않는다 — 이미 실패한 케이스다.
    if judge is None or not all(c.passed for c in checks):
        return CaseResult(
            case_id=case.id, request=case.request, spec=spec, checks=checks
        )

    try:
        verdict = judge(spec, case)
    except JudgeError as exc:
        return CaseResult(
            case_id=case.id,
            request=case.request,
            spec=spec,
            checks=checks,
            error=f"채점 실패: {exc}",
        )

    return CaseResult(
        case_id=case.id,
        request=case.request,
        spec=spec,
        checks=checks,
        verdict=verdict,
    )


def run_evaluation(
    cases: list[EvalCase] | None = None,
    *,
    spec_generator: SpecGenerator | None = None,
    judge: Judge | None = None,
) -> EvalReport:
    """케이스 전체를 평가해 리포트를 만든다.

    Args:
        cases: 평가할 케이스. 생략하면 `eval/cases/*.json` 전체.
        spec_generator: 자연어 → AgentSpec. 기본값은 Builder.
        judge: 심판. None이면 기계적 검사만 돈다.
    """
    cases = load_cases() if cases is None else cases
    return EvalReport(
        results=[
            run_case(case, spec_generator=spec_generator, judge=judge) for case in cases
        ]
    )


def format_report(report: EvalReport) -> str:
    """리포트를 사람이 읽는 텍스트로 만든다 (CLI·로그용)."""
    lines = [report.summary_line(), ""]
    for result in report.results:
        mark = "PASS" if result.passed else "FAIL"
        lines.append(f"[{mark}] {result.case_id}")
        if result.error:
            lines.append(f"       error: {result.error}")
        for check in result.failed_checks:
            lines.append(f"       check {check.name}: {check.detail}")
        if result.verdict is not None:
            lines.append(
                f"       judge {result.verdict.score}/5 — {result.verdict.reason}"
            )
    return "\n".join(lines)


def main() -> int:
    """`python -m eval.runner` — 기본 케이스로 평가를 돌린다 (심판 포함).

    인코딩 고정이 **평가를 돌리기 전에** 와야 한다. 리포트에 `—` 같은 문자가 있어
    출력 단계에서 죽으면 이미 지불한 LLM 호출 결과가 통째로 사라진다(실제로 겪었다).
    """
    force_utf8_stdio()
    load_env()

    report = run_evaluation(judge=judge_spec)
    print(format_report(report))
    return 0 if report.passed == report.total else 1


if __name__ == "__main__":
    raise SystemExit(main())
