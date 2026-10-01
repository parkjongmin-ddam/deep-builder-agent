"""소속 팀(직무 프로필) 로더 (Phase 9) — 예시·추천·평가 세트의 축.

팀은 권한(역할)과 **별개의 축**이다. 역할(iam.json)은 "무엇을 할 수 있나"를,
팀 프로필은 "어떤 일을 하나"를 정한다. 프로필은 권한·도구 경계를 바꾸지
않으므로 사용자가 사이드바에서 팀을 직접 골라도 보안상 문제가 없다 —
바뀌는 것은 예시 문구·템플릿 추천·평가 세트뿐이다.

로드 규칙 (iam.json과 같은 실패 원칙):
- 인자 > `DEEP_BUILDER_TEAMS_FILE` > `teams.json` > `teams.example.json` > None
- 명시한 파일(인자·환경변수)이 없거나 깨지면 **폴백하지 않고 실패한다** —
  설정 오타가 조용히 기본 동작이 되면 디버깅이 불가능하다.
- 둘 다 없으면 None — 팀 선택 UI를 숨기고 공통으로 동작한다.
  example이 레포에 커밋되므로 clone 직후에도 팀 선택이 동작한다.

프로필 자체(표시 이름·예시·추천 템플릿)는 파일이 아니라 **코드에 정의**한다.
파일은 "어느 팀이 어느 프로필인가"만 말한다 — 조직 개편으로 팀이 늘어도
코드는 그대로고, 프로필 내용 수정은 코드 리뷰를 거친다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, field_validator, model_validator

from runtime.config import env_or_default


@dataclass(frozen=True)
class Profile:
    """직무 프로필 — UI(단계 2)와 평가 세트(단계 4)가 소비하는 재료.

    examples는 클릭 시 입력창에 들어가는 예시 칩 2개, placeholder는
    입력창 안내 문구 1개다 (지시서 2절: 문구 3개의 역할 분담).
    recommended_templates의 순서가 곧 추천 순서다. 아직 없는 템플릿
    이름이 있어도 된다(단계 3에서 생성) — UI는 존재하는 것만 보여준다.
    """

    key: str
    display: str
    placeholder: str
    examples: tuple[str, str]
    recommended_templates: tuple[str, ...]


PROFILES: dict[str, Profile] = {
    "infra": Profile(
        key="infra",
        display="시스템 엔지니어",
        placeholder=(
            "작업공간의 ADFS 이벤트 로그를 읽고 인증 실패 원인 후보와 "
            "조치 순서를 정리해주는 에이전트 만들어줘"
        ),
        examples=(
            "계정 동기화 결과 CSV를 읽어 실패 건을 유형별로 집계하고 "
            "보고서 파일로 저장해주는 에이전트 만들어줘",
            "ADFS 토큰 서명 인증서 만료 대응 절차를 조사해서 점검 "
            "체크리스트로 정리해주는 에이전트 만들어줘",
        ),
        recommended_templates=("adfs_log_triage_team", "sync_report_team"),
    ),
    "dev": Profile(
        key="dev",
        display="개발자",
        placeholder=(
            "ASP.NET Core 앱의 ADFS OIDC 로그인 예외 스택트레이스를 읽고 "
            "원인과 수정 방향을 알려주는 에이전트 만들어줘"
        ),
        examples=(
            "Python 계정 동기화 스크립트의 traceback을 읽고 원인 후보를 "
            "정리해주는 에이전트 만들어줘",
            ".NET과 Python에서 ADFS(OIDC·SAML) 연동에 쓰는 라이브러리를 "
            "비교 조사해주는 에이전트 만들어줘",
        ),
        recommended_templates=("auth_error_analysis_team", "auth_lib_research_team"),
    ),
}

DEFAULT_TEAMS_FILE = Path("teams.json")
EXAMPLE_TEAMS_FILE = Path("teams.example.json")


class TeamsConfig(BaseModel):
    """팀 → 프로필 매핑 + (선택) Okta 그룹 → 팀 매핑.

    `groups`는 로그인 시 자동 선택용이다 — 여러 그룹에 속한 사용자는
    **파일 선언 순서**로 첫 매칭이 이긴다 (iam의 groups와 같은 규칙).
    자동 선택일 뿐이라 사용자가 UI에서 바꿀 수 있다.
    """

    teams: dict[str, str]
    groups: dict[str, str] = {}

    @field_validator("teams")
    @classmethod
    def teams_must_reference_defined_profiles(cls, v: dict[str, str]) -> dict[str, str]:
        """오타난 프로필 키가 조용히 공통 화면이 되는 것을 막는다 (로드 시점 실패)."""
        if not v:
            raise ValueError("teams is empty — 파일을 지우면 기능이 숨겨진다 (빈 매핑 금지)")
        unknown = sorted({k for k in v.values() if k not in PROFILES})
        if unknown:
            raise ValueError(
                f"undefined profile keys: {unknown} (defined: {sorted(PROFILES)})"
            )
        return v

    @model_validator(mode="after")
    def groups_must_reference_defined_teams(self) -> TeamsConfig:
        dangling = sorted(t for t in self.groups.values() if t not in self.teams)
        if dangling:
            raise ValueError(
                f"groups reference undefined teams: {dangling} "
                f"(defined teams: {sorted(self.teams)})"
            )
        return self

    def profile_key_for(self, team: str) -> str:
        return self.teams[team]

    def profile_for(self, team: str) -> Profile:
        """팀의 프로필 실체. 미정의 팀이면 KeyError — 호출부가 선택지를 제한한다."""
        return PROFILES[self.teams[team]]

    def team_for_groups(self, groups: Iterable[str]) -> str | None:
        """OIDC 그룹 클레임으로 팀을 자동 선택한다 (선언 순서 첫 매칭, 없으면 None)."""
        user_groups = set(groups)
        for group, team in self.groups.items():
            if group in user_groups:
                return team
        return None


def load_teams_config(path: Path | None = None) -> TeamsConfig | None:
    """팀 설정을 로드한다. 인자 > 환경변수 > teams.json > example > None.

    Raises:
        FileNotFoundError: 명시한 파일(인자·환경변수)이 없을 때 — 폴백 금지.
        json.JSONDecodeError / pydantic.ValidationError: 파일이 깨졌을 때.
            호출부(UI·CLI)는 iam.json과 같은 원칙으로 멈추고 오류를 보여준다.
    """
    explicit = path or (
        Path(p) if (p := env_or_default("DEEP_BUILDER_TEAMS_FILE", "")) else None
    )
    if explicit is not None:
        return TeamsConfig(**json.loads(explicit.read_text(encoding="utf-8")))

    for candidate in (DEFAULT_TEAMS_FILE, EXAMPLE_TEAMS_FILE):
        if candidate.exists():
            return TeamsConfig(**json.loads(candidate.read_text(encoding="utf-8")))
    return None
