"""환경변수 읽기 헬퍼.

`os.environ.get(name, default)`의 기본값은 키가 **없을 때만** 적용된다.
`.env.example`을 복사하면 `DEEP_BUILDER_MODEL=`처럼 값이 빈 키가 생기므로
기본값이 무시되고 빈 문자열이 그대로 흘러간다 — README가 안내하는
`cp .env.example .env` 경로에서 실제로 발생한 버그다.

여기서는 **비어 있거나 공백뿐인 값도 미설정으로 본다.**
"""

from __future__ import annotations

import os
from pathlib import Path

# 에이전트가 실제 디스크를 읽을 수 있는 유일한 디렉터리.
# 프로젝트 루트가 아니라 전용 하위 디렉터리인 것이 핵심 — .env를 비롯한
# 비밀값은 이 밖에 있어야 한다 (BUILD_SPEC "파일 백엔드" 결정 참조).
DEFAULT_WORKSPACE = "workspace"


def load_env() -> None:
    """`.env`를 읽어 환경변수에 올린다. 모든 진입점이 가장 먼저 호출한다.

    진입점마다 `load_dotenv()`를 따로 부르던 것을 여기로 모았다.
    빠뜨리면 키가 있는데도 "미설정"으로 취급되는데, 그 증상이 진입점마다
    다르게 나타난다 — CLI는 인증 오류, UI는 사이드바가 실행을 막는다.

    이미 설정된 환경변수는 덮어쓰지 않는다(`.env`보다 셸 환경이 우선).
    """
    from dotenv import load_dotenv

    load_dotenv()


def env_or_default(name: str, default: str) -> str:
    """환경변수를 읽되, 비었거나 공백뿐이면 기본값을 돌려준다.

    Args:
        name: 환경변수 이름.
        default: 미설정으로 판단됐을 때 쓸 값.
    """
    return os.environ.get(name, "").strip() or default


def workspace_dir() -> Path:
    """에이전트가 파일을 읽고 쓸 수 있는 디렉터리. 없으면 만든다.

    `DEEP_BUILDER_WORKSPACE`로 바꿀 수 있다(기본 `workspace`).

    **이 디렉터리에 비밀값을 두지 않는다.** 에이전트가 읽을 수 있는 유일한
    경로이며, 경로 탈출은 라이브러리가 막지만 안에 있는 것은 전부 읽힌다.
    """
    path = Path(env_or_default("DEEP_BUILDER_WORKSPACE", DEFAULT_WORKSPACE)).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path
