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

from builder.prompts import RETRY_FEEDBACK_TEMPLATE, build_system_prompt
from runtime.config import env_or_default

# 가드레일은 runtime/에 산다 — Builder 루프뿐 아니라 `--spec`·UI 경로도 같은 보장을
# 받아야 하기 때문이다. 여기서 재수출해 기존 임포터(`from builder.builder import
# ensure_guardrail`)를 깨뜨리지 않는다.
from runtime.guardrail import ensure_guardrail
from runtime.spec import AgentSpec

# Builder용 모델. 생성되는 에이전트의 모델(AgentSpec.model)과 분리한다.
# env_or_default를 쓰는 이유는 runtime/config.py 참조 — 빈 환경변수도 미설정으로 본다.
DEFAULT_BUILDER_MODEL = env_or_default("DEEP_BUILDER_MODEL", "claude-sonnet-4-6")

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


def _cached_system_message():
    """시스템 프롬프트를 **프롬프트 캐시 대상**으로 표시해 만든다.

    Builder 프롬프트는 약 2,800토큰이고 호출마다 통째로 다시 전송된다.
    평가는 케이스 수만큼 Builder를 연속 호출하므로(현재 12회) 같은 프롬프트가
    12번 청구된다. 캐시를 걸면 2번째 호출부터 정가의 10%로 읽는다.

    재시도로 덧붙는 user/assistant 메시지는 튜플 형식을 그대로 둔다 —
    캐시 breakpoint는 프리픽스(system)에만 있으면 되고, 뒤쪽이 바뀌어도
    앞쪽 캐시는 유효하다.
    """
    from langchain_core.messages import SystemMessage

    return SystemMessage(
        content=[
            {
                "type": "text",
                "text": build_system_prompt(),
                "cache_control": {"type": "ephemeral"},
            }
        ]
    )


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
        _cached_system_message(),
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
