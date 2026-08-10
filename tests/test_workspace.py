"""파일시스템 경계 테스트 — 에이전트가 workspace/ 밖을 읽지 못해야 한다.

기본 백엔드(StateBackend)는 세션 내 가상 FS라 실제 문서를 못 읽었고,
반대로 루트를 프로젝트 전체로 열면 `.env`가 읽힌다. 그래서 전용 디렉터리로
묶었다(2026-08-10 결정). **그 경계가 실제로 지켜지는지가 이 파일의 관심사다.**

여기서 쓰는 '비밀값'은 전부 합성 문자열이다. 실제 .env를 건드리지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from runtime.config import workspace_dir

SYNTHETIC_SECRET = "NOT-A-REAL-SECRET-abc123"


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch) -> Path:
    """workspace를 임시 디렉터리로 옮기고, 그 **밖**에 합성 비밀값을 둔다."""
    work = tmp_path / "workspace"
    work.mkdir()
    (work / "inside.txt").write_text("workspace 안의 문서", encoding="utf-8")

    # workspace 밖 — 실제 프로젝트에서 .env 가 놓이는 위치에 해당한다
    (tmp_path / "secret.env").write_text(
        f"ANTHROPIC_API_KEY={SYNTHETIC_SECRET}\n", encoding="utf-8"
    )

    monkeypatch.setenv("DEEP_BUILDER_WORKSPACE", str(work))
    return tmp_path


def _backend(root: Path):
    from deepagents.backends import FilesystemBackend

    return FilesystemBackend(root_dir=root, virtual_mode=True)


# --- workspace 해석 ---------------------------------------------------------


def test_workspace_dir_follows_env_var(sandbox: Path):
    assert workspace_dir() == (sandbox / "workspace").resolve()


def test_workspace_dir_is_created_when_missing(tmp_path: Path, monkeypatch):
    """없으면 만들어야 한다 — 첫 실행에서 백엔드가 죽지 않도록."""
    target = tmp_path / "does_not_exist_yet"
    monkeypatch.setenv("DEEP_BUILDER_WORKSPACE", str(target))

    assert workspace_dir().is_dir()


# --- 경계 ------------------------------------------------------------------


def _attempt_read(backend, path: str) -> str:
    """백엔드로 읽기를 시도하고, 결과든 오류든 문자열로 돌려준다.

    차단 방식이 경로마다 다르다 — `..`는 ValueError, `~`는 not-found 결과다.
    둘 다 '비밀값이 안 나온다'는 같은 성질을 검사해야 하므로 한데 모은다.
    """
    try:
        return repr(backend.read(path))
    except Exception as exc:  # noqa: BLE001 - 차단도 정상 결과다
        return f"{type(exc).__name__}: {exc}"


def test_file_inside_workspace_is_readable(sandbox: Path):
    """대조군 — 안쪽 파일은 오류 없이 읽혀야 한다.

    이게 없으면 '전부 실패해서' 통과하는 테스트가 된다.
    """
    backend = _backend(workspace_dir())

    result = backend.read("/inside.txt")

    assert getattr(result, "error", None) is None


@pytest.mark.parametrize(
    "escape_path",
    [
        "../secret.env",
        "../../secret.env",
        "~/secret.env",
        "/../secret.env",
        "./../secret.env",
    ],
)
def test_traversal_paths_cannot_reach_secrets(sandbox: Path, escape_path: str):
    """`..`·`~`로 workspace를 벗어나 비밀값에 닿을 수 없어야 한다."""
    backend = _backend(workspace_dir())

    assert SYNTHETIC_SECRET not in _attempt_read(backend, escape_path)


def test_absolute_path_outside_workspace_cannot_reach_secrets(sandbox: Path):
    """workspace 밖 절대경로도 막혀야 한다."""
    backend = _backend(workspace_dir())

    outcome = _attempt_read(backend, str(sandbox / "secret.env"))

    assert SYNTHETIC_SECRET not in outcome


def test_read_is_the_actual_backend_api(sandbox: Path):
    """메서드 이름을 잘못 짚으면 경계 테스트가 통째로 무의미해진다.

    실제로 `read_file`로 잘못 쓴 적이 있고, 그때 테스트는 AttributeError를
    '차단됨'으로 오인해 전부 통과했다. 계약을 여기서 고정한다.
    """
    backend = _backend(workspace_dir())

    assert callable(backend.read)
    assert not hasattr(backend, "read_file")


# --- 배선 ------------------------------------------------------------------


def test_agent_filesystem_is_bound_to_workspace(sandbox: Path, monkeypatch):
    """factory가 만든 에이전트의 백엔드가 workspace에 묶여 있는가.

    deepagents 0.7.5는 생성자 인자 `root_dir`을 `backend.cwd`에 저장한다
    (인자명과 필드명이 다르다 — 설치본으로 확인).
    """
    pytest.importorskip("deepagents")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")

    from runtime.factory import _filesystem_middleware

    backend = _filesystem_middleware(["file_read"]).backend

    assert Path(str(backend.cwd)).resolve() == workspace_dir()
    assert backend.virtual_mode is True, "virtual_mode가 꺼지면 경로 탈출이 열린다"


def test_project_env_file_is_outside_the_workspace():
    """실제 프로젝트 배치 확인 — .env 가 workspace 안에 있으면 안 된다."""
    project_root = Path(__file__).resolve().parent.parent
    workspace = project_root / "workspace"

    assert not (project_root / ".env").is_relative_to(workspace)
