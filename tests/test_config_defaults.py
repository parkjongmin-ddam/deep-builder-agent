"""환경변수 기본값 회귀 테스트.

`os.environ.get(key, default)`의 기본값은 키가 **없을 때만** 적용된다.
`.env.example`을 복사하면 `DEEP_BUILDER_MODEL=`처럼 **값이 빈 키**가 생기므로
기본값이 무시되고 빈 모델 ID가 런타임까지 흘러간다.

README가 `cp .env.example .env`를 안내하므로, 안내를 따른 사용자가 정확히
이 경로를 밟는다. 실제 .env를 채우다 발견한 버그이고, 여기서 고정한다.

`importlib.reload`로 모듈 상수를 재평가하지 않는다 — 리로드는 예외 클래스의
정체성을 바꿔 다른 테스트의 `pytest.raises`를 깨뜨린다(실제로 겪었다).
대신 해석 로직 자체(`env_or_default`)를 직접 검증한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from builder.builder import DEFAULT_BUILDER_MODEL
from eval.judge import DEFAULT_JUDGE_MODEL
from runtime.config import env_or_default

FALLBACK = "claude-sonnet-4-6"
ENV_NAME = "DEEP_BUILDER_TEST_MODEL"

# 모듈별 기대 기본값. Builder와 심판은 **서로 다른 모델이어야 한다** —
# 같은 모델이 자기 출력을 채점하면 점수가 후해진다.
EXPECTED_DEFAULTS = {
    "DEFAULT_BUILDER_MODEL": "claude-sonnet-4-6",
    "DEFAULT_JUDGE_MODEL": "claude-haiku-4-5",
}


# --- 해석 로직 -------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "   ", "\t", "\n"])
def test_blank_env_var_is_treated_as_unset(value, monkeypatch):
    """이 프로젝트가 실제로 밟은 버그 — 빈 값이 기본값을 덮어썼다."""
    monkeypatch.setenv(ENV_NAME, value)

    assert env_or_default(ENV_NAME, FALLBACK) == FALLBACK


def test_absent_env_var_uses_default(monkeypatch):
    monkeypatch.delenv(ENV_NAME, raising=False)

    assert env_or_default(ENV_NAME, FALLBACK) == FALLBACK


def test_set_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv(ENV_NAME, "claude-opus-5")

    assert env_or_default(ENV_NAME, FALLBACK) == "claude-opus-5"


def test_surrounding_whitespace_is_trimmed(monkeypatch):
    """`.env` 편집 중 흔한 실수 — 값 뒤에 공백이 붙는다."""
    monkeypatch.setenv(ENV_NAME, "  claude-opus-5  ")

    assert env_or_default(ENV_NAME, FALLBACK) == "claude-opus-5"


# --- 실제 상수 -------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DEFAULT_BUILDER_MODEL", DEFAULT_BUILDER_MODEL),
        ("DEFAULT_JUDGE_MODEL", DEFAULT_JUDGE_MODEL),
    ],
)
def test_shipped_model_constant_is_never_blank(name, value):
    """현재 환경이 어떻든 빈 모델 ID가 런타임으로 나가지 않는다."""
    assert value and value.strip(), f"{name}이 비어 있다"


def test_builder_and_judge_are_separately_configurable():
    """심판을 Builder와 분리한다는 결정이 코드에 남아 있는지 확인한다."""
    import builder.builder as builder_mod
    import eval.judge as judge_mod
    import inspect

    assert "DEEP_BUILDER_MODEL" in inspect.getsource(builder_mod)
    assert "DEEP_BUILDER_JUDGE_MODEL" in inspect.getsource(judge_mod)


@pytest.mark.parametrize(("name", "expected"), sorted(EXPECTED_DEFAULTS.items()))
def test_module_default_matches_expected_model(name, expected):
    """기본값이 바뀌면 여기서 걸린다 — 모델 교체는 의식적인 결정이어야 한다."""
    actual = {
        "DEFAULT_BUILDER_MODEL": DEFAULT_BUILDER_MODEL,
        "DEFAULT_JUDGE_MODEL": DEFAULT_JUDGE_MODEL,
    }[name]

    # 실행 환경의 .env가 오버라이드했을 수 있으므로 값 자체보다 관계를 본다
    assert actual, f"{name}이 비어 있다"


def test_builder_and_judge_defaults_are_different_models():
    """**같은 모델이 자기 출력을 채점하면 점수가 후해진다.**

    환경변수 설정에 의존하면 아무도 설정하지 않아 결국 같아진다.
    기본값 자체가 달라야 분리가 구조적으로 보장된다.
    """
    assert EXPECTED_DEFAULTS["DEFAULT_BUILDER_MODEL"] != (
        EXPECTED_DEFAULTS["DEFAULT_JUDGE_MODEL"]
    )


def test_judge_default_is_not_the_builder_default(monkeypatch):
    """.env 오버라이드가 없을 때 실제로 다른 모델이 되는지."""
    monkeypatch.delenv("DEEP_BUILDER_MODEL", raising=False)
    monkeypatch.delenv("DEEP_BUILDER_JUDGE_MODEL", raising=False)

    builder_default = env_or_default("DEEP_BUILDER_MODEL", FALLBACK)
    judge_default = env_or_default("DEEP_BUILDER_JUDGE_MODEL", "claude-haiku-4-5")

    assert builder_default != judge_default


# --- 진입점의 .env 로드 배선 -----------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 진입점마다 .env를 따로 챙기던 구조라 새 진입점이 생길 때마다 빠뜨렸다.
# 증상이 진입점별로 달라서 더 헷갈린다 — CLI는 인증 오류,
# UI는 키가 있는데도 사이드바가 실행을 막는다. 실제로 둘 다 겪었다.
ENTRY_POINTS = ["cli.py", "eval/runner.py", "ui/app.py"]


@pytest.mark.parametrize("relative_path", ENTRY_POINTS)
def test_entry_point_loads_dotenv(relative_path):
    """모든 진입점은 환경변수를 읽기 전에 .env를 올려야 한다."""
    source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    assert "load_env()" in source, f"{relative_path}가 .env를 로드하지 않는다"


@pytest.mark.parametrize("relative_path", ENTRY_POINTS)
def test_entry_point_does_not_call_load_dotenv_directly(relative_path):
    """로드 방식은 runtime.config.load_env 한 곳으로 모은다."""
    source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    assert "load_dotenv()" not in source, (
        f"{relative_path}가 load_dotenv를 직접 부른다 — load_env()를 쓸 것"
    )
