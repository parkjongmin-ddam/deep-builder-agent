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


def test_readiness_rows_html_covers_three_states():
    """시안 5a의 환경 점검 3단계: 정상 / 경고 / 필수 누락 — 상태 라벨 우측 정렬 그리드."""
    from runtime.readiness import ReadinessItem
    from ui.state import readiness_rows_html

    out = readiness_rows_html(
        [
            ReadinessItem(label="KEY", ok=True, detail="필요한 이유", required=True),
            ReadinessItem(label="OPT", ok=False, detail="", required=False),
            ReadinessItem(label="REQ", ok=False, detail="", required=True),
        ]
    )

    assert out.count('class="dba-env__row"') == 3
    assert "check_circle" in out and "정상" in out
    assert "error" in out and "경고" in out
    assert "cancel" in out and "필수 누락" in out
    assert "필요한 이유" in out


def test_readiness_rows_html_escapes_labels():
    from runtime.readiness import ReadinessItem
    from ui.state import readiness_rows_html

    out = readiness_rows_html(
        [ReadinessItem(label="<KEY>", ok=True, detail="<detail>", required=True)]
    )

    assert "&lt;KEY&gt;" in out and "<KEY>" not in out
    assert "&lt;detail&gt;" in out


def test_user_card_html_shows_initials_and_plain_email():
    """이메일이 마크다운 자동 링크로 변하면 안 된다 — HTML 일반 텍스트로 그린다."""
    from ui.state import user_card_html

    out = user_card_html("user01@example.com")

    assert 'class="dba-user__avatar">PJ<' in out
    assert "user01@example.com" in out
    assert "Okta · OIDC" in out
    assert "href" not in out


def test_user_card_html_handles_nameless_local_part():
    from ui.state import user_card_html

    assert 'class="dba-user__avatar">?<' in user_card_html("754@example.com")


def test_eval_case_icon_maps_pass_and_fail():
    """expander icon 파라미터는 색 지시자 없이 아이콘 이름만 받는다 (Phase 8)."""
    from ui.state import eval_case_icon

    assert eval_case_icon(True) == ":material/check_circle:"
    assert eval_case_icon(False) == ":material/cancel:"


def test_readiness_never_exposes_secret_values():
    """화면에 키 값이 새면 안 된다. 존재 여부만 다룬다."""
    rendered = " ".join(
        f"{item.label} {item.detail}" for item in check_readiness(READY_ENV)
    )

    assert "synthetic-key" not in rendered


# --- 배지·칩·요약 (Phase 8 단계 2) ------------------------------------------


def test_badges_html_renders_and_escapes():
    """도구 키를 배지 span으로. 외부 입력이 아니어도 이스케이프는 기본이다."""
    from ui.state import badges_html

    out = badges_html(["web_search", "<b>"])

    assert out.count('class="dba-badge"') == 2
    assert "web_search" in out
    assert "&lt;b&gt;" in out and "<b>" not in out


def test_badges_html_accent_variant():
    from ui.state import badges_html

    assert 'dba-badge--accent' in badges_html(["builder"], accent=True)


def test_chips_html_solid_and_dashed():
    from ui.state import chips_html

    solid = chips_html(["create_agent"])
    dashed = chips_html(["calculate"], dashed=True)

    assert 'class="dba-chip"' in solid and "--dashed" not in solid
    assert 'class="dba-chip dba-chip--dashed"' in dashed


def test_readiness_summary_three_states():
    """사이드바 요약 필: 실행 가능(녹) / 실행 가능·경고 n / 실행 불가 (시안 5a)."""
    from runtime.readiness import ReadinessItem
    from ui.state import readiness_summary

    ok = ReadinessItem(label="A", ok=True, detail="", required=True)
    warn = ReadinessItem(label="B", ok=False, detail="", required=False)
    missing = ReadinessItem(label="C", ok=False, detail="", required=True)

    assert readiness_summary([ok]) == "실행 가능"
    assert readiness_summary([ok, warn, warn]) == "실행 가능 · 경고 2"
    assert readiness_summary([ok, missing]) == "실행 불가"


def test_badge_palette_css_follows_detected_theme():
    """st.context.theme을 읽을 수 있으면 배지 색을 그 테마로 고정한다 (Phase 8 보완).

    감지 불가(None)면 prefers-color-scheme 미디어 쿼리로 폴백한다.
    """
    from ui.style import badge_palette_css

    dark = badge_palette_css("dark")
    light = badge_palette_css("light")
    fallback = badge_palette_css(None)

    assert "#6AA8FF" in dark and "@media" not in dark
    assert "#1F6FD1" in light and "@media" not in light
    assert "prefers-color-scheme" in fallback


def test_denial_reason_names_role_and_action():
    """권한 비활성 버튼 옆 사유 한 줄 (시안 5a) — 행위별 한국어 술어."""
    from runtime.iam import ACTION_CREATE, ACTION_REVISE, ACTION_RUN, load_iam_config
    from ui.state import denial_reason

    viewer = load_iam_config().resolve("demo_viewer")

    assert denial_reason(viewer, ACTION_CREATE) == "viewer 역할은 에이전트를 생성할 수 없습니다"
    assert "수정할 수 없습니다" in denial_reason(viewer, ACTION_REVISE)
    assert "실행할 수 없습니다" in denial_reason(viewer, ACTION_RUN)


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


