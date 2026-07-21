# report/ — MOBISCOPE 프로젝트 보고서 (LaTeX)

## 현재 상태
v0.1 뼈대(skeleton) — 목차 9절 + Abstract, 각 절 1~2문단만 채워져 있다. 컴파일 성공·PDF 생성 확인 완료. 절별 상세 서술은 다음 턴부터 진행.

## 구성
- `main.tex` — 본문 소스
- `main.pdf` — 컴파일 산출물(커밋 대상)
- `figures/` — 그림 자산 자리(현재 비어 있음, 7절은 `../docs/screenshots/dashboard.png`를 상대경로로 직접 참조)
- 참고문헌은 `report/` 안에 두지 않고 `../docs/paper/references.bib`를 상대경로로 참조한다(정본 단일화 — 사전 작업 세션에서 이미 검증·수정한 파일을 그대로 재사용).

## 필요 패키지 (MiKTeX 기준, 확인 완료)
- `xelatex` (한글 처리를 위해 pdflatex 대신 xelatex 사용)
- `kotex` (한글 조판, `xetexko` 자동 로드)
- `Malgun Gothic` 폰트(Windows 기본 내장 — 다른 OS에서 컴파일 시 `\setmainhangulfont`를 시스템에 있는 한글 폰트로 교체 필요, 예: Noto Sans CJK KR)
- `geometry`, `graphicx`, `booktabs`, `tikz`, `float`, `authblk`, `hyperref` — 전부 표준 MiKTeX 배포에 포함(`authblk`는 저자별 개별 소속을 번호로 묶어 표시하는 데 사용, 저자 5인·소속 5곳 전부 다름)

MiKTeX은 패키지 최초 사용 시 자동 설치를 시도한다(이번 세션에서 `kotex` 관련 패키지는 이미 로컬에 설치돼 있어 추가 설치 없이 바로 컴파일됨). 인터넷 연결이 없는 환경에서는 사전에 `kotex-utf`·`xetexko` 패키지를 MiKTeX Package Manager로 설치해 둘 것.

## 컴파일 명령

`report/` 디렉터리에서 실행(상대경로가 이 위치를 기준으로 하므로 반드시 이 디렉터리에서 실행):

```bash
xelatex -interaction=nonstopmode main.tex
bibtex main
xelatex -interaction=nonstopmode main.tex
xelatex -interaction=nonstopmode main.tex
```

4단계가 모두 필요한 이유: 1차 xelatex는 `\cite`를 임시 번호로만 채우고 `.aux`에 인용 목록을 기록한다. `bibtex`가 그 `.aux`를 읽어 `references.bib`에서 실제 서지정보를 찾아 `.bbl`을 만든다. 이후 2번의 xelatex는 각각 (a) `.bbl`을 반영해 참고문헌 목록을 실제로 그려 넣고 (b) 목차·각주·그림 번호 등 상호참조를 안정화한다(1회만 더 돌리면 `Label(s) may have changed` 경고가 남을 수 있어 총 2회 필요).

컴파일 후 생성되는 중간 파일(`*.aux .log .bbl .blg .out .toc`)은 `.gitignore`에 등록해 커밋하지 않는다 — `main.pdf`만 커밋 대상이다.

## 알려진 경고 (무해, 원인 확인됨)
```
LaTeX Font Warning: Font shape `TU/MalgunGothic(0)/m/it' undefined
LaTeX Font Warning: Some font shapes were not available, defaults substituted.
```
Malgun Gothic에 이탤릭 글리프가 없어 발생하는 경고로, 참고문헌의 저널명 이탤릭체 등에서 자동으로 정자체로 대체된다. 컴파일은 정상 완료되며 내용 손실 없음 — 필요하면 이탤릭 대응 한글 폰트(예: 나눔고딕)로 교체 검토 가능.

## 작업 중 발견·수정한 BibTeX 함정 (기록)
`references.bib` 엔트리 "내부"에서 필드 값 뒤에 같은 줄로 `% 확인 필요` 같은 주석을 붙이면 BibTeX가 "필드명 누락" 오류를 낸다(LaTeX 본문과 달리 BibTeX 파서는 엔트리 내부의 줄 끝 `%` 주석을 지원하지 않음). 모든 설명 주석을 엔트리 "앞" 줄로 옮겨 해결했다 — 필드 값 자체는 변경하지 않았다.

같은 이유로 `main.tex` 본문에서도 문장 끝에 바로 `% 출처: ...` 주석을 붙이면, 그 줄의 개행까지 주석이 함께 삼켜 다음 줄 단어가 띄어쓰기 없이 붙어버리는 문제가 있었다(예: "...텍스트이며,이를" — 공백 소실). 출처 주석은 항상 문장이 끝나는 줄과 "별도의 새 줄"에 두어 이 문제를 피했다.
