"""평가 데이터셋 — Builder를 채점하기 위한 케이스 정의 (Phase 4).

무엇을 평가하는가: **Builder가 자연어 요구를 옳은 AgentSpec으로 옮기는가.**
생성된 에이전트의 답변 품질이 아니다. 그건 도구·모델·프롬프트가 뒤섞인 결과라
회귀 신호로 쓰기 어렵다. Builder의 번역 품질은 이 프로젝트가 직접 책임지는 부분이다.

케이스마다 두 종류의 기대를 적는다:
- **기계적으로 확인 가능한 것** (도구 선택, 팀 구성, 가드레일) → eval/checks.py
- **사람 판단이 필요한 것** (프롬프트가 요구를 담고 있는가) → eval/judge.py 의 rubric
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

CASES_DIR = Path(__file__).resolve().parent / "cases"


class EvalCase(BaseModel):
    """평가 케이스 하나. 자연어 요구 + 그 요구에 대한 기대."""

    id: str = Field(..., pattern=r"^[a-z][a-z0-9_]{1,60}$")
    request: str = Field(..., min_length=1)

    # 기계적 확인 -----------------------------------------------------------
    expect_tools: list[str] = Field(
        default_factory=list, description="반드시 선택되어야 하는 도구 키"
    )
    forbid_tools: list[str] = Field(
        default_factory=list, description="선택되면 안 되는 도구 키 (과잉 선택 탐지)"
    )
    expect_team: bool = Field(
        default=False, description="팀(subagents)을 만들어야 하는 요구인가"
    )

    # 사람 판단 -------------------------------------------------------------
    rubric: str = Field(
        ..., min_length=1, description="LLM 심판이 system_prompt를 볼 때 쓸 기준"
    )


def load_cases(path: Path | None = None) -> list[EvalCase]:
    """케이스 파일(들)을 읽어 검증된 EvalCase 목록으로 만든다.

    Args:
        path: 특정 JSON 파일. 생략하면 `eval/cases/*.json` 전체.

    Raises:
        ValueError: JSON 형식이 틀렸거나 케이스 id가 중복될 때.
    """
    paths = [path] if path is not None else sorted(CASES_DIR.glob("*.json"))

    cases: list[EvalCase] = []
    for p in paths:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"{p}: 최상위는 케이스 배열이어야 한다")
        cases.extend(EvalCase(**entry) for entry in raw)

    ids = [c.id for c in cases]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"중복된 케이스 id: {duplicates}")

    return cases
