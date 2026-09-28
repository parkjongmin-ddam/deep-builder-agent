"""전 테스트 공통 픽스처.

감사 로그 격리를 여기서 강제한다 — 개별 테스트가 env 설정을 빠뜨리면
실제 `logs/audit.jsonl`이 오염된다 (2026-09-28 실측: pytest 실행이
저장소 감사 로그에 admin 레코드를 남겼다). 파일별 수동 설정 대신
autouse로 전건에 적용한다.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolated_audit_log(tmp_path, monkeypatch):
    """감사 로그를 테스트별 임시 경로로 돌린다 — 저장소 로그 오염 금지."""
    monkeypatch.setenv("DEEP_BUILDER_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    yield
