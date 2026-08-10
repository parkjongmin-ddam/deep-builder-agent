"""에이전트 응답 메시지 다루기.

Phase 4에서 cli.py 밖으로 꺼냈다. UI도 같은 추출 로직이 필요한데
`ui`가 `cli`를 임포트하는 것은 레이어가 거꾸로다.

LangChain 메시지의 `content`는 문자열일 수도, 블록 리스트일 수도 있다
(도구 호출이 섞이면 후자). 그 차이를 여기서 흡수한다.
"""

from __future__ import annotations

NO_TEXT_RESPONSE = "(에이전트가 텍스트 응답을 내지 않았습니다)"


def message_text(message) -> str:
    """메시지 하나에서 텍스트를 뽑는다. 텍스트가 없으면 빈 문자열.

    메시지 종류(ai/human/tool)를 가리지 않는다 — 걸러내는 일은 호출자 몫이다.
    """
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def last_text(messages: list) -> str:
    """메시지 목록에서 마지막 AI 텍스트 응답을 뽑는다.

    텍스트 없이 도구만 호출한 AI 메시지는 건너뛰고 더 뒤로 거슬러 올라간다.
    """
    for message in reversed(messages):
        if getattr(message, "type", None) != "ai":
            continue
        text = message_text(message)
        if text.strip():
            return text
    return NO_TEXT_RESPONSE
