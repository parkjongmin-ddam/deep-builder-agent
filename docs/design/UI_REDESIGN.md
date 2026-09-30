# UI 리디자인 작업 지시서 (Phase 8)

## 0. 기준 자료
- 시안: `docs/design/deep_builder_agent_Redesign.html` (Claude Design 산출물)
  - 화면: 빌더 1a/1b, 평가 2a/2b, 로그인 3a/3b, 권한 거부 4a/4b, 스타일 가이드 5a
  - 분홍 태그 = 해당 요소의 Streamlit 컴포넌트. 구현 시 이 매핑을 따른다
- 시안의 샘플 데이터는 전부 가상이다. 실제 값으로 대체한다
  - 대화 예시, 평가 케이스 6건·점수, 데모 주체 `reviewer@demo`, 모델명 `claude-sonnet-4-5`
  - 실제: 케이스 21건(`eval/cases/builder_cases.json`), 기본 모델 `claude-sonnet-4-6`
- 작업 전 BUILD_SPEC.md를 읽고, 완료 후 결정 로그에 Phase 8 항목을 추가한다

## 1. 원칙 (CLAUDE.md 준수)
- `ui/app.py`는 그리기만 한다. 판단·가공 로직은 `ui/state.py`의 순수 함수로 두고 테스트한다
- `AgentSpec` 스키마는 변경하지 않는다 (SPEC_VERSION 상향 없음)
- deepagents·Streamlit API는 추측하지 않는다. 설치된 버전의 소스/문서로 확인 후 사용한다
- 단계마다 `pytest tests/ -q` 통과 확인. UI 변경이므로 `-m integration`(AppTest)까지 돌린다
- 커밋은 단계별로 나눈다. 메시지 형식 `phase8: <변경 요약>`

## 2. 작업 단계

### 단계 1. 테마·공통 스타일 (로직 변경 없음)
- 설치된 Streamlit 버전 확인
  - `[theme.light]` / `[theme.dark]` 분리 섹션 지원 여부 확인
  - 미지원이면 단일 `[theme]`로 다크 기준 적용하고 BUILD_SPEC.md에 기록
  - requirements.txt에 streamlit 버전 고정 (현재 미고정)
- `.streamlit/config.toml` 추가: 스타일 가이드 5a의 색상·폰트 값 반영
- Pretendard 폰트 적용 (config.toml 폰트 설정 또는 CSS 주입)
- CSS 주입은 `ui/style.py` 한 곳에 모은다. Streamlit 내부 클래스명 의존은 최소화하고, 사용한 선택자는 주석으로 남긴다
- 상태 표시 이모지(✅❌⚠️)를 Material 아이콘(`:material/check_circle:` 등)으로 교체

### 단계 2. 빌더 탭 레이아웃
- 좌우 패널: `st.columns(2)` + 각각 `st.container(height=...)`로 독립 스크롤
- 사이드바: 사용자(IAM) 카드, 역할 배지, 허용 행위·도구 경계 칩, 환경 점검 목록 (시안 1a)
- 현재 명세: `st.table(spec_overview)` → 카드형. 도구는 배지, 팀 구성은 `st.dataframe(column_config=...)`
- 성공·오류 메시지: 시안의 통일된 체계로 교체 (`st.success/st.error` + Material 아이콘)
- 권한 없는 버튼: 비활성 + 사유 문구 (스타일 가이드 5a의 비활성 상태 참조)

### 단계 3. 명세 버전 이력 (로직 추가)
- 저장 방식: `specs/<name>/v1.json, v2.json …` 이력 파일 누적. 최신본은 기존 경로 `specs/<name>.json`에도 유지해 CLI 호환을 보존한다
- 버전 번호는 이력 파일 개수로 계산 (스키마 필드 추가 없음)
- 함수 위치: 저장은 `builder/builder.py`(save_spec 확장 또는 별도 함수), 버전 조회는 `ui/state.py`
- 테스트: 연속 저장 시 v1→v2→v3 증가, 기존 최신본 경로 유지, 같은 이름 덮어쓰기 없음
- UI: 명세 카드에 `v3` 배지, 저장 메시지에 `v2 → v3` 표시
- 변경 내역: `st.code(diff, language="diff")`로 추가/삭제 색 구분. `format_diff` 출력이 diff 문법(`+`/`-` 접두)과 맞지 않으면 변환 함수를 state.py에 추가

