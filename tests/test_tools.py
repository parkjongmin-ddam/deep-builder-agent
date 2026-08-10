"""도구 구현 테스트.

python_repl의 UTF-8 케이스는 회귀 테스트다: subprocess가 로케일 코덱(Windows cp949)으로
디코딩하면 한글 출력이 UnicodeDecodeError로 유실되어, 에이전트가 도구 결과를 못 받는다.
"""

import pytest

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


# --- 비밀값 격리 -----------------------------------------------------------
#
# python_repl은 임의 코드를 실행한다(`os.system`도 된다). 예전에는 부모 환경을
# 통째로(`{**os.environ}`) 물려줘서 실행 코드가 `os.environ["ANTHROPIC_API_KEY"]`로
# 키를 그대로 읽을 수 있었다 — 실측으로 확인하고 화이트리스트로 바꿨다.

SYNTHETIC_SECRET = "sk-ant-SYNTHETIC-not-a-real-key"

SECRET_VARS = ["ANTHROPIC_API_KEY", "TAVILY_API_KEY", "LANGSMITH_API_KEY"]


@pytest.mark.parametrize("var", SECRET_VARS)
def test_python_repl_does_not_leak_parent_env(var, monkeypatch):
    """부모 프로세스의 비밀값이 자식에게 넘어가면 안 된다."""
    monkeypatch.setenv(var, SYNTHETIC_SECRET)

    out = _run(f'import os; print(os.environ.get("{var}", "ABSENT"))')

    assert SYNTHETIC_SECRET not in out
    assert "ABSENT" in out


def test_python_repl_env_is_a_small_whitelist(monkeypatch):
    """통과 목록이 조용히 늘어나면 여기서 걸린다."""
    monkeypatch.setenv("SOME_UNRELATED_SECRET", SYNTHETIC_SECRET)

    out = _run("import os; print(sorted(os.environ))")

    assert "SOME_UNRELATED_SECRET" not in out
    assert "PYTHONUTF8" in out  # 인코딩 고정은 유지되어야 한다


def test_python_repl_still_runs_after_env_restriction():
    """격리 때문에 인터프리터가 못 뜨면 도구가 무용지물이 된다."""
    assert "stdout:\n5050\n" in _run("print(sum(range(1, 101)))")


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
