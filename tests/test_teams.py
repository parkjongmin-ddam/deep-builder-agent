"""소속 팀(직무 프로필) 로더 테스트 (Phase 9 단계 1).

팀 프로필은 권한(iam.json)과 별개의 축이다 — 예시·템플릿 추천·평가 세트만
바꾸고 권한·도구 경계는 건드리지 않는다. 그래서 여기서는 보안이 아니라
**설정 로드의 실패 방식**을 고정한다:

- 명시한 파일(인자·환경변수)이 없거나 깨지면 폴백하지 않고 실패한다
  (iam.json과 같은 원칙 — 오타가 조용히 기본 동작이 되면 안 된다)
- 루트 teams.json이 없으면 teams.example.json으로 폴백한다
  (clone 직후에도 팀 선택이 동작해야 한다 — 완료 조건 ①)
- 둘 다 없으면 None — 기능을 숨기고 공통으로 동작한다
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from runtime.teams import (
    EXAMPLE_TEAMS_FILE,
    PROFILES,
    Profile,
    TeamsConfig,
    load_teams_config,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# --- 프로필 정의 -------------------------------------------------------------


def test_profiles_define_infra_and_dev():
    """지시서(PHASE9_TEAMS.md)의 프로필 2종이 코드에 정의되어야 한다."""
    assert set(PROFILES) == {"infra", "dev"}
    assert PROFILES["infra"].display == "시스템 엔지니어"
    assert PROFILES["dev"].display == "개발자"


@pytest.mark.parametrize("key", ["infra", "dev"])
def test_profile_carries_examples_and_recommendations(key):
    """placeholder 1 + 예시 칩 2 + 템플릿 추천 순서 — UI(단계 2)가 소비할 재료."""
    profile = PROFILES[key]

    assert profile.key == key
    assert profile.placeholder.strip()
    assert len(profile.examples) == 2
    assert all(text.strip() for text in profile.examples)
    assert profile.recommended_templates, "추천 템플릿 순서가 비어 있다"


def test_profiles_are_immutable():
    with pytest.raises(AttributeError):
        PROFILES["infra"].display = "바꿔치기"  # type: ignore[misc]


# --- 배포 example 파일 -------------------------------------------------------


def test_example_file_matches_the_spec_table():
    """레포에 커밋되는 example이 지시서의 팀 표와 일치해야 한다.

    example은 단순 견본이 아니라 teams.json이 없을 때 **실제로 로드되는**
    기본값이다 (mcp_servers.example.json이 로드 실패했던 전례 — 배포 산출물은
    그대로 동작해야 한다).
    """
    config = TeamsConfig(
        **json.loads((PROJECT_ROOT / EXAMPLE_TEAMS_FILE).read_text(encoding="utf-8"))
    )

    assert config.teams == {"CLP": "infra", "ANX": "dev", "SNP": "dev"}
    assert config.groups == {}, "example의 groups가 실제 매핑으로 동작하면 안 된다"


# --- 로드 경로와 폴백 --------------------------------------------------------


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


VALID_PAYLOAD = {"teams": {"CLP": "infra", "ANX": "dev"}}


def test_explicit_path_loads(tmp_path):
    config = load_teams_config(_write(tmp_path / "teams.json", VALID_PAYLOAD))

    assert config is not None
    assert config.profile_key_for("CLP") == "infra"


def test_missing_explicit_path_fails_instead_of_falling_back(tmp_path):
    """명시한 파일이 없으면 example로 넘어가지 않는다 (iam.json과 같은 원칙)."""
    with pytest.raises(FileNotFoundError):
        load_teams_config(tmp_path / "nope.json")


def test_env_var_selects_the_file(tmp_path, monkeypatch):
    target = _write(tmp_path / "custom.json", VALID_PAYLOAD)
    monkeypatch.setenv("DEEP_BUILDER_TEAMS_FILE", str(target))

    config = load_teams_config()

    assert config is not None and "CLP" in config.teams


def test_missing_env_var_target_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEP_BUILDER_TEAMS_FILE", str(tmp_path / "nope.json"))

    with pytest.raises(FileNotFoundError):
        load_teams_config()


def test_falls_back_to_example_when_teams_json_is_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEP_BUILDER_TEAMS_FILE", raising=False)
    _write(tmp_path / "teams.example.json", VALID_PAYLOAD)

    config = load_teams_config()

    assert config is not None and config.profile_key_for("ANX") == "dev"


def test_teams_json_wins_over_example(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEP_BUILDER_TEAMS_FILE", raising=False)
    _write(tmp_path / "teams.example.json", VALID_PAYLOAD)
    _write(tmp_path / "teams.json", {"teams": {"OPS": "infra"}})

    config = load_teams_config()

    assert config is not None and set(config.teams) == {"OPS"}


def test_no_files_means_feature_hidden(tmp_path, monkeypatch):
    """둘 다 없으면 None — 팀 선택을 숨기고 현행(공통)과 동일하게 동작한다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEP_BUILDER_TEAMS_FILE", raising=False)

    assert load_teams_config() is None


def test_broken_json_raises(tmp_path):
    broken = tmp_path / "teams.json"
    broken.write_text("{not json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_teams_config(broken)


# --- 검증 --------------------------------------------------------------------


def test_unknown_profile_key_is_rejected_at_load_time():
    """정의되지 않은 프로필 키는 로드 시점에 실패해야 한다.

    조용히 받아주면 그 팀의 사용자는 공통 화면을 보게 되고, 오타는
    아무도 모른 채 남는다 (iam의 행위명 검증과 같은 이유).
    """
    with pytest.raises(ValidationError, match="infra"):
        TeamsConfig(teams={"CLP": "infro"})


def test_group_mapping_must_reference_a_defined_team():
    with pytest.raises(ValidationError, match="CLP"):
        TeamsConfig(teams={"CLP": "infra"}, groups={"okta-adfs-ops": "ANX"})


def test_empty_teams_is_rejected():
    """빈 매핑은 '파일은 있는데 아무것도 안 되는' 상태 — 숨김(None)과 다르다."""
    with pytest.raises(ValidationError):
        TeamsConfig(teams={})


# --- 해석 헬퍼 ---------------------------------------------------------------


def _config() -> TeamsConfig:
    return TeamsConfig(
        teams={"CLP": "infra", "ANX": "dev", "SNP": "dev"},
        groups={"okta-adfs-ops": "CLP", "okta-app-dev": "ANX"},
    )


def test_profile_for_team_resolves():
    config = _config()

    profile = config.profile_for("SNP")

    assert isinstance(profile, Profile)
    assert profile.key == "dev"


def test_profile_for_unknown_team_raises():
    with pytest.raises(KeyError):
        _config().profile_for("GHOST")


def test_team_for_groups_uses_declaration_order():
    """여러 그룹에 속하면 설정 파일 선언 순서로 첫 매칭 (iam groups와 같은 규칙)."""
    config = _config()

    assert config.team_for_groups(["okta-app-dev", "okta-adfs-ops"]) == "CLP"
    assert config.team_for_groups(["okta-app-dev"]) == "ANX"
    assert config.team_for_groups(["unrelated"]) is None
    assert config.team_for_groups([]) is None


# --- UI 표시 (단계 2가 소비) -------------------------------------------------


def test_team_label_for_sidebar():
    """사이드바 표시 형식 `CLP · 시스템 엔지니어` (지시서 5절)."""
    from ui.state import team_label

    assert team_label("CLP", "시스템 엔지니어") == "CLP · 시스템 엔지니어"
