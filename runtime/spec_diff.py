"""두 AgentSpec의 차이를 사람이 읽을 수 있게 요약한다.

**왜 필요한가**: 수정 루프의 주된 실패 모드는 "요청하지 않은 것까지 바뀌는 것"이다.
LLM에게 전체 명세를 다시 쓰게 하면 손대지 말라고 한 문장도 조용히 다듬는다.
바뀐 것을 전부 보여주면 사용자가 그 자리에서 알아챈다 —
**신뢰는 "요청한 것만 바뀐다"는 약속이 아니라 "바뀐 것이 보인다"는 사실에서 온다.**

`system_prompt`는 길어서 전문을 찍으면 나머지 변경이 묻힌다. 바뀌었다는 사실과
길이 변화만 보여주고, 전문은 저장된 파일에서 보게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from runtime.spec import AgentSpec, SubAgentSpec

# 이 길이를 넘는 문자열 필드는 전문 대신 요약으로 보여준다.
INLINE_TEXT_LIMIT = 120


@dataclass(frozen=True)
class FieldChange:
    """스칼라 필드 하나의 변경."""

    name: str
    before: str
    after: str


@dataclass(frozen=True)
class MemberChange:
    """팀원 하나의 변경 내역."""

    name: str
    fields: list[FieldChange] = field(default_factory=list)
    tools_added: list[str] = field(default_factory=list)
    tools_removed: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SpecDiff:
    """두 명세의 차이 전체."""

    fields: list[FieldChange] = field(default_factory=list)
    tools_added: list[str] = field(default_factory=list)
    tools_removed: list[str] = field(default_factory=list)
    members_added: list[str] = field(default_factory=list)
    members_removed: list[str] = field(default_factory=list)
    members_changed: list[MemberChange] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """아무것도 바뀌지 않았는가."""
        return not (
            self.fields
            or self.tools_added
            or self.tools_removed
            or self.members_added
            or self.members_removed
            or self.members_changed
        )


def _summarize(value: object) -> str:
    """긴 텍스트는 길이로 대신 보여준다."""
    if value is None:
        return "(없음)"
    text = str(value)
    if len(text) <= INLINE_TEXT_LIMIT:
        return text
    return f"({len(text):,}자)"


def _scalar_changes(
    before: object, after: object, names: tuple[str, ...]
) -> list[FieldChange]:
    changes: list[FieldChange] = []
    for name in names:
        old, new = getattr(before, name), getattr(after, name)
        if old != new:
            changes.append(FieldChange(name, _summarize(old), _summarize(new)))
    return changes


def _member_change(before: SubAgentSpec, after: SubAgentSpec) -> MemberChange | None:
    """팀원 하나의 변경. 바뀐 게 없으면 None."""
    fields = _scalar_changes(before, after, ("description", "system_prompt", "model"))
    added = sorted(set(after.tools) - set(before.tools))
    removed = sorted(set(before.tools) - set(after.tools))

    if not (fields or added or removed):
        return None
    return MemberChange(after.name, fields, added, removed)


def diff_specs(before: AgentSpec, after: AgentSpec) -> SpecDiff:
    """수정 전후 명세를 비교한다.

    팀원은 **이름으로** 맞춘다. 이름이 바뀌면 추가+삭제로 보인다 —
    이름은 리더가 위임에 쓰는 식별자라, 바뀌면 실제로 다른 팀원이다.
    """
    before_members = {s.name: s for s in before.subagents}
    after_members = {s.name: s for s in after.subagents}

    changed = [
        change
        for name in sorted(before_members.keys() & after_members.keys())
        if (change := _member_change(before_members[name], after_members[name]))
    ]

    return SpecDiff(
        fields=_scalar_changes(
            before,
            after,
            ("name", "description", "system_prompt", "model", "spec_version"),
        ),
        tools_added=sorted(set(after.tools) - set(before.tools)),
        tools_removed=sorted(set(before.tools) - set(after.tools)),
        members_added=sorted(after_members.keys() - before_members.keys()),
        members_removed=sorted(before_members.keys() - after_members.keys()),
        members_changed=changed,
    )


def format_diff(diff: SpecDiff) -> str:
    """변경 내역을 콘솔·UI에 그대로 찍을 수 있는 텍스트로 만든다."""
    if diff.is_empty:
        return "  (변경 없음 — 요구가 이미 반영돼 있거나 해석되지 않았다)"

    lines: list[str] = []
    for change in diff.fields:
        lines.append(f"  ~ {change.name}: {change.before} → {change.after}")
    for key in diff.tools_added:
        lines.append(f"  + 도구 {key}")
    for key in diff.tools_removed:
        lines.append(f"  - 도구 {key}")
    for name in diff.members_added:
        lines.append(f"  + 팀원 {name}")
    for name in diff.members_removed:
        lines.append(f"  - 팀원 {name}")

    for member in diff.members_changed:
        lines.append(f"  ~ 팀원 {member.name}")
        for change in member.fields:
            lines.append(f"      {change.name}: {change.before} → {change.after}")
        for key in member.tools_added:
            lines.append(f"      + 도구 {key}")
        for key in member.tools_removed:
            lines.append(f"      - 도구 {key}")

    return "\n".join(lines)
