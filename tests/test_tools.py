"""도구 구현 테스트.

python_repl의 UTF-8 케이스는 회귀 테스트다: subprocess가 로케일 코덱(Windows cp949)으로
디코딩하면 한글 출력이 UnicodeDecodeError로 유실되어, 에이전트가 도구 결과를 못 받는다.
"""

from registry.builtin import (
    PYTHON_REPL_MAX_OUTPUT_CHARS,
    _truncate,
    python_repl,
    web_search,
)


def _run(code: str) -> str:
    return python_repl.invoke({"code": code})


def test_python_repl_returns_stdout():
    assert "stdout:\n4\n" in _run("print(2 + 2)")


def test_python_repl_handles_non_ascii_output():
    """Windows cp949 환경에서도 한글·이모지 출력이 온전히 돌아와야 한다."""
    assert "한글 출력 테스트 ✅" in _run('print("한글 출력 테스트 ✅")')


def test_python_repl_reports_nonzero_exit():
    assert "exit_code: 3" in _run("import sys; sys.exit(3)")


def test_python_repl_reports_stderr():
    out = _run("raise ValueError('boom')")
    assert "stderr:" in out
    assert "ValueError" in out


def test_python_repl_no_output():
    assert _run("x = 1") == "(no output)"


def test_python_repl_truncates_large_output():
    out = _run(f"print('x' * {PYTHON_REPL_MAX_OUTPUT_CHARS * 2})")
    assert "truncated" in out
    assert len(out) < PYTHON_REPL_MAX_OUTPUT_CHARS * 2


def test_truncate_leaves_short_text_alone():
    assert _truncate("short", 100) == "short"


def test_web_search_without_key_returns_actionable_error(monkeypatch):
    """키가 없으면 조용히 실패하지 말고, 모델이 지어내지 않도록 명시적으로 알린다."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    out = web_search.invoke({"query": "latest IT news"})
    assert out.startswith("Error:")
    assert "TAVILY_API_KEY" in out
