"""전역 스타일 — CSS 주입은 이 파일 한 곳에 모은다 (Phase 8 단계 1).

색상·반경·위젯 테두리·폰트 패밀리는 `.streamlit/config.toml`
([theme.light] / [theme.dark])이 단일 진실 원천이다. 여기서는 config로
표현할 수 없는 것만 주입한다:

- **웹폰트 로드** — config의 `font = "Pretendard Variable"`은 패밀리 이름을
  지정할 뿐 폰트 파일을 가져오지 않는다. CDN @import로 로드하고, 오프라인이면
  config의 폴백(sans-serif / monospace)으로 조용히 내려간다.
  로컬 woff2 커밋은 기각 — 사유는 BUILD_SPEC.md Phase 8 결정 로그.

- **도구 배지·칩** (단계 2) — `ui/state.py`의 `badges_html`/`chips_html`이
  만드는 span을 st.html로 렌더한다. 색은 시안 5a의 CSS 주입 예제대로
  `prefers-color-scheme`으로 전환한다. **한계**: 사용자가 Streamlit 설정에서
  OS와 반대 테마를 강제하면 배지 색이 테마와 어긋난다 — config 색상이 아닌
  주입 CSS라 Streamlit 테마 전환에 연동할 수단이 없다(시안이 지정한 방식).

Streamlit 내부 클래스명 의존은 최소화한다. 사용 중인 선택자는 전부
자체 클래스(`.dba-*`)다. 이후 단계에서 내부 선택자를 쓰면 여기 주석에 남긴다.
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

# 배지·칩 색 토큰 — 값은 .streamlit/config.toml의 라이트/다크 팔레트와 동일.
_BADGE_CSS = """
:root {
  --dba-info: #1F6FD1;
  --dba-accent: #0F8C73;
  --dba-chip-bg: #F3F3F0;
  --dba-chip-border: #E2E2DD;
  --dba-chip-border-dashed: #C9C9C2;
  --dba-chip-text: #565B63;
}
@media (prefers-color-scheme: dark) {
  :root {
    --dba-info: #6AA8FF;
    --dba-accent: #34D3B0;
    --dba-chip-bg: #1E2229;
    --dba-chip-border: #2A2F38;
    --dba-chip-border-dashed: #3A404B;
    --dba-chip-text: #A3A9B3;
  }
}
.dba-badge {
  display: inline-flex; align-items: center;
  height: 22px; padding: 0 7px; margin: 0 4px 4px 0;
  border-radius: 6px;
  font: 500 11.5px/1 "JetBrains Mono", monospace;
  background: color-mix(in srgb, var(--dba-info) 14%, transparent);
  color: var(--dba-info);
}
.dba-badge--accent {
  background: color-mix(in srgb, var(--dba-accent) 14%, transparent);
  color: var(--dba-accent);
}
.dba-chip {
  display: inline-flex; align-items: center;
  height: 22px; padding: 0 7px; margin: 0 4px 4px 0;
  border-radius: 5px;
  font: 500 11.5px/1 "JetBrains Mono", monospace;
  background: var(--dba-chip-bg);
  border: 1px solid var(--dba-chip-border);
  color: var(--dba-chip-text);
}
.dba-chip--dashed {
  background: transparent;
  border-style: dashed;
  border-color: var(--dba-chip-border-dashed);
}
"""


def inject_css() -> None:
    """앱 시작 시 1회 호출한다 (재실행마다 불려도 멱등이다)."""
    st.html(f"<style>\n{_FONT_CSS}\n{_BADGE_CSS}\n</style>")
