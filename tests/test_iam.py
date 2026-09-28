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


# 감사 로그 격리는 tests/conftest.py의 autouse 픽스처가 전 테스트에 강제한다.


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


# --- OIDC 신원 해석 (Phase 7) -------------------------------------------------


def test_identity_maps_group_claim_to_role():
    principal = _default_config().resolve_identity(
        "user@example.com", ["agent-builders"]
    )
    assert principal.role_name == "builder"
    assert principal.name == "user@example.com", "감사 로그는 검증된 신원을 가리켜야 한다"


def test_identity_email_mapping_beats_group_mapping():
    """개인 예외(이메일 직접 매핑)가 그룹보다 구체적이므로 우선한다."""
    config = _default_config().model_copy(
        update={"principals": {**_default_config().principals, "vip@example.com": "admin"}}
    )
    principal = config.resolve_identity("vip@example.com", ["agent-viewers"])
    assert principal.role_name == "admin"


def test_identity_first_declared_group_wins():
    """여러 그룹 매칭 시 정책 파일 선언 순서가 우선순위다."""
    principal = _default_config().resolve_identity(
        "user@example.com", ["agent-viewers", "agent-admins"]
    )
    assert principal.role_name == "admin"  # groups 선언 순서상 agent-admins가 먼저다


def test_identity_without_mapping_is_denied():
    """로그인 성공 ≠ 인가 — IdP가 보증한 신원도 정책 매핑이 없으면 거부한다."""
    with pytest.raises(PermissionDeniedError, match="no role mapping"):
        _default_config().resolve_identity("stranger@example.com", ["unmapped-group"])


def test_identity_without_email_is_denied():
    with pytest.raises(PermissionDeniedError, match="no email claim"):
        _default_config().resolve_identity("", ["agent-builders"])


def test_identity_mapping_failure_is_audited(tmp_path):
    """거부된 접근 시도야말로 감사 대상이다 — 예외만 던지고 침묵하면 안 된다.

    2026-09-28 Okta 실측에서 발견: 매핑 없는 신원의 로그인 거부가
    감사 로그에 남지 않았다.
    """
    with pytest.raises(PermissionDeniedError, match="no role mapping"):
        _default_config().resolve_identity("stranger@example.com", ["unmapped-group"])

    (record,) = [r for r in read_audit(tmp_path) if r["action"] == "resolve_identity"]
    assert record["decision"] == "deny"
    assert record["principal"] == "stranger@example.com", "검증된 신원이 남아야 추적된다"
    assert "unmapped-group" in record["detail"]["groups"], "무엇으로 왔는지가 남아야 한다"


def test_identity_missing_email_is_audited(tmp_path):
    with pytest.raises(PermissionDeniedError, match="no email claim"):
        _default_config().resolve_identity("", ["agent-builders"])

    (record,) = [r for r in read_audit(tmp_path) if r["action"] == "resolve_identity"]
    assert record["decision"] == "deny"


def test_identity_success_is_not_audited(tmp_path):
    """성공 해석은 기록하지 않는다 — Streamlit이 위젯 조작마다 스크립트를
    재실행하며 매번 resolve_identity를 호출하므로, allow를 남기면 클릭당
    한 줄씩 쌓여 로그가 스팸이 된다. 행위 허용은 authorize_action이
    행위 시점에 이미 기록한다."""
    principal = _default_config().resolve_identity("dev@example.com", ["agent-builders"])
    assert principal.role_name == "builder"  # 대조군: 해석 자체는 성공한다

    assert not [r for r in read_audit(tmp_path) if r["action"] == "resolve_identity"]


def test_audit_log_is_isolated_from_repo(tmp_path):
    """conftest의 autouse 격리가 살아 있는지 감시한다 — 이것이 풀리면
    pytest가 저장소 `logs/audit.jsonl`을 오염시킨다 (2026-09-28 실측)."""
    import os

    from runtime.iam import audit_log_path

    assert os.environ["DEEP_BUILDER_AUDIT_LOG"] == str(tmp_path / "audit.jsonl")
    assert audit_log_path() != Path("logs/audit.jsonl")


def test_group_mapping_to_undefined_role_fails_at_load():
    with pytest.raises(ValueError, match="groups reference undefined roles"):
        IamConfig(
            roles={"admin": Role(actions=["*"])},
            principals={"admin": "admin"},
            groups={"some-group": "ghost"},
        )


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
