# 프로젝트 기획안 — deep_builder_agent

## 프로젝트 개요

- **프로젝트 주제**: 자연어 대화로 AI 에이전트를 생성·실행·평가하는 대화형 에이전트 빌더 제작
- **프로젝트명**: deep_builder_agent
- **구성원**: 박종민 (1인)
- **GitHub Repo**: https://github.com/parkjongmin-ddam/deep-builder-agent

## R&R

**박종민**
- 기획·설계·개발·문서화·발표 전담 (1인 프로젝트)
- 설계 원칙: Phase 게이트 기반 단계별 검증, BUILD_SPEC.md로 결정 이력 관리

## 사용 스택

| 구분 | 내용 |
|---|---|
| 언어 | Python 3.11+ (3.13에서 전체 테스트 통과 검증) |
| 에이전트 하네스 | LangChain deepagents (LangGraph 기반) |
| LLM | Claude Sonnet 4.6 (Anthropic API) — Builder 기본 모델, 팀원별 모델 차등 지정 지원 |
| 스키마 검증 | Pydantic v2 |
| 도구 연결 | MCP (stdio·HTTP transport, 실연결 검증 완료) |
| UI | Streamlit |
| 평가·관측 | LangSmith 트레이싱 + 자체 평가 스위트(기계 판정 + LLM-as-judge) |
| 개발 도구 | Claude Code, pytest, GitHub |

## 지원 기능

- 자연어 요구 → 에이전트 명세(AgentSpec JSON) 자동 생성
  - 모호한 요구는 질문 없이 **가정을 명세에 명시**하고 즉시 생성 (인터뷰 왕복 대신 단발 생성 + `/revise` 수정 루프로 보완)
- 명세 검증 하네스: 스키마 검증, 도구 화이트리스트(Pydantic 밸리데이터가 거부), 가드레일 프롬프트 강제 주입(`ensure_guardrail()`), 실패 시 최대 3회 재생성 루프
- 도구 레지스트리: 내장 도구(웹검색·계산 전용 AST 평가·Python 실행·파일 I/O) + MCP 서버 연결(stdio/HTTP)
- 멀티에이전트 팀 자동 구성: 리더 + 서브에이전트 템플릿(리서처·작성자 등), 서브에이전트에도 도구 격리 적용
- 생성 직후 즉시 대화 실행, 자연어 수정 루프(`/revise` — 변경 내역 diff 표시 후 재생성)
- 평가: LangSmith 트레이싱 + 평가 케이스 21건 기반 기계 판정·LLM-as-judge 점수 (심판 모델을 Builder와 다른 모델로 분리해 자기 채점 편향 제거)
- IAM 레이어: 사용자 RBAC(admin/builder/operator/viewer) + **에이전트 권한 경계(permissions boundary)** — 생성되는 에이전트(리더·팀원 전원)의 도구가 생성자의 역할 경계를 초과할 수 없음, deny-by-default, 허용·거부 전건 감사 로그(JSONL)

## 산출물 목표

- 실행 가능한 오픈소스 코드 (GitHub, 테스트 307건 포함)
- Streamlit 데모: 빌더 채팅 / 생성 에이전트 채팅 2패널 + 평가 탭
- 기술 보고서(아키텍처·설계 원칙·평가 결과: REPORT.md) 및 README·BUILD_SPEC.md(설계 결정 원장)·DEMO.md(데모 대본)
- 데모 영상
- 정량 목표: 자연어 요구 **21건** 평가 케이스 기준 유효 명세 생성 성공률, MCP 실연결·멀티에이전트 실행 성공, 평가셋 응답 품질 점수, 단일 vs 팀 구성 비용·품질 실측 비교

## 각오 한마디!

5년간 IAM 인프라를 운영하며 "동작하는 것"과 "안전하게 재현되는 것"의 차이를 배웠습니다. 에이전트도 같은 기준으로, 작은 baseline부터 검증하며 끝까지 완주하겠습니다.
