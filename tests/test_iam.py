"""IAM 레이어 테스트 — RBAC 행위 통제와 권한 경계(boundary)를 검증한다.

보안 경계 테스트 원칙 (CLAUDE.md):
- `pytest.raises(Exception)`만으로 쓰지 않는다 — 구체 예외 + 메시지 성질 검사.
- 대조군을 함께 둔다 — 허용 경로가 실제로 되는지 확인해야 '차단'이 의미를 가진다.
"""

import json
from pathlib import Path

import pytest

from runtime.iam import (
    ACTION_CREATE,
    ACTION_RUN,
    ACTION_VIEW,
    IamConfig,
    PermissionDeniedError,
    Role,
    _default_config,
    authorize_action,
    boundary_violations,
    enforce_boundary,
    is_allowed,
    load_iam_config,
    spec_tool_keys,
)
from runtime.spec import AgentSpec

REPO_ROOT = Path(__file__).resolve().parent.parent

SPEC_DATA = {
    "name": "news_summarizer",
    "description": "IT 뉴스 요약 에이전트",
    "system_prompt": "너는 IT 뉴스 요약 에이전트다.",
    "tools": ["web_search"],
    "subagents": [],
}


@pytest.fixture(autouse=True)
def _isolated_audit_log(tmp_path, monkeypatch):
    """감사 로그를 임시 경로로 돌린다 — 테스트가 저장소에 로그를 남기면 안 된다."""
    monkeypatch.setenv("DEEP_BUILDER_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    yield


def read_audit(tmp_path) -> list[dict]:
    path = tmp_path / "audit.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# --- 정책 로드 ---------------------------------------------------------------


def test_repo_iam_json_matches_default_policy():
    """파일 정책과 코드 기본 정책이 어긋나면 '어느 쪽이 진실인가'가 생긴다."""
    from_file = IamConfig(
        **json.loads((REPO_ROOT / "iam.json").read_text(encoding="utf-8"))
    )
    assert from_file == _default_config()


def test_missing_default_file_falls_back_to_builtin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEP_BUILDER_IAM_FILE", raising=False)
    assert load_iam_config() == _default_config()


def test_explicitly_named_missing_file_fails(tmp_path):
    """명시한 정책 파일이 없으면 기본 정책으로 조용히 넘어가지 않는다."""
    with pytest.raises(OSError):
        load_iam_config(tmp_path / "nope.json")


def test_role_rejects_unknown_action():
    """오타난 행위명은 deny-by-default에서 소리 없이 사라진다 — 로드 시점에 잡는다."""
    with pytest.raises(ValueError, match="unknown actions"):
        Role(actions=["creat_agent"])  # 오타


def test_role_rejects_unregistered_tool():
    with pytest.raises(ValueError, match="unregistered tools"):
        Role(tools=["shell_exec"])  # 레지스트리에 없는 도구


def test_role_accepts_wildcards_and_mcp_keys():
    role = Role(actions=["*"], tools=["*", "mcp:*", "mcp:some_server"])
    assert "*" in role.tools


def test_principal_referencing_undefined_role_fails():
    with pytest.raises(ValueError, match="undefined roles"):
        IamConfig(roles={"admin": Role(actions=["*"])}, principals={"kim": "ghost"})


# --- 주체 해석 ---------------------------------------------------------------


def test_resolve_defaults_to_admin(monkeypatch):
    """주체 미지정 = admin. 기존 CLI·UI 흐름이 그대로 돌아야 한다."""
    monkeypatch.delenv("DEEP_BUILDER_PRINCIPAL", raising=False)
    principal = _default_config().resolve()
    assert principal.name == "admin"
    assert is_allowed(principal, ACTION_CREATE)


def test_resolve_reads_env(monkeypatch):
    monkeypatch.setenv("DEEP_BUILDER_PRINCIPAL", "demo_viewer")
    assert _default_config().resolve().role_name == "viewer"


def test_argument_overrides_env(monkeypatch):
    monkeypatch.setenv("DEEP_BUILDER_PRINCIPAL", "demo_viewer")
    assert _default_config().resolve("demo_builder").role_name == "builder"


def test_unknown_principal_is_denied_not_defaulted():
    """미등록 주체를 기본 역할로 받아주면 RBAC이 장식이 된다."""
    with pytest.raises(PermissionDeniedError, match="unknown principal"):
        _default_config().resolve("intruder")


# --- 행위 통제 (RBAC) --------------------------------------------------------


def test_viewer_cannot_create_but_can_view(tmp_path):
    viewer = _default_config().resolve("demo_viewer")

    authorize_action(viewer, ACTION_VIEW)  # 대조군: 허용 행위는 실제로 통과한다

    with pytest.raises(PermissionDeniedError, match="not allowed to create_agent"):
        authorize_action(viewer, ACTION_CREATE)

    decisions = [(r["action"], r["decision"]) for r in read_audit(tmp_path)]
    assert (ACTION_VIEW, "allow") in decisions
    assert (ACTION_CREATE, "deny") in decisions


def test_operator_can_run_but_not_create():
    operator = _default_config().resolve("demo_operator")
    assert is_allowed(operator, ACTION_RUN)
    assert not is_allowed(operator, ACTION_CREATE)


def test_admin_wildcard_allows_every_action():
    admin = _default_config().resolve("admin")
    for action in (ACTION_CREATE, ACTION_RUN, ACTION_VIEW):
        assert is_allowed(admin, action)


# --- 권한 경계 (permissions boundary) -----------------------------------------


def test_boundary_wildcard_allows_everything():
    assert boundary_violations(["python_repl", "mcp:x"], ["*"]) == []


def test_boundary_reports_only_the_excess_sorted():
    violations = boundary_violations(
        ["web_search", "python_repl", "file_write"], ["web_search"]
    )
    assert violations == ["file_write", "python_repl"]


def test_boundary_mcp_wildcard_covers_any_server_but_nothing_else():
    allowed = ["mcp:*"]
    assert boundary_violations(["mcp:alpha", "mcp:beta"], allowed) == []
    assert boundary_violations(["web_search"], allowed) == ["web_search"]


def test_enforce_boundary_blocks_subagent_tools_too(tmp_path):
    """리더는 깨끗해도 팀원이 경계 밖 도구를 들면 거부 — 위임이 상승 경로가 되면 안 된다."""
    spec = AgentSpec(
        **{
            **SPEC_DATA,
            "subagents": [
                {
                    "name": "coder",
                    "description": "코드 실행 담당",
                    "system_prompt": "너는 코더다.",
                    "tools": ["python_repl"],
                }
            ],
        }
    )
    builder_user = _default_config().resolve("demo_builder")

    with pytest.raises(PermissionDeniedError, match="python_repl"):
        enforce_boundary(builder_user, spec)

    denies = [r for r in read_audit(tmp_path) if r["decision"] == "deny"]
    assert denies and denies[-1]["detail"]["violations"] == ["python_repl"]


def test_enforce_boundary_allows_specs_within_the_boundary(tmp_path):
    """대조군 — 경계 안 스펙은 통과하고 allow가 기록된다."""
    spec = AgentSpec(**SPEC_DATA)
    builder_user = _default_config().resolve("demo_builder")

    enforce_boundary(builder_user, spec)

    allows = [r for r in read_audit(tmp_path) if r["decision"] == "allow"]
    assert allows and allows[-1]["action"] == "grant_tools"
    assert allows[-1]["resource"] == spec.name


def test_spec_tool_keys_unions_leader_and_team():
    spec = AgentSpec(
        **{
            **SPEC_DATA,
            "tools": ["web_search"],
            "subagents": [
                {
                    "name": "writer",
                    "description": "작성 담당",
                    "system_prompt": "너는 작성자다.",
                    "tools": ["file_write", "web_search"],
                }
            ],
        }
    )
    assert spec_tool_keys(spec) == {"web_search", "file_write"}


# --- 감사 로그 ----------------------------------------------------------------


def test_audit_records_are_parseable_and_complete(tmp_path):
    viewer = _default_config().resolve("demo_viewer")
    with pytest.raises(PermissionDeniedError):
        authorize_action(viewer, ACTION_RUN, resource="doc_qa_team")

    (record,) = read_audit(tmp_path)
    assert record["principal"] == "demo_viewer"
    assert record["role"] == "viewer"
    assert record["decision"] == "deny"
    assert record["resource"] == "doc_qa_team"
    # UTC ISO-8601 — 타임존 없는 타임스탬프는 감사에서 증거 능력이 없다.
    assert record["timestamp"].endswith("+00:00")
