"""내장 커스텀 도구 구현.

Phase 1의 runtime/tools.py에서 이관했다. file_read/file_write는 deepagents
내장 파일시스템 도구로 위임하므로(registry.BUILTIN_FS_TOOLS) 여기에는
직접 구현이 필요한 도구만 둔다.

각 도구의 설명 첫 줄은 Builder 프롬프트의 도구 목록에 그대로 노출된다
(`registry.tool_catalog()`). 모델이 읽는 문장이므로 무엇을 하는 도구인지 명확히 쓴다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from langchain_core.tools import tool

from registry.registry import register_tool

# python_repl 실행 제한. 무한 루프/폭주 스크립트를 차단한다.
PYTHON_REPL_TIMEOUT_SECONDS = 30
PYTHON_REPL_MAX_OUTPUT_CHARS = 10_000

# 자식 프로세스에 넘길 환경변수 **화이트리스트**.
#
# 예전에는 `{**os.environ, ...}`로 부모 환경을 통째로 물려줬다. 그러면 실행되는
# 코드가 `os.environ["ANTHROPIC_API_KEY"]`로 키를 그대로 읽는다 — 실측으로 확인했다.
# python_repl은 임의 파이썬을 실행하므로(`os.system`도 된다) 환경변수는
# "에이전트가 읽을 수 있는 값"으로 봐야 한다. 필요한 것만 넘긴다.
#
# 인터프리터 구동에 필요한 최소 항목만 통과시킨다. 비밀값 이름을 여기에 추가하지 않는다.
_REPL_ENV_PASSTHROUGH = (
    "PATH",  # 인터프리터·표준 도구 탐색
    "SYSTEMROOT",  # Windows: 없으면 socket/ssl 초기화가 깨진다
    "COMSPEC",
    "TEMP",
    "TMP",
    "TMPDIR",
    "LANG",
    "LC_ALL",
)


def _repl_env() -> dict[str, str]:
    """python_repl 자식 프로세스에 넘길 환경. 비밀값은 넘기지 않는다."""
    env = {k: os.environ[k] for k in _REPL_ENV_PASSTHROUGH if k in os.environ}
    # 자식 프로세스 I/O를 UTF-8로 고정한다. text=True의 기본값은 로케일 코덱이라
    # Windows(cp949)에서 한글 출력이 UnicodeDecodeError로 유실된다.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env

# web_search 기본 결과 수.
WEB_SEARCH_MAX_RESULTS = 5


def _truncate(text: str, limit: int) -> str:
    """도구 출력이 컨텍스트를 잠식하지 않도록 자른다."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated, {len(text) - limit} chars omitted]"


@register_tool("python_repl")
@tool
def python_repl(code: str) -> str:
    """별도 파이썬 프로세스에서 코드를 실행하고 stdout/stderr를 반환한다.

    Args:
        code: 실행할 파이썬 소스 코드. 결과는 print로 출력해야 보인다.

    보안 주의 — 이 도구는 **임의 코드 실행**이다. 샌드박스가 아니다.
    임시 디렉터리에서 실행하고 비밀값 환경변수를 넘기지 않으며 30초에 끊지만,
    `os.system`·`subprocess`·절대경로 파일 접근·네트워크는 여전히 가능하다.
    스펙에 이 도구를 넣는 것은 그 권한을 주는 것과 같다.
    (deepagents의 `execute`를 차단해도 이 도구가 열려 있으면 셸은 열린 셈이다)
    """
    with tempfile.TemporaryDirectory(prefix="deep_builder_repl_") as workdir:
        try:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=_repl_env(),
                timeout=PYTHON_REPL_TIMEOUT_SECONDS,
                cwd=workdir,
            )
        except subprocess.TimeoutExpired:
            return f"Error: execution exceeded {PYTHON_REPL_TIMEOUT_SECONDS}s and was terminated."

    parts: list[str] = []
    if completed.stdout:
        parts.append(f"stdout:\n{completed.stdout}")
    if completed.stderr:
        parts.append(f"stderr:\n{completed.stderr}")
    if completed.returncode != 0:
        parts.append(f"exit_code: {completed.returncode}")
    if not parts:
        return "(no output)"
    return _truncate("\n".join(parts), PYTHON_REPL_MAX_OUTPUT_CHARS)


@register_tool("web_search")
@tool
def web_search(query: str) -> str:
    """웹을 검색해 상위 결과의 제목·URL·요약을 반환한다.

    Args:
        query: 검색어. 자연어 질문 형태를 권장한다.
    """
    if not os.environ.get("TAVILY_API_KEY"):
        return (
            "Error: web_search is unavailable because TAVILY_API_KEY is not set. "
            "Set it in the environment or .env file, then retry. "
            "Do not answer from memory as if a search had succeeded."
        )

    from langchain_tavily import TavilySearch

    search = TavilySearch(max_results=WEB_SEARCH_MAX_RESULTS)
    try:
        payload = search.invoke({"query": query})
    except Exception as exc:  # noqa: BLE001 - 도구 실패는 모델에게 문자열로 전달한다
        return f"Error: web search failed ({type(exc).__name__}: {exc})"

    results = payload.get("results", []) if isinstance(payload, dict) else []
    if not results:
        return f"No results for {query!r}."

    lines: list[str] = []
    for index, item in enumerate(results, start=1):
        title = item.get("title", "(no title)")
        url = item.get("url", "")
        content = (item.get("content") or "").strip()
        lines.append(f"{index}. {title}\n   {url}\n   {content}")
    return _truncate("\n".join(lines), PYTHON_REPL_MAX_OUTPUT_CHARS)
