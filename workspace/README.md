# workspace/

에이전트가 **실제 디스크에서 읽고 쓸 수 있는 유일한 디렉터리**입니다.

`file_read` / `file_write` 도구는 `FilesystemBackend(root_dir=여기, virtual_mode=True)`에
묶여 있습니다. `..`, `~`, 이 디렉터리 밖의 절대경로는 라이브러리가 차단합니다.

## 규칙: 여기에 비밀값을 두지 않습니다

경로 탈출은 막히지만, **이 안에 있는 파일은 에이전트가 전부 읽을 수 있습니다.**
프로세스 격리가 아니라 경로 제한일 뿐입니다.

- API 키, 자격증명, 개인정보를 이 디렉터리에 두지 마세요
- `.env`는 프로젝트 루트(이 디렉터리 **밖**)에 있어 접근되지 않습니다
- 웹 검색 도구를 함께 켠 에이전트에게는 여기 있는 내용이 외부로 나갈 경로가 생깁니다

## 쓰는 법

문서를 이 디렉터리에 넣고 `doc_qa_team`으로 질문하면 됩니다.

```bash
cp ~/some-report.md workspace/
python cli.py --spec templates/doc_qa_team.json
# you> workspace의 some-report.md 를 읽고 핵심만 정리해줘
```

위치를 바꾸려면 `.env`에 `DEEP_BUILDER_WORKSPACE=다른/경로`를 설정하세요.
