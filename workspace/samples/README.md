# 샘플 작업공간 파일 (Phase 9)

ADFS·계정 동기화 도메인의 **가상 데이터**다. 실제 사내 호스트·도메인·계정·로그는
없으며, 모든 값은 `contoso.com` / `CONTOSO\userNN` 류의 일반 예시다.
프로필 템플릿(adfs_log_triage_team, sync_report_team, auth_error_analysis_team)의
실행 재료로 쓰인다 — 에이전트 가상 경로로는 `/samples/<파일명>`이다.

| 파일 | 내용 |
|---|---|
| `adfs_events.csv` | AD FS Admin 이벤트 로그 export 형식의 가상 오류 12건 |
| `sync_result_2026-09.csv` | 계정 동기화 결과 가상 37행 (성공 27 · 실패 6 · 비활성 4, user17은 재시도로 2행) |
| `dotnet_oidc_exception.txt` | ASP.NET Core OIDC 로그인 실패 예외 스택 1건 |
| `python_sync_traceback.txt` | 동기화 스크립트(ldap3) bind 실패 traceback 1건 |

## 사용한 오류 코드·이벤트 ID와 의도한 의미 (검토 대상)

작성 원칙: **실제 의미와 일치한다고 확신하는 코드만 썼고**, 확신이 없는 것은
코드 없이 메시지 기반으로 적었다. 아래 표가 실무 의미와 다르면 알려달라 —
샘플과 이 문서를 함께 고친다.

### AD FS Admin 이벤트 ID (`adfs_events.csv`)

| 이벤트 ID | 의도한 의미 | 샘플에서의 시나리오 |
|---|---|---|
| 342 | Token validation failed — 자격 증명 오류(틀린 암호) 또는 잠긴 계정 | user07 연속 3회 암호 오류, user12는 **AD 계정 잠금**(도메인 잠금 정책) 시나리오 — ADFS Extranet (Smart) Lockout이 아니다, user20 단건 |
| 364 | Encountered error during federation passive request — 수동(브라우저) 인증 요청 처리 중 오류의 일반 래퍼. 세부 원인은 Exception details에 | MSIS7007·MSIS7065·일반 오류의 컨테이너 |
| 111 | Federation Service가 WS-Trust 요청 처리 중 오류 | WS-Trust Issue 요청 실패 2건 |
| 276 | 페더레이션 서버 프록시(WAP)가 Federation Service에 인증 실패 — 프록시 신뢰(trust) 문제 (2026-10-01 Microsoft 문서로 의미 재확인) | wap01 프록시 신뢰 인증서 문제 1건 |

### MSIS 코드 (`adfs_events.csv`의 Exception details)

| 코드 | 의도한 의미 | 시나리오 |
|---|---|---|
| MSIS7007 | 요청한 relying party trust가 미등록/미지원(또는 비활성) | 미등록 RP `https://newapp.contoso.com/` 접근 2건 |
| MSIS7065 | 해당 경로를 처리할 등록된 프로토콜 핸들러 없음 | 비활성화된 `/adfs/ls/idpinitiatedsignon` 접근 1건 — 원인: `EnableIdpInitiatedSignonPage` 속성 비활성(ADFS 2016+ 기본값 false, `Set-AdfsProperties`로 변경) |

### Microsoft.IdentityModel IDX 코드 (`dotnet_oidc_exception.txt`)

| 코드 | 의도한 의미 |
|---|---|
| IDX20803 | OIDC 메타데이터(구성 문서)를 가져오지 못함 — ConfigurationManager 수준 |
| IDX20804 | 지정 주소에서 문서 자체를 받지 못함 — HttpDocumentRetriever 수준 (여기서는 내부 원인이 SSL 인증서 체인 오류) |

### LDAP 결과 코드 (`python_sync_traceback.txt`)

| 코드 | 의도한 의미 |
|---|---|
| result 49 (invalidCredentials) | LDAP bind 자격 증명 거부 |
| data 52e | AD 확장 하위 코드 — 암호 불일치 (시나리오: 서비스 계정 암호가 전날 교체됨) |

### 코드 없이 메시지 기반으로만 쓴 것

- 364의 일반 실패 1건("The sign-in request could not be completed...") — 특정 MSIS 코드를 단정하지 않았다
- 111의 Exception details — WS-Trust 실패의 세부 코드를 단정하지 않았다
- `sync_result_2026-09.csv`의 실패 사유(`duplicate-upn`, `attribute-invalid`,
  `connection-timeout`, `password-policy`)는 특정 제품의 코드가 아니라
  일반 용어다 — 샘플 동기화 스크립트가 쓰는 자체 분류라는 설정

## 주의

- 이 디렉터리는 에이전트가 읽을 수 있다(`workspace/` 경로 제한 안). **비밀값을 두지 않는다.**
- 파일을 수정하면 템플릿 실대화 예시(README·DEMO의 수치)와 어긋날 수 있다.
