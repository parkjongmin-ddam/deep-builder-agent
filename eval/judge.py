"""LLM-as-judge — 기계적으로 못 재는 것만 심판에게 맡긴다 (Phase 4).

checks.py가 도구·팀·가드레일을 확정적으로 판정한 뒤 남는 질문은 하나다:
**system_prompt가 사용자의 요구를 실제로 담고 있는가.** 이건 문자열 매칭으로
확인할 수 없어서 LLM에게 묻는다.

설계상 주의:
- 심판 모델은 Builder 모델과 분리한다(`DEEP_BUILDER_JUDGE_MODEL`). 같은 모델이
  자기 출력을 채점하면 후한 점수가 나온다.
- 점수만 받지 않고 **이유를 반드시 함께** 받는다. 이유 없는 점수로는 회귀를 못 고친다.
- 파싱 실패를 0점으로 뭉개지 않는다. 채점 실패와 낮은 점수는 다른 사건이다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from builder.builder import extract_json
from eval.dataset import EvalCase
from runtime.config import env_or_default
from runtime.spec import AgentSpec

# 심판 모델. Builder(DEEP_BUILDER_MODEL)와 의도적으로 분리한다.
DEFAULT_JUDGE_MODEL = env_or_default("DEEP_BUILDER_JUDGE_MODEL", "claude-sonnet-4-6")

MIN_SCORE = 1
MAX_SCORE = 5
# 이 점수 미만이면 실패로 본다. 3점("요구는 담았으나 빈틈")은 통과시키지 않는다.
PASS_THRESHOLD = 4

JUDGE_SYSTEM_PROMPT = """\
당신은 AI 에이전트 명세를 채점하는 심판입니다.

사용자의 자연어 요구와, 그 요구로 생성된 에이전트 명세를 받습니다.
주어진 채점 기준에 따라 명세의 system_prompt를 평가하세요.

점수 기준 (1~5):
5 — 요구를 정확히 담았고, 작업 절차와 출력 형식이 구체적이다
4 — 요구를 담았고 실행 가능하다. 세부는 다소 성기다
3 — 요구는 담았으나 중요한 부분이 빠졌다
2 — 요구와 부분적으로만 맞다
1 — 요구와 맞지 않거나 내용이 비어 있다

감점 사유:
- 사용자가 말하지 않은 기능을 임의로 추가했다
- 절차나 출력 형식이 없어 실행 결과를 예측할 수 없다
- 도구가 있는데 언제 쓰는지 적혀 있지 않다

출력은 아래 JSON만. 코드펜스·설명 없이 순수 JSON입니다.
{"score": <1~5 정수>, "reason": "<판단 근거 한두 문장>"}
"""

_JUDGE_USER_TEMPLATE = """\
## 사용자의 요구
{request}

## 채점 기준
{rubric}

## 생성된 명세
- name: {name}
- description: {description}
- tools: {tools}
- subagents: {subagents}

### system_prompt
{system_prompt}
"""


class JudgeError(RuntimeError):
    """심판이 점수를 내지 못했다. 낮은 점수와는 다른 사건이다."""


@dataclass(frozen=True)
class JudgeVerdict:
    """심판 판정."""

    score: int
    reason: str

    @property
    def passed(self) -> bool:
        return self.score >= PASS_THRESHOLD


def build_judge_prompt(spec: AgentSpec, case: EvalCase) -> str:
    """심판에게 보여줄 사용자 메시지를 만든다."""
    return _JUDGE_USER_TEMPLATE.format(
        request=case.request,
        rubric=case.rubric,
        name=spec.name,
        description=spec.description,
        tools=spec.tools or "(none)",
        subagents=[s.name for s in spec.subagents] or "(none)",
        system_prompt=spec.system_prompt,
    )


def _build_chat_model(model: str):
    """지연 임포트 — 심판을 안 쓰는 테스트가 LangChain을 끌고 오지 않도록."""
    from langchain.chat_models import init_chat_model

    return init_chat_model(model)


def _message_text(response) -> str:
    """LangChain 응답에서 텍스트를 뽑는다 (content가 블록 리스트인 경우 포함)."""
    content = response.content
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def judge_spec(
    spec: AgentSpec,
    case: EvalCase,
    *,
    model: str = DEFAULT_JUDGE_MODEL,
    chat_model=None,
) -> JudgeVerdict:
    """생성된 명세를 심판에게 채점시킨다.

    Args:
        spec: 채점 대상 명세.
        case: 요구와 채점 기준.
        model: 심판 모델 ID. `chat_model`이 주어지면 무시된다.
        chat_model: 테스트용 주입 지점.

    Raises:
        JudgeError: 응답을 점수로 해석하지 못했을 때.
    """
    llm = chat_model if chat_model is not None else _build_chat_model(model)

    response = llm.invoke(
        [("system", JUDGE_SYSTEM_PROMPT), ("user", build_judge_prompt(spec, case))]
    )
    raw = _message_text(response)

    try:
        parsed = extract_json(raw)
    except ValueError as exc:
        raise JudgeError(f"심판 응답을 JSON으로 읽지 못했다: {exc}") from exc

    score = parsed.get("score")
    if not isinstance(score, int) or not MIN_SCORE <= score <= MAX_SCORE:
        raise JudgeError(
            f"심판이 {MIN_SCORE}~{MAX_SCORE} 범위의 정수 점수를 주지 않았다: {score!r}"
        )

    reason = parsed.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise JudgeError("심판이 판단 근거를 적지 않았다")

    return JudgeVerdict(score=score, reason=reason.strip())
