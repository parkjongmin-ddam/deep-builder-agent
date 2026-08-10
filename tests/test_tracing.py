"""트레이싱 설정 테스트 — 조용히 꺼지는 상태를 잡아내는지 확인한다.

환경변수는 전부 테스트 안에서 만든 dict로 주입한다. 실제 키를 읽지 않는다.
"""

import pytest

from runtime.tracing import (
    DEFAULT_PROJECT,
    TracingConfigError,
    configure_tracing,
    tracing_status,
)

ENABLED_ENV = {
    "LANGSMITH_TRACING": "true",
    "LANGSMITH_API_KEY": "synthetic-key",
    "LANGSMITH_PROJECT": "deep-builder-test",
}


def test_tracing_off_when_unset():
    status = tracing_status({})

    assert not status.requested
    assert not status.enabled


def test_tracing_on_with_key():
    status = tracing_status(ENABLED_ENV)

    assert status.enabled
    assert status.project == "deep-builder-test"


def test_project_defaults_when_not_named():
    env = {k: v for k, v in ENABLED_ENV.items() if k != "LANGSMITH_PROJECT"}

    assert tracing_status(env).project == DEFAULT_PROJECT


def test_requested_without_key_is_not_silently_off():
    """가장 중요한 케이스 — 켜라고 했는데 키가 없다."""
    status = tracing_status({"LANGSMITH_TRACING": "true"})

    assert status.requested
    assert not status.enabled
    assert "LANGSMITH_API_KEY" in status.detail


def test_configure_raises_when_requested_without_key():
    with pytest.raises(TracingConfigError, match="LANGSMITH_API_KEY"):
        configure_tracing({"LANGSMITH_TRACING": "true"})


def test_configure_is_quiet_when_tracing_is_off():
    """트레이싱을 안 쓰는 사람을 막지 않는다."""
    status = configure_tracing({})

    assert not status.enabled


def test_legacy_variable_names_still_work():
    """LANGCHAIN_* 이름을 쓰던 설정도 받아준다."""
    status = tracing_status(
        {"LANGCHAIN_TRACING_V2": "true", "LANGCHAIN_API_KEY": "synthetic-key"}
    )

    assert status.enabled


@pytest.mark.parametrize("value", ["false", "0", "no", "", "off"])
def test_falsey_values_do_not_enable(value):
    assert not tracing_status({"LANGSMITH_TRACING": value}).requested


def test_status_string_is_human_readable():
    assert "on" in str(tracing_status(ENABLED_ENV))
    assert "off" in str(tracing_status({}))
