"""LangSmith 트레이싱 설정 (Phase 4).

LangChain은 환경변수만 맞으면 자동으로 트레이스를 보낸다. 이 모듈이 하는 일은
그 설정을 **읽어서 상태를 명시적으로 알려주는 것**이다.

왜 필요한가: 트레이싱이 조용히 꺼져 있는 것이 가장 나쁘다. 데모 도중
"왜 LangSmith에 아무것도 안 뜨지?"를 디버깅하게 된다. 키가 없는데 켜라고
요청받으면 실행 전에 알려준다 — web_search가 TAVILY_API_KEY 없을 때
결과를 지어내지 않고 에러를 반환하는 것과 같은 원칙이다.

환경변수 (신규 이름 우선, 없으면 레거시 이름):
- LANGSMITH_TRACING / LANGCHAIN_TRACING_V2 : "true"면 켠다
- LANGSMITH_API_KEY  / LANGCHAIN_API_KEY   : 키 (값은 절대 로그에 남기지 않는다)
- LANGSMITH_PROJECT  / LANGCHAIN_PROJECT   : 프로젝트 이름
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

DEFAULT_PROJECT = "deep-builder"

_TRACING_VARS = ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2")
_API_KEY_VARS = ("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY")
_PROJECT_VARS = ("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT")

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


class TracingConfigError(RuntimeError):
    """트레이싱을 켜라고 했는데 켤 수 없는 상태다."""


@dataclass(frozen=True)
class TracingStatus:
    """트레이싱 상태 요약. 사람이 읽을 수 있게 만드는 것이 목적이다."""

    requested: bool
    enabled: bool
    project: str | None
    detail: str

    def __str__(self) -> str:
        if self.enabled:
            return f"on (project={self.project})"
        return f"off ({self.detail})"


def _first_set(env: Mapping[str, str], names: tuple[str, ...]) -> str | None:
    """여러 이름 중 먼저 설정된 값을 돌려준다 (신규 이름 우선)."""
    for name in names:
        value = env.get(name)
        if value:
            return value
    return None


def tracing_status(env: Mapping[str, str] | None = None) -> TracingStatus:
    """환경변수를 읽어 트레이싱 상태를 판정한다. 부작용 없음."""
    env = os.environ if env is None else env

    raw = _first_set(env, _TRACING_VARS)
    requested = bool(raw) and raw.strip().lower() in _TRUE_VALUES
    if not requested:
        return TracingStatus(
            requested=False,
            enabled=False,
            project=None,
            detail="LANGSMITH_TRACING이 설정되지 않았다",
        )

    if not _first_set(env, _API_KEY_VARS):
        return TracingStatus(
            requested=True,
            enabled=False,
            project=None,
            detail="LANGSMITH_TRACING=true 인데 LANGSMITH_API_KEY가 없다",
        )

    project = _first_set(env, _PROJECT_VARS) or DEFAULT_PROJECT
    return TracingStatus(
        requested=True, enabled=True, project=project, detail="설정 완료"
    )


def configure_tracing(env: Mapping[str, str] | None = None) -> TracingStatus:
    """트레이싱 설정을 검증하고 프로젝트 이름을 프로세스 환경에 채운다.

    LangChain 자체가 환경변수를 직접 읽으므로 여기서 클라이언트를 만들지 않는다.
    이 함수의 값어치는 "켜달라고 했는데 안 켜지는 상태"를 실행 전에 잡는 것이다.

    Raises:
        TracingConfigError: 트레이싱을 요청했는데 API 키가 없을 때.
    """
    status = tracing_status(env)

    if status.requested and not status.enabled:
        raise TracingConfigError(
            f"{status.detail}. 키를 설정하거나 LANGSMITH_TRACING을 끄세요 "
            "(https://smith.langchain.com 에서 발급)."
        )

    # 프로젝트 이름이 비어 있으면 LangSmith가 'default'에 몰아넣는다. 명시해 둔다.
    if status.enabled and not _first_set(os.environ, _PROJECT_VARS):
        os.environ["LANGSMITH_PROJECT"] = status.project or DEFAULT_PROJECT

    return status
