"""전역 스타일 — CSS 주입은 이 파일 한 곳에 모은다 (Phase 8 단계 1).

색상·반경·위젯 테두리·폰트 패밀리는 `.streamlit/config.toml`
([theme.light] / [theme.dark])이 단일 진실 원천이다. 여기서는 config로
표현할 수 없는 것만 주입한다:

- **웹폰트 로드** — config의 `font = "Pretendard Variable"`은 패밀리 이름을
  지정할 뿐 폰트 파일을 가져오지 않는다. CDN @import로 로드하고, 오프라인이면
  config의 폴백(sans-serif / monospace)으로 조용히 내려간다.
  로컬 woff2 커밋은 기각 — 사유는 BUILD_SPEC.md Phase 8 결정 로그.

Streamlit 내부 클래스명 의존은 최소화한다. 현재 사용하는 선택자는 없다
(@import는 선택자가 아니다). 이후 단계에서 선택자를 쓰면 여기 주석에 남긴다.
"""

from __future__ import annotations

import streamlit as st

# Pretendard: 한글 포함 dynamic-subset — 필요한 글리프 블록만 내려받는다.
# JetBrains Mono: 코드·배지·식별자용 (스타일 가이드 5a).
_FONT_CSS = (
    "@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9"
    "/dist/web/variable/pretendardvariable-dynamic-subset.min.css');\n"
    "@import url('https://fonts.googleapis.com/css2"
    "?family=JetBrains+Mono:wght@400;500;600&display=swap');"
)


def inject_css() -> None:
    """앱 시작 시 1회 호출한다 (재실행마다 불려도 멱등이다)."""
    st.html(f"<style>\n{_FONT_CSS}\n</style>")
