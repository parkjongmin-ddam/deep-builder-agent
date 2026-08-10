"""콘솔 입출력 인코딩 — Windows cp949 함정을 막는다.

**왜 공용 모듈인가**: 같은 버그가 진입점마다 따로 났다. Phase 1에서 `cli.py`에
고쳤는데 `eval/runner.py`는 그 함수를 물려받지 못해, 리포트를 파일로 넘기는 순간
`UnicodeEncodeError`로 죽었다 — 평가 21건을 다 돌린 **뒤에** 출력 단계에서.

콘솔에 직접 찍을 때는 드러나지 않는다. 리다이렉트·파이프일 때 파이썬이
로케일 코덱(한국어 Windows는 cp949)을 고르기 때문이다. 그래서 손으로 돌려보면
멀쩡하고 로그로 저장할 때만 깨진다.

새 진입점을 만들면 여기를 부른다. 복사가 아니라 공용화가 답이다.
"""

from __future__ import annotations

import sys


def force_utf8_stdio() -> None:
    """표준 입출력을 UTF-8로 고정한다.

    Windows 기본 콘솔 코덱(cp949)에서는 출력 시 이모지·일부 기호가
    `UnicodeEncodeError`를 내고, 파이프 입력 시 한글이 서로게이트로 디코딩되어
    이후 인코딩이 실패한다.

    `reconfigure`가 없는 스트림(테스트가 갈아끼운 가짜 객체 등)은 건너뛴다 —
    인코딩 고정 실패가 프로그램을 죽일 이유는 없다.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
