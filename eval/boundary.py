"""Builder 팀 판단 **경계 프로브** (Phase 9) — 통과/실패가 아니라 빈도를 잰다.

평가 세트(eval/cases/)는 기대가 확정된 케이스만 담는다. 여기 있는 문구는
Builder가 **흔들리는 것이 관찰된** 경계 입력이다 — 어느 쪽이 정답인지보다
"얼마나 자주 팀을 만드는가"가 관심사라, 세트에 넣으면 간헐 실패로 기준값만
흐린다. 대신 별도로 보존하고 빈도를 측정한다.

용도: BUILD_SPEC 6절 "Builder 팀 판단 경계 변동" 후속 과제의 측정 도구.
프롬프트의 팀 판단 기준을 고친 뒤 `python -m eval.boundary`로 전/후 빈도를
비교한다 (기본 3회 — Builder 호출 비용이 있으므로 수동 실행 전용).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from runtime.spec import AgentSpec

SpecGenerator = Callable[[str], AgentSpec]


@dataclass(frozen=True)
class BoundaryProbe:
    """경계 프로브 하나 — 원문 요청과 관찰 기록.

    `in_prompt=True`는 이 문구(또는 거의 같은 문구)가 Builder 프롬프트에
    예시로 들어가 있다는 뜻이다 — 그 프로브의 개선은 일반화가 아니라
    **과적합일 수 있으므로**, 판단은 in_prompt=False 프로브들로 한다.
    """

    id: str
    request: str
    observed: str  # 측정 이력 (날짜 + 빈도). 재측정하면 여기에 덧붙인다.
    in_prompt: bool = False


# 전부 "A해서 B해주는" 꼴 + 역할 분리 요구 없음 — 단일이 정답인 경계 입력.
# 1번은 최초 발견 원문, 2~4번은 일반화 측정용 새 문구(2026-10-01 추가).
# 1번을 프롬프트 예시로 넣었던 수정은 되돌렸다(효과 미검출 + 프로브 오염) —
# 그래서 현재 어떤 프로브도 프롬프트에 없다. 프로브 문구를 프롬프트 예시로
# 넣게 되면 반드시 in_prompt=True로 표시한다.
BOUNDARY_PROBES: tuple[BoundaryProbe, ...] = (
    BoundaryProbe(
        id="research_then_summarize",
        request=(
            "ADFS 토큰 서명 인증서 만료 대응 절차를 웹에서 조사해서 "
            "점검 체크리스트로 정리해주는 에이전트 만들어줘"
        ),
        observed=(
            "2026-10-01: 수정 전 합산 8회 중 2회 팀(오전 발견 3회 중 2회 + "
            "대칭 측정 5회 중 0회) → 중간본(예시 ② 포함) 5회 중 0회 → "
            "최종본(①③만) 5회 중 1회. 수정 전 25%와 최종 20%는 같은 수준 — "
            "발생률 낮은 현상이라 이 표본으로는 효과 검출 불가, 개선을 주장하지 "
            "않는다. 오전/오후 측정의 조건 차이(문구·호출 경로·레지스트리 상태) "
            "없음 확인. 중간본의 예시 ②는 과적합·프로브 오염 때문에 제거됐다"
        ),
    ),
    BoundaryProbe(
        id="read_log_then_organize",
        request="작업공간의 로그 파일을 읽고 오류 원인을 정리해주는 에이전트 만들어줘",
        observed="2026-10-01: 수정 전 0/5 · 중간본 0/5 · 최종본 0/5",
    ),
    BoundaryProbe(
        id="search_then_tabulate",
        request="웹에서 자료를 찾아서 표로 요약해주는 에이전트 만들어줘",
        observed="2026-10-01: 수정 전 0/5 · 중간본 0/5 · 최종본 0/5",
    ),
    BoundaryProbe(
        id="read_minutes_then_todos",
        request="회의록 파일을 읽고 할 일 목록으로 정리해주는 에이전트 만들어줘",
        observed="2026-10-01: 수정 전 0/5 · 중간본 0/5 · 최종본 0/5",
    ),
)


def _default_generator(request: str) -> AgentSpec:
    """지연 임포트 — eval.runner와 같은 이유 (임포트만으로 LangChain 금지)."""
    from builder.builder import generate_spec

    return generate_spec(request)


def team_formation_count(
    request: str,
    runs: int = 3,
    spec_generator: SpecGenerator | None = None,
) -> tuple[int, int]:
    """요청을 `runs`회 생성해 (팀 생성 횟수, 전체 시도 횟수)를 돌려준다.

    생성 실패는 팀도 단일도 아니다 — 조용히 세지 않고 예외를 그대로 올린다
    (실패가 섞이면 빈도 해석이 불가능하다).
    """
    if runs < 1:
        raise ValueError(f"runs must be >= 1, got {runs}")
    generate = spec_generator or _default_generator
    team_count = sum(1 for _ in range(runs) if generate(request).subagents)
    return team_count, runs


def main(argv: list[str] | None = None) -> int:
    """`python -m eval.boundary [--runs N]` — 프로브 전체의 팀 생성 빈도 측정."""
    import argparse

    from runtime.config import load_env
    from runtime.console import force_utf8_stdio

    force_utf8_stdio()
    load_env()

    parser = argparse.ArgumentParser(prog="eval.boundary", description=__doc__)
    parser.add_argument("--runs", type=int, default=3, help="프로브당 생성 횟수")
    args = parser.parse_args(argv)

    for probe in BOUNDARY_PROBES:
        teams, total = team_formation_count(probe.request, runs=args.runs)
        marker = " [프롬프트 예시 — 과적합 주의]" if probe.in_prompt else ""
        print(f"[{probe.id}]{marker} 팀 생성 {teams}/{total}")
        print(f"  요청: {probe.request}")
        print(f"  기존 관찰: {probe.observed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
