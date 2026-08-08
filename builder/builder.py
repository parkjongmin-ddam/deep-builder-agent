"""Builder 루프: 자연어 요구 → AgentSpec JSON → 검증 → 실패 시 재시도.

하네스 구조 (BUILD_SPEC "제품 층위"):
1. LLM이 JSON을 생성한다.
2. 코드가 JSON을 파싱하고 가드레일 문장을 주입한다.
3. Pydantic(AgentSpec)이 도구 화이트리스트·subagents 게이트를 검증한다.
4. 검증 실패 시 에러 메시지를 Builder에게 되돌려 재생성한다 (기본 최대 2회).

LLM이 제약을 지키리라 신뢰하지 않는다. 프롬프트는 요청이고, 검증이 강제다.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from pydantic import ValidationError

from builder.prompts import (
    BUILDER_SYSTEM_PROMPT,
    GUARDRAIL_SENTENCE,
    RETRY_FEEDBACK_TEMPLATE,
)
from runtime.spec import AgentSpec

# Builder용 모델. 생성되는 에이전트의 모델(AgentSpec.model)과 분리한다.
DEFAULT_BUILDER_MODEL = os.environ.get("DEEP_BUILDER_MODEL", "claude-sonnet-4-6")

# 검증 실패 시 Builder에게 되돌리는 최대 재시도 횟수.
DEFAULT_MAX_RETRIES = 2

# 생성된 스펙 저장 위치 (Phase 1 결정: 파일 저장).
SPECS_DIR = Path("specs")

_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


class SpecGenerationError(RuntimeError):
    """재시도를 모두 소진하고도 유효한 AgentSpec을 얻지 못했다."""


def extract_json(text: str) -> dict:
    """LLM 응답 문자열에서 최상위 JSON 객체를 추출한다.

    코드펜스나 앞뒤 설명이 섞여 나와도 첫 번째 균형 잡힌 `{...}` 블록을 회수한다.
    """
    stripped = _CODE_FENCE_RE.sub("", text).strip()

    start = stripped.find("{")
    if start == -1:
        raise ValueError("no JSON object found in builder output")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(stripped)):
        char = stripped[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(stripped[start : index + 1])

    raise ValueError("unterminated JSON object in builder output")


def ensure_guardrail(data: dict) -> dict:
    """system_prompt에 가드레일 문장이 없으면 주입한 새 dict를 반환한다.

    원본을 변경하지 않는다. Builder가 프롬프트 지시를 어겨도 제품 층위에서 보장된다.
    """
    system_prompt = data.get("system_prompt")
    if not isinstance(system_prompt, str) or GUARDRAIL_SENTENCE in system_prompt:
        return dict(data)
    return {**data, "system_prompt": f"{system_prompt.rstrip()}\n\n{GUARDRAIL_SENTENCE}"}


def _build_chat_model(model: str):
    """Builder용 채팅 모델을 생성한다. 지연 임포트로 테스트 부담을 줄인다."""
    from langchain.chat_models import init_chat_model

    return init_chat_model(model)


def _message_text(response) -> str:
    """LangChain 응답 메시지에서 텍스트를 뽑는다 (content가 블록 리스트인 경우 포함)."""
    content = response.content
    if isinstance(content, str):
        return content
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "".join(parts)


def generate_spec(
    request: str,
    *,
    model: str = DEFAULT_BUILDER_MODEL,
    max_retries: int = DEFAULT_MAX_RETRIES,
    chat_model=None,
) -> AgentSpec:
    """자연어 요구로부터 검증된 AgentSpec을 생성한다.

    Args:
        request: 사용자의 자연어 요구.
        model: Builder LLM 모델 ID. `chat_model`이 주어지면 무시된다.
        max_retries: 검증 실패 시 추가 재시도 횟수.
        chat_model: 테스트용 주입 지점. LangChain BaseChatModel 호환 객체.

    Raises:
        SpecGenerationError: 모든 시도가 실패한 경우. 마지막 원인을 __cause__로 전달한다.
    """
    llm = chat_model if chat_model is not None else _build_chat_model(model)

    messages: list = [
        ("system", BUILDER_SYSTEM_PROMPT),
        ("user", request),
    ]

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        response = llm.invoke(messages)
        raw = _message_text(response)

        try:
            return AgentSpec(**ensure_guardrail(extract_json(raw)))
        except (ValueError, ValidationError) as exc:
            last_error = exc
            if attempt == max_retries:
                break
            messages = [
                *messages,
                ("assistant", raw),
                ("user", RETRY_FEEDBACK_TEMPLATE.format(error=exc)),
            ]

    raise SpecGenerationError(
        f"failed to produce a valid AgentSpec after {max_retries + 1} attempts"
    ) from last_error


def save_spec(spec: AgentSpec, directory: Path = SPECS_DIR) -> Path:
    """검증된 스펙을 `<directory>/<name>.json`에 저장하고 경로를 반환한다."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{spec.name}.json"
    path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    return path
