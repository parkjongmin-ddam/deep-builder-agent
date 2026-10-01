"""전역 스타일 — CSS 주입은 이 파일 한 곳에 모은다 (Phase 8 단계 1).

색상·반경·위젯 테두리·폰트 패밀리는 `.streamlit/config.toml`
([theme.light] / [theme.dark])이 단일 진실 원천이다. 여기서는 config로
표현할 수 없는 것만 주입한다:

- **웹폰트 로드** — config의 `font = "Pretendard Variable"`은 패밀리 이름을
  지정할 뿐 폰트 파일을 가져오지 않는다. CDN @import로 로드하고, 오프라인이면
  config의 폴백(sans-serif / monospace)으로 조용히 내려간다.
  로컬 woff2 커밋은 기각 — 사유는 BUILD_SPEC.md Phase 8 결정 로그.

- **도구 배지·칩·환경 점검·신원 카드** (단계 2) — `ui/state.py`의 `*_html`
  함수들이 만드는 마크업을 st.html로 렌더한다. 색 팔레트는 **CSS
  `light-dark()` 쌍**으로 양 테마를 한 선언에 담는다 — Streamlit 프런트엔드가
  앱 컨테이너에 `color-scheme`을 activeTheme 기준으로 설정하는 것을 설치본
  1.64.0 index.js로 확인했고, light-dark()는 그 값을 요소 위치에서 평가하므로
  테마 전환 **즉시**(파이썬 리런 없이) 맞는 색이 된다. 이전의
  `st.context.theme.type` 고정 방식은 전환 직후 한 리런 동안 이전 팔레트를
  주입하는 결함이 있었다(실화면 확인, 2026-10-01). light-dark() 미지원 구형
  브라우저는 라이트 기본 + prefers-color-scheme 다크로 폴백한다.

Streamlit 내부 클래스명 의존은 최소화한다. 자체 클래스(`.dba-*`) 외에
사용 중인 내부 선택자는 다음 하나다 (Streamlit 버전 업그레이드 시 확인할 것):
- `[data-testid="stChatMessage"]` — 채팅 메시지 영역 한정 보정 2건.
  (1) 에이전트 응답 속 마크다운 h1~h3가 페이지 섹션 제목보다 커 보이는
  것을 본문보다 약간 큰 수준으로 축소, (2) 넓은 표가 패널 폭을 넘을 때
  가로 스크롤 + 셀 줄바꿈 방지. 메시지 영역 밖의 제목·표에는 손대지 않는다.
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


def badge_palette_css() -> str:
    """양 테마를 한 번에 담는 색 변수 블록 — 테마 분기·리런 의존이 없다.

    `light-dark(라이트값, 다크값)`은 사용 요소의 color-scheme으로 평가된다.
    Streamlit은 앱 컨테이너에 color-scheme을 activeTheme 기준으로 즉시
    설정하므로(설치본 index.js 실측), 테마를 바꾸면 파이썬 리런 없이도
    맞는 색이 된다. 폴백 블록(라이트 기본 + prefers-color-scheme 다크)은
    light-dark() 미지원 구형 브라우저용이며, @supports 블록이 소스 뒤에
    있어 지원 브라우저에서는 항상 이긴다.
    """
    pairs = "".join(
        f"--dba-{name}: light-dark("
        f"{_PALETTES['light'][name]}, {_PALETTES['dark'][name]});"
        for name in _PALETTES["light"]
    )
    return (
        _root_vars(_PALETTES["light"])
        + "\n@media (prefers-color-scheme: dark) {"
        + _root_vars(_PALETTES["dark"])
        + "}"
        + "\n@supports (color: light-dark(#000, #fff)) {"
        + f":root {{{pairs}}}"
        + "}"
    )


_COMPONENT_CSS = """
/* 칩·배지 기본 폰트는 본문 — 한글 라벨을 고정폭으로 그리면 자간이 벌어진다.
   식별자를 그대로 보여주는 배지(vN 등)만 --mono 변형으로 고정폭을 쓴다. */
.dba-badge {
  display: inline-flex; align-items: center;
  height: 22px; padding: 0 7px; margin: 0 4px 4px 0;
  border-radius: 6px;
  font: 500 12px/1 "Pretendard Variable", Pretendard, sans-serif;
  background: color-mix(in srgb, var(--dba-info) 14%, transparent);
  color: var(--dba-info);
}
.dba-badge--accent {
  background: color-mix(in srgb, var(--dba-accent) 14%, transparent);
  color: var(--dba-accent);
}
.dba-badge--mono {
  font: 500 11.5px/1 "JetBrains Mono", monospace;
}
.dba-chip {
  display: inline-flex; align-items: center;
  height: 22px; padding: 0 7px; margin: 0 4px 4px 0;
  border-radius: 5px;
  font: 500 12px/1 "Pretendard Variable", Pretendard, sans-serif;
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

/* 채팅 메시지 안 마크다운 보정 — 선택자 근거는 모듈 docstring 참조 */
[data-testid="stChatMessage"] h1 { font-size: 1.15rem; padding: 0.25rem 0; }
[data-testid="stChatMessage"] h2 { font-size: 1.1rem; padding: 0.2rem 0; }
[data-testid="stChatMessage"] h3 { font-size: 1.05rem; padding: 0.15rem 0; }
[data-testid="stChatMessage"] table {
  display: block; max-width: 100%;
  overflow-x: auto;
}
[data-testid="stChatMessage"] table th,
[data-testid="stChatMessage"] table td {
  white-space: nowrap;
}
"""


def inject_css() -> None:
    """앱 시작 시 1회 호출한다 (재실행마다 불려도 멱등이다).

    팔레트는 light-dark() 쌍이라 호출 시점의 테마를 알 필요가 없다 —
    테마 전환은 브라우저 쪽 color-scheme 변경만으로 즉시 반영된다.
    """
    st.html(f"<style>\n{_FONT_CSS}\n{badge_palette_css()}\n{_COMPONENT_CSS}\n</style>")
