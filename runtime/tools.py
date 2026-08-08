"""Phase 1 내장 도구 구현.

설계 원칙:
- AgentSpec의 도구 키(문자열)와 실제 구현을 이 모듈에서 연결한다.
- file_read/file_write는 deepagents 내장 파일시스템 도구로 위임한다(factory.BUILTIN_FS_TOOLS).
  따라서 여기에는 커스텀 도구(web_search, python_repl)만 구현한다.
- Phase 2에서 registry/ 모듈로 이관한다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from langchain_core.tools import tool

from runtime.factory import register_tool

# python_repl 실행 제한. 무한 루프/폭주 스크립트를 차단한다.
PYTHON_REPL_TIMEOUT_SECONDS = 30
PYTHON_REPL_MAX_OUTPUT_CHARS = 10_000

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
    """격리된 파이썬 프로세스에서 코드를 실행하고 stdout/stderr를 반환한다.

    Args:
        code: 실행할 파이썬 소스 코드. 결과는 print로 출력해야 보인다.
    """
    # 자식 프로세스 I/O를 UTF-8로 고정한다. text=True의 기본값은 로케일 코덱이라
    # Windows(cp949)에서 한글 출력이 UnicodeDecodeError로 유실된다.
    child_env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

    with tempfile.TemporaryDirectory(prefix="deep_builder_repl_") as workdir:
        try:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=child_env,
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