def demo_mode_apptest(AppTest, timeout: int = 60):
    """개발자 로컬 `.streamlit/secrets.toml`(OIDC 설정)에 오염되지 않는 AppTest.

    AppTest는 secrets가 **비어 있으면** 실제 secrets 파일을 그대로 읽는다
    (설치본 streamlit/testing/v1/app_test.py의 `if self.secrets:` 분기 실측).
    Phase 7 실측 후 실제 secrets.toml이 생기자 UI 테스트 전건이 OIDC 로그인
    게이트를 렌더링하며 깨졌다 — 비어 있지 않은 더미를 넣어 st.secrets를
    대체시키면 [auth]가 없으므로 앱은 데모 모드로 뜬다.
    """
    app = AppTest.from_file(str(APP_PATH), default_timeout=timeout)
    app.secrets["_isolated_from_local_secrets"] = True
    return app


@pytest.mark.integration
def test_streamlit_app_renders_without_exceptions(monkeypatch):
    """`streamlit run ui/app.py`가 실제로 뜨는지 확인한다.

    state.py 단위 테스트가 전부 통과해도 app.py의 위젯 호출이 깨져 있으면
    앱은 열리지 않는다. 느려서 integration 마커로 분리한다.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = demo_mode_apptest(AppTest).run()

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

    app = demo_mode_apptest(AppTest, timeout=90).run()
    # AppTest는 본문 요소를 사이드바보다 먼저 인덱싱한다 —
    # selectbox[0]이 템플릿, 사이드바 IAM 주체는 app.sidebar.selectbox[0]이다.
    app.selectbox[0].set_value("data_analysis_team").run()
    loaded = [b for b in app.button if "불러오기" in b.label][0].click().run()

    assert not loaded.exception, [e.value for e in loaded.exception]
    assert loaded.chat_input, "대화 입력창이 렌더링되지 않았다"
    assert any("data_analysis_team" in s.value for s in loaded.success)


@pytest.mark.integration
def test_revision_form_appears_once_a_spec_is_active(monkeypatch):
    """명세를 올린 뒤에야 수정 폼이 뜬다 — 고칠 대상이 없으면 의미가 없다.

    LLM은 호출하지 않는다. 폼이 실제로 렌더링되는지만 본다 —
    `render_revision_form`이 호출되지 않으면 CLI에만 있는 기능이 된다.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    pytest.importorskip("deepagents")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    app = demo_mode_apptest(AppTest, timeout=90).run()
    before = [b for b in app.button if "수정" in b.label]
    assert not before, "명세가 없는데 수정 폼이 떠 있다"

    app.selectbox[0].set_value("data_analysis_team").run()
    loaded = [b for b in app.button if "불러오기" in b.label][0].click().run()

    assert not loaded.exception, [e.value for e in loaded.exception]
    assert [b for b in loaded.button if "수정" in b.label], "수정 폼이 렌더링되지 않았다"


@pytest.mark.integration
def test_viewer_principal_disables_creation_in_the_ui(monkeypatch, tmp_path):
    """viewer를 고르면 생성이 비활성화되고 그 이유가 화면에 보인다 (Phase 6).

    위젯 비활성은 UX이고 강제는 authorize_action이 맡지만, 사용자가 '왜 안
    되는지'를 화면에서 알 수 없으면 그것대로 결함이다.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")
    monkeypatch.setenv("DEEP_BUILDER_AUDIT_LOG", str(tmp_path / "audit.jsonl"))

    app = demo_mode_apptest(AppTest).run()
    app.sidebar.selectbox[0].set_value("demo_viewer").run()

    assert not app.exception, [e.value for e in app.exception]
    # Phase 8: 사유는 st.info가 아니라 비활성 버튼 옆 caption 한 줄이다 (시안 5a).
    captions = [c.value for c in app.caption]
    assert any("생성할 수 없습니다" in m for m in captions), captions


def test_principal_names_puts_the_default_first():
    """selectbox 기본 선택(첫 항목)이 admin이어야 CLI와 기본 동작이 같다."""
    from ui.state import load_iam_config, principal_names

    names = principal_names(load_iam_config())
    assert names[0] == "admin"
    assert set(names) == {"admin", "demo_builder", "demo_operator", "demo_viewer"}


# --- OIDC 헬퍼 (Phase 7) -----------------------------------------------------


def test_oidc_configured_requires_a_client_id():
    from ui.state import oidc_configured

    assert not oidc_configured({})
    assert not oidc_configured({"auth": {}})
    assert oidc_configured({"auth": {"client_id": "abc"}})


def test_oidc_configured_treats_missing_secrets_file_as_demo_mode():
    """secrets.toml이 없는 클린 클론에서 앱이 죽으면 안 된다 — 데모 모드다."""
    from ui.state import oidc_configured

    class NoSecretsFile:
        def get(self, key):
            raise FileNotFoundError("No secrets files found")

    assert not oidc_configured(NoSecretsFile())


def test_user_identity_normalizes_missing_and_scalar_groups():
    from ui.state import user_identity

    assert user_identity({"email": "a@b.c", "groups": ["g1", "g2"]}) == (
        "a@b.c",
        ["g1", "g2"],
    )
    assert user_identity({"email": "a@b.c"}) == ("a@b.c", [])
    # IdP에 따라 그룹이 문자열 하나로 올 수 있다
    assert user_identity({"email": "a@b.c", "groups": "solo"}) == ("a@b.c", ["solo"])
    assert user_identity({}) == ("", [])


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
    app = demo_mode_apptest(AppTest).run()

    messages = [e.value for e in app.sidebar.error]
    assert any("ANTHROPIC_API_KEY" in m for m in messages), messages
