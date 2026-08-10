"""실행 전 환경 점검 — 무엇이 준비됐고 무엇이 막고 있는가.

**왜 `ui/`가 아니라 `runtime/`인가**: 원래 `ui/state.py`에 있었고 UI만 이 점검을
했다. 그래서 CLI는 키가 없어도 대화 화면까지 들어간 뒤, 사용자가 질문을 던지는
순간 SDK 원시 오류로 죽었다 — `ANTHROPIC_API_KEY`도 `.env`도 언급되지 않는
`TypeError: Could not resolve authentication method...` 하나였다.

`.env` 로드·콘솔 인코딩과 **같은 실패 계열**이다: 진입점마다 각자 챙기면
새 진입점에서 반드시 빠진다. `cli`가 `ui`를 임포트하는 것은 레이어가 거꾸로이므로
아래층인 여기에 둔다.

비밀값은 **존재 여부만** 본다. 값을 읽어 화면·로그에 흘리지 않는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from registry.mcp import configured_server_names
from runtime.tracing import tracing_status


@dataclass(frozen=True)
class ReadinessItem:
    """환경 점검 항목 하나."""

    label: str
    ok: bool
    detail: str
    required: bool = False


def check_readiness(env: Mapping[str, str] | None = None) -> list[ReadinessItem]:
    """실행 전에 무엇이 준비됐는지 점검한다.

    비밀값은 **존재 여부만** 본다. 값을 읽어 화면에 흘리지 않는다.
    """
    env = os.environ if env is None else env

    trace = tracing_status(env)
    servers = sorted(configured_server_names())

    return [
        ReadinessItem(
            label="ANTHROPIC_API_KEY",
            ok=bool(env.get("ANTHROPIC_API_KEY")),
            detail="Builder와 생성된 에이전트 실행에 필요",
            required=True,
        ),
        ReadinessItem(
            label="TAVILY_API_KEY",
            ok=bool(env.get("TAVILY_API_KEY")),
            detail="web_search 도구용. 없으면 도구가 명확한 에러를 반환한다",
        ),
        ReadinessItem(
            label="LangSmith 트레이싱",
            ok=trace.enabled,
            detail=str(trace),
        ),
        ReadinessItem(
            label="MCP 서버",
            ok=bool(servers),
            detail=", ".join(servers) if servers else "mcp_servers.json 없음",
        ),
    ]


def blocking_problems(items: list[ReadinessItem]) -> list[str]:
    """실행을 막는 항목만 추린다. 선택 항목은 경고일 뿐 차단하지 않는다."""
    return [item.label for item in items if item.required and not item.ok]


def readiness_error(missing: list[str]) -> str:
    """막힌 이유와 **고치는 방법**을 함께 알려준다.

    "키가 없습니다"만으로는 처음 쓰는 사람이 무엇을 해야 할지 모른다.
    """
    names = ", ".join(missing)
    return (
        f"필수 환경변수가 설정되지 않았습니다: {names}\n"
        "        1) cp .env.example .env\n"
        "        2) .env 를 열어 ANTHROPIC_API_KEY= 뒤에 키를 붙여넣으세요\n"
        "        키 발급: https://console.anthropic.com/settings/keys"
    )
