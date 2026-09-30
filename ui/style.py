"""전역 스타일 — CSS 주입은 이 파일 한 곳에 모은다 (Phase 8 단계 1).

색상·반경·위젯 테두리·폰트 패밀리는 `.streamlit/config.toml`
([theme.light] / [theme.dark])이 단일 진실 원천이다. 여기서는 config로
표현할 수 없는 것만 주입한다:

- **웹폰트 로드** — config의 `font = "Pretendard Variable"`은 패밀리 이름을
  지정할 뿐 폰트 파일을 가져오지 않는다. CDN @import로 로드하고, 오프라인이면
  config의 폴백(sans-serif / monospace)으로 조용히 내려간다.
  로컬 woff2 커밋은 기각 — 사유는 BUILD_SPEC.md Phase 8 결정 로그.

- **도구 배지·칩·환경 점검·신원 카드** (단계 2) — `ui/state.py`의 `*_html`
  함수들이 만드는 마크업을 st.html로 렌더한다. 색 팔레트는
  `st.context.theme.type`(설치본 1.64.0 확인)으로 현재 앱 테마를 읽어
  고정한다 — Streamlit 설정에서 OS와 반대 테마를 강제해도 일치한다.
  **한계**: 테마 타입은 세션 첫 로드나 테마 전환 직후 한 리런 동안 부정확할
  수 있고(설치본 docstring 명시), 감지 불가(None)면 prefers-color-scheme
  미디어 쿼리로 폴백한다.

Streamlit 내부 클래스명 의존은 최소화한다. 사용 중인 선택자는 전부
자체 클래스(`.dba-*`)다. 이후 단계에서 내부 선택자를 쓰면 여기 주석에 남긴다.
"""

from __future__ import annotations

import streamlit as st

# Pretendard: 한글 포함 dynamic-subset — 필요한 글리프 블록만 내려받는다.
# JetBrains Mono: 코드·배지·식별자용, Material Symbols: HTML 아이콘 리가처용
# (마크다운 :material/…:은 Streamlit이 자체 로드하지만 st.html 마크업은 아니다).
_FONT_CSS = (
    "@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9"
    "/dist/web/variable/pretendardvariable-dynamic-subset.min.css');\n"
    "@import url('https://fonts.googleapis.com/css2"
    "?family=JetBrains+Mono:wght@400;500;600&display=swap');\n"
    "@import url('https://fonts.googleapis.com/css2"
    "?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,400,0..1,0"
    "&display=block');"
)

# 색 토큰 — 값은 .streamlit/config.toml 및 시안 5a 팔레트와 동일하게 유지한다.
_PALETTES = {
    "light": {
        "info": "#1F6FD1",
        "accent": "#0F8C73",
        "chip-bg": "#F3F3F0",
        "chip-border": "#E2E2DD",
        "chip-border-dashed": "#C9C9C2",
        "chip-text": "#565B63",
        "muted": "#8B9099",
        "ok": "#1E8A4C",
        "warn": "#A86A00",
        "err": "#D0342C",
    },
    "dark": {
        "info": "#6AA8FF",
        "accent": "#34D3B0",
        "chip-bg": "#1E2229",
        "chip-border": "#2A2F38",
        "chip-border-dashed": "#3A404B",
        "chip-text": "#A3A9B3",
        "muted": "#6E7580",
        "ok": "#3FB968",
        "warn": "#E0A33A",
        "err": "#F2645A",
    },
}


def _root_vars(palette: dict[str, str]) -> str:
    body = "".join(f"--dba-{name}: {value};" for name, value in palette.items())
    return f":root {{{body}}}"


def badge_palette_css(theme_type: str | None) -> str:
    """현재 테마에 맞는 색 변수 블록을 만든다.

    테마를 아는 경우("light"/"dark") 그 팔레트로 고정하고, 모르는 경우(None)
    라이트 기본 + prefers-color-scheme 다크 미디어 쿼리로 폴백한다.
    """
    if theme_type in _PALETTES:
        return _root_vars(_PALETTES[theme_type])
    return (
        _root_vars(_PALETTES["light"])
        + "\n@media (prefers-color-scheme: dark) {"
        + _root_vars(_PALETTES["dark"])
        + "}"
    )


def _detected_theme() -> str | None:
    """st.context.theme.type — 스크립트 컨텍스트가 없으면 None."""
    try:
        return st.context.theme.type
    except Exception:  # noqa: BLE001 - 감지 실패는 폴백 CSS로 흡수한다
        return None


_COMPONENT_CSS = """
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
.dba-or {
  white-space: nowrap;
  font-size: 12px; color: var(--dba-muted);
}
.dba-user { display: flex; align-items: center; gap: 10px; }
.dba-user__avatar {
  width: 32px; height: 32px; flex: none;
  border-radius: 50%;
  background: color-mix(in srgb, var(--dba-accent) 14%, transparent);
  color: var(--dba-accent);
  display: flex; align-items: center; justify-content: center;
  font: 700 12px/1 "Pretendard Variable", Pretendard, sans-serif;
}
.dba-user__meta { display: flex; flex-direction: column; min-width: 0; }
.dba-user__name {
  font-size: 13px; font-weight: 600;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dba-user__sub { font-size: 12px; color: var(--dba-muted); }
.dba-env { display: flex; flex-direction: column; gap: 10px; }
.dba-env__row {
  display: grid; grid-template-columns: 18px 1fr auto;
  gap: 2px 8px; align-items: center;
}
.dba-env__icon {
  font-family: "Material Symbols Rounded";
  font-size: 18px; line-height: 1;
  font-variation-settings: "FILL" 1;
}
.dba-env__label {
  font-size: 13px; font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dba-env__label--code {
  font: 500 12.5px/1.3 "JetBrains Mono", monospace;
}
.dba-env__status { font-size: 12px; font-weight: 600; text-align: right; }
.dba-env__detail {
  grid-column: 2 / 4;
  font-size: 12px; line-height: 1.45;
  color: var(--dba-muted);
}
.dba-env--ok { color: var(--dba-ok); }
.dba-env--warn { color: var(--dba-warn); }
.dba-env--err { color: var(--dba-err); }
"""


def inject_css() -> None:
    """앱 시작 시 1회 호출한다 (재실행마다 불려도 멱등이다).

    팔레트는 호출 시점의 st.context.theme으로 고른다 — 테마 전환은 리런을
    일으키므로 다음 리런에서 맞는 팔레트로 다시 주입된다.
    """
    palette = badge_palette_css(_detected_theme())
    st.html(f"<style>\n{_FONT_CSS}\n{palette}\n{_COMPONENT_CSS}\n</style>")
