"""가드레일 문장 — 생성 경로와 무관하게 모든 스펙에 보장한다.

**왜 `builder/`가 아니라 `runtime/`인가**: 가드레일은 Builder만의 관심사가 아니라
**제품 층위의 불변식**이다. 예전에는 `builder/`에 있어서 Builder 루프를 거친
스펙만 보호받았고, `cli.py --spec`과 UI의 템플릿 로드는 손으로 쓴 스펙을
가드레일 없이 그대로 통과시켰다. `ui`가 `cli`를 임포트하는 것은 레이어가
거꾸로이므로(`last_text`를 `runtime/messages.py`로 옮긴 것과 같은 이유)
아래층인 여기에 둔다.

`_with_guardrail`은 멱등이다 — 이미 있으면 그대로 둔다. 그래서 Builder가
프롬프트 지시를 지켜 직접 써 넣었든 안 썼든 결과가 같다.
"""

from __future__ import annotations

# 생성되는 모든 에이전트의 system_prompt에 반드시 포함되는 문장.
# Builder가 빠뜨려도 `ensure_guardrail()`이 코드로 주입한다.
GUARDRAIL_SENTENCE = "허용된 도구 외의 작업을 시도하지 말고, 불확실하면 사용자에게 확인하라."


def _with_guardrail(prompt):
    """프롬프트 끝에 가드레일 문장을 덧붙인다 (이미 있거나 문자열이 아니면 그대로)."""
    if not isinstance(prompt, str) or GUARDRAIL_SENTENCE in prompt:
        return prompt
    return f"{prompt.rstrip()}\n\n{GUARDRAIL_SENTENCE}"


def ensure_guardrail(data: dict) -> dict:
    """리더와 모든 서브에이전트의 system_prompt에 가드레일 문장을 보장한다.

    원본을 변경하지 않는다. Builder가 프롬프트 지시를 어겨도, 사람이 손으로 쓴
    스펙에 문장이 없어도 제품 층위에서 보장된다.

    서브에이전트까지 훑는다 — 위임된 팀원만 가드레일 없이 도는 구멍을 막는다.
    팀원 프롬프트는 리더와 별도로 작성되므로 누락 가능성이 더 높다.
    """
    patched = {**data, "system_prompt": _with_guardrail(data.get("system_prompt"))}

    subagents = data.get("subagents")
    if isinstance(subagents, list):
        patched["subagents"] = [
            {**sub, "system_prompt": _with_guardrail(sub.get("system_prompt"))}
            if isinstance(sub, dict)
            else sub
            for sub in subagents
        ]
    return patched
