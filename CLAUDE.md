# CLAUDE.md — deep_builder_agent

생성 AI 교육과정 파이널 과제. 자연어로 AI 에이전트를 생성·실행·평가하는 빌더 (Deep Agent Builder 유사 미니 버전).

## 진실의 원천
- 모든 설계 결정과 현재 상태는 BUILD_SPEC.md에 있다. 작업 전 반드시 읽고, 결정 변경 시 갱신한다.
- Phase 게이트를 넘기 전에는 다음 Phase 기능을 구현하지 않는다 (카파시 원칙).

## 개발 환경
- 프로젝트 전용 venv를 쓴다: `./.venv/Scripts/python.exe` (전역 파이썬의 langchain 버전과 충돌하므로 전역에 설치하지 않는다)
- 의존성은 requirements.txt에 고정한다. 비밀값은 .env(커밋 금지), 형식은 .env.example 참조

## 아키텍처 (4레이어)
- builder/  — 메타 에이전트: 자연어 → AgentSpec JSON
- registry/ — 도구 레지스트리 + MCP 커넥터 (Phase 2)
- runtime/  — AgentSpec 검증(spec.py) → deepagents 인스턴스화(factory.py)
- ui/       — Streamlit 2패널 (Phase 4)
- eval/     — LangSmith + LLM-as-judge (Phase 4)

## 코딩 규칙
- Python 3.11+, Pydantic v2, 타입 힌트 필수
- 도구 참조는 문자열 키로만. 임의 임포트 경로/코드 실행 경로를 스펙에 넣지 않는다
- 스키마 변경 시 SPEC_VERSION 상향 + BUILD_SPEC.md에 사유 기록
- 외부 라이브러리 API(특히 deepagents)는 추측하지 말고 설치된 버전 문서/소스로 확인 후 사용

## 검증 루프
- 모든 runtime/ 변경은 `./.venv/Scripts/python.exe -m pytest tests/ -q` 통과 후 커밋
- Phase 완료 조건: 동작 데모 성공 + 테스트 통과 + BUILD_SPEC.md 갱신 + 커밋
- 커밋 메시지: `phase{N}: <변경 요약>`

## 금지
- Phase 1~2에서 subagents 활성화 금지 (spec.py 밸리데이터가 강제)
- CLAUDE.md/훅/커스텀 커맨드 등 개발 하네스 개선에 반나절 이상 쓰지 않는다
