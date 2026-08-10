# CLAUDE.md — deep_builder_agent

자연어로 AI 에이전트를 생성·실행·평가하는 빌더.

## 진실의 원천
- 모든 설계 결정과 현재 상태는 BUILD_SPEC.md에 있다. 작업 전 반드시 읽고, 결정 변경 시 갱신한다.
- Phase 게이트를 넘기 전에는 다음 Phase 기능을 구현하지 않는다 (카파시 원칙).

## 개발 환경
- 프로젝트 전용 venv를 쓴다: `./.venv/Scripts/python.exe` (전역 파이썬의 langchain 버전과 충돌하므로 전역에 설치하지 않는다)
- 의존성은 requirements.txt에 고정한다. 비밀값은 .env(커밋 금지), 형식은 .env.example 참조

## 아키텍처 (4레이어)
- builder/  — 메타 에이전트: 자연어 → AgentSpec JSON. 프롬프트의 도구 목록은 registry에서 렌더링
- registry/ — 도구 레지스트리(registry.py) + 도구 구현(builtin.py) + MCP 커넥터(mcp.py).
              허용 도구 화이트리스트의 단일 진실 원천 — 도구를 늘리려면 여기에만 등록한다
- runtime/  — AgentSpec 검증(spec.py) → deepagents 인스턴스화(factory.py).
              서브에이전트 번역·도구 격리도 factory가 담당한다
- templates/ — 손으로 쓴 팀 스펙 JSON. `cli.py --spec`으로 바로 실행된다.
              Builder를 거치지 않으므로 가드레일 문장을 파일에 직접 써야 한다
- workspace/ — 에이전트가 실제 디스크를 읽고 쓸 수 있는 **유일한** 디렉터리.
              가상 루트가 `/`라 파일은 `/README.md` 형태로 보인다
- ui/       — Streamlit 2패널. app.py는 그리기만, 판단은 state.py의 순수 함수에 둔다
- eval/     — Builder 회귀 평가. checks.py(기계적 판정) + judge.py(LLM 심판) + runner.py(집계).
              `import eval`은 내장 함수를 가린다 — 항상 `from eval.x import y` 형태로 쓴다

## 코딩 규칙
- Python 3.11+, Pydantic v2, 타입 힌트 필수
- 도구 참조는 문자열 키로만. 임의 임포트 경로/코드 실행 경로를 스펙에 넣지 않는다
- 스키마 변경 시 SPEC_VERSION 상향 + BUILD_SPEC.md에 사유 기록
- 외부 라이브러리 API(특히 deepagents)는 추측하지 말고 설치된 버전 문서/소스로 확인 후 사용

## 검증 루프
- 모든 runtime/ 변경은 `./.venv/Scripts/python.exe -m pytest tests/ -q` 통과 후 커밋
- 빠른 피드백이 필요하면 `-m "not integration"` (프로세스·앱을 띄우는 느린 검증 제외)
- UI 변경은 단위 테스트만으로 부족하다. `AppTest`가 도는 `-m integration`까지 돌린다
- Builder 프롬프트·도구 레지스트리를 건드리면 `python -m eval.runner`로 회귀를 본다 (API 키 필요)
- Phase 완료 조건: 동작 데모 성공 + 테스트 통과 + BUILD_SPEC.md 갱신 + 커밋
- 커밋 메시지: `phase{N}: <변경 요약>`

## 금지
- 서브에이전트에 FilesystemMiddleware 없이 도구를 붙이지 않는다. 메인의 도구 화이트리스트는
  서브에이전트에 전파되지 않으며, 빠뜨리면 위임 한 번으로 셸(execute)이 열린다
  (실측 근거는 BUILD_SPEC.md 5-3)
- `workspace/`에 비밀값을 두지 않는다. 경로 탈출은 `virtual_mode`가 막지만 그 안의 파일은
  에이전트가 전부 읽는다 — 프로세스 격리가 아니라 경로 제한이다
- 파일 백엔드의 `root_dir`을 프로젝트 루트로 넓히지 않는다. `.env`가 읽히게 된다
- 보안 경계 테스트를 `pytest.raises(Exception)`만으로 쓰지 않는다. 오타난 메서드명이 던지는
  AttributeError를 '차단됨'으로 오인해 통과한 적이 있다 — 대조군(허용 경로가 실제로 되는지)을
  함께 두고, "비밀값이 결과에 없다"처럼 성질로 검사한다
- CLAUDE.md/훅/커스텀 커맨드 등 개발 하네스 개선에 반나절 이상 쓰지 않는다