### 단계 4. 대화 중 위임·도구 호출 표시 — 1차 (로직 추가)
- 현재 `render_history`는 도구만 호출한 턴을 버린다. 이력에서 단계를 추출하는 함수를 `ui/state.py`에 추가
  - 입력: 한 턴의 메시지 목록 (AIMessage.tool_calls, ToolMessage)
  - 출력: 단계 목록 `[(kind, name, args_summary, result_summary)]`
  - kind: 서브에이전트 위임(`task` 도구, subagent_type 인자) / 일반 도구 호출
- 표시: 에이전트 응답 위에 `st.status(state="complete")`, 단계는 들여쓰기 줄 (시안 1a). `st.status` 안에 expander는 넣지 않는다
- 이 단계에서는 리더 수준(위임 대상 + 리더의 도구 호출)까지만 표시한다. 소요시간은 표시하지 않는다
- 테스트: 위임 포함 이력, 도구만 있는 이력, 텍스트만 있는 이력 각각의 추출 결과

### 단계 5. 평가 탭 대시보드 (로직 추가)
- 상단 지표 3개: 통과율, 심판 평균, 실패 케이스 수 → `st.columns(3)` + `st.metric(border=True)`
- 검사 항목별 통과율: `ui/state.py`에 `EvalReport` → 검사 이름별 (통과 수, 전체 수) 집계 함수 추가
  - 실제 검사 5종 사용: expected_tools, forbidden_tools, team_shape, subagent_tools, guardrail
  - 화면 표기용 한글 라벨 매핑도 state.py에 둔다
  - 표시: `st.progress` (시안 2a)
- 케이스 목록: `st.dataframe`, 실제 21건
- 케이스별 상세: 실패 케이스 먼저, `st.expander(icon=...)`. 검사 결과는 칩, 심판 코멘트는 시안 형태
- 마지막 실행 시각·소요시간: 실행 전후 시각을 session_state에 저장
- expander 제목 우측 정렬은 CSS 주입이 필요하다. 안 되면 제목 뒤에 붙여 표시해도 된다
- 테스트: 집계 함수 (전부 통과, 일부 실패, 케이스 오류로 checks가 빈 경우)

### 단계 6. 로그인·권한 거부 화면
- 로그인 전(3a): `st.columns([1,1,1])` 가운데에 `st.container(border=True)` 카드 + `st.button(on_click=st.login)`
- 권한 거부(4a): 같은 카드 형태 + 사유 + 로그아웃 + 관리자 안내 문구
- `main()`의 OIDC 게이트 흐름과 `st.stop()` 위치는 바꾸지 않는다

### 단계 7. 스트리밍·서브에이전트 내부 단계 (조사 후 결정)
- 먼저 조사만 한다. 코드 변경 전 결과를 보고한다
  - deepagents 0.7.5에서 `agent.stream(..., subgraphs=True)`로 서브에이전트 내부 도구 호출을 받을 수 있는지
  - 단계별 소요시간 측정이 가능한지
- 가능하면: `agent_reply`를 스트리밍 방식으로 바꾸고 `st.status`를 실시간 갱신, 소요시간 표시
- 불가하면: 단계 4 수준 유지, BUILD_SPEC.md에 사유 기록

## 3. 완료 조건
- 시안 1a~4b의 구조가 실제 앱에서 재현됨 (다크/라이트 전환 포함)
- `pytest tests/ -q` 및 `-m integration` 통과
- BUILD_SPEC.md 결정 로그 갱신 (테마 방식, 버전 이력 방식, 단계 7 결과)
- README.md의 Streamlit UI 섹션 스크린샷·설명 갱신
