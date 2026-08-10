"""UI 로직 테스트 — Streamlit 없이 판단 부분만 검증한다.

`ui/app.py`는 그리기만 하므로 테스트하지 않는다. 판단이 들어 있는
`ui/state.py`가 대상이다.
"""

from pathlib import Path

import pytest

from builder.prompts import GUARDRAIL_SENTENCE
from runtime.spec import AgentSpec
from ui.state import (
    agent_reply,
    append_turn,
    blocking_problems,
    check_readiness,
    render_history,
    spec_overview,
    team_rows,
)

APP_PATH = Path(__file__).resolve().parent.parent / "ui" / "app.py"

READY_ENV = {
    "ANTHROPIC_API_KEY": "synthetic-key",
    "TAVILY_API_KEY": "synthetic-key",
    "LANGSMITH_TRACING": "true",
    "LANGSMITH_API_KEY": "synthetic-key",
}


def _spec(**over) -> AgentSpec:
    d = dict(
        name="news_agent",
        description="뉴스 요약",
        system_prompt=f"너는 요약가다. {GUARDRAIL_SENTENCE}",
        tools=["web_search"],
    )
    d.update(over)
    return AgentSpec(**d)


class FakeMessage:
    def __init__(self, type_: str, content):
        self.type = type_
        self.content = content


class FakeAgent:
    def __init__(self, messages=None, error: Exception | None = None):
        self._messages = messages or []
        self._error = error

    def invoke(self, _payload):
        if self._error is not None:
            raise self._error
        return {"messages": self._messages}


# --- 환경 점검 -------------------------------------------------------------


def test_missing_anthropic_key_blocks_execution():
    items = check_readiness({})

    assert "ANTHROPIC_API_KEY" in blocking_problems(items)


def test_optional_keys_do_not_block():
    """Tavily·트레이싱이 없다고 앱을 막지는 않는다."""
    items = check_readiness({"ANTHROPIC_API_KEY": "synthetic-key"})

    assert blocking_problems(items) == []


def test_ready_environment_has_no_blockers():
    assert blocking_problems(check_readiness(READY_ENV)) == []


def test_readiness_never_exposes_secret_values():
    """화면에 키 값이 새면 안 된다. 존재 여부만 다룬다."""
    rendered = " ".join(
        f"{item.label} {item.detail}" for item in check_readiness(READY_ENV)
    )

    assert "synthetic-key" not in rendered


# --- 스펙 표시 -------------------------------------------------------------


def test_spec_overview_flattens_fields():
    overview = spec_overview(_spec())

    assert overview["name"] == "news_agent"
    assert overview["tools"] == "web_search"
    assert overview["subagents"] == "(none)"


def test_team_rows_empty_for_solo_agent():
    assert team_rows(_spec()) == []


def test_team_rows_list_members():
    spec = _spec(
        subagents=[
            {
                "name": "researcher",
                "description": "조사",
                "system_prompt": f"조사하라. {GUARDRAIL_SENTENCE}",
                "tools": ["web_search"],
            }
        ]
    )

    rows = team_rows(spec)

    assert rows[0]["name"] == "researcher"
    assert rows[0]["tools"] == "web_search"


# --- 대화 상태 -------------------------------------------------------------


def test_append_turn_does_not_mutate_history():
    """Streamlit은 매 실행마다 상태를 다시 읽는다. 제자리 변경은 버그가 된다."""
    original: list = []

    updated = append_turn(original, "안녕")

    assert original == []
    assert updated == [{"role": "user", "content": "안녕"}]


def test_agent_reply_returns_text():
    agent = FakeAgent([FakeMessage("ai", "안녕하세요")])

    history, reply = agent_reply(agent, [])

    assert reply == "안녕하세요"
    assert len(history) == 1


def test_agent_failure_becomes_a_message_not_an_exception():
    agent = FakeAgent(error=RuntimeError("모델 오류"))

    history, reply = agent_reply(agent, [{"role": "user", "content": "안녕"}])

    assert reply.startswith("[error]")
    assert "모델 오류" in reply
    assert history == [{"role": "user", "content": "안녕"}]


def test_render_history_handles_dicts_and_messages():
    history = [
        {"role": "user", "content": "안녕"},
        FakeMessage("ai", "반갑습니다"),
    ]

    assert render_history(history) == [
        ("user", "안녕"),
        ("assistant", "반갑습니다"),
    ]


def test_render_history_skips_tool_only_turns():
    """도구만 호출하고 텍스트가 없는 턴은 화면에 띄우지 않는다."""
    history = [
        FakeMessage("ai", [{"type": "tool_use", "name": "web_search"}]),
        FakeMessage("tool", "검색 결과"),
        FakeMessage("ai", [{"type": "text", "text": "찾았습니다"}]),
    ]

    assert render_history(history) == [("assistant", "찾았습니다")]


def test_render_history_reads_human_messages():
    """human 메시지도 텍스트가 나와야 한다 (ai 전용 추출을 쓰면 깨진다)."""
    assert render_history([FakeMessage("human", "질문입니다")]) == [
        ("user", "질문입니다")
    ]


# --- 앱 렌더링 -------------------------------------------------------------


@pytest.mark.integration
def test_streamlit_app_renders_without_exceptions(monkeypatch):
    """`streamlit run ui/app.py`가 실제로 뜨는지 확인한다.

    state.py 단위 테스트가 전부 통과해도 app.py의 위젯 호출이 깨져 있으면
    앱은 열리지 않는다. 느려서 integration 마커로 분리한다.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = AppTest.from_file(str(APP_PATH), default_timeout=60).run()

    assert not app.exception, [e.value for e in app.exception]
    assert app.title[0].value == "deep_builder_agent"
    assert len(app.tabs) == 2  # 빌더 / 평가


@pytest.mark.integration
def test_loading_a_template_opens_the_chat_panel(monkeypatch):
    """템플릿을 불러오면 대화 패널이 떠야 한다.

    다른 렌더링 테스트는 **키 없는 차단 상태**만 덮는다 — 그 경로에서는
    agent가 None이라 `render_chat_panel`이 조기 반환하고, 컬럼 안의
    `st.chat_input`은 한 번도 실행되지 않는다. 사용자가 실제로 밟는 경로다.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    pytest.importorskip("deepagents")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    app = AppTest.from_file(str(APP_PATH), default_timeout=90).run()
    app.selectbox[0].set_value("data_analysis_team").run()
    loaded = [b for b in app.button if "불러오기" in b.label][0].click().run()

    assert not loaded.exception, [e.value for e in loaded.exception]
    assert loaded.chat_input, "대화 입력창이 렌더링되지 않았다"
    assert any("data_analysis_team" in s.value for s in loaded.success)


@pytest.mark.integration
def test_app_blocks_execution_without_api_key(monkeypatch):
    """키가 없으면 실행을 막고 그 사실을 화면에 알려야 한다.

    앱은 시작 시 `.env`를 로드하므로, 개발자 머신의 실제 키가 새어 들어오지
    않도록 로더를 no-op으로 막는다. 이 격리가 없으면 테스트가 환경에 따라
    통과했다 실패했다 한다.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

    monkeypatch.setattr("runtime.config.load_env", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = AppTest.from_file(str(APP_PATH), default_timeout=60).run()

    messages = [e.value for e in app.sidebar.error]
    assert any("ANTHROPIC_API_KEY" in m for m in messages), messages
