# 보건관리자 채용 모아보기

휴대폰·아이패드·노트북에서 공고를 고용형태와 지역으로 필터링하는 웹페이지입니다.
수집과 자동 실행에는 Python만 사용하며 GPT/API 키는 필요 없습니다.

## 현재 상태

- 고용형태: 정규직 / 비정규직 / 확인 필요
- 지역: 서울 / 경기 / 기타 지역 / 확인 필요
- 회사명·제목 검색, 마감일 정렬, 마감 공고 숨기기, 원문 링크
- 관심 공고는 기기별 브라우저에 저장 (다른 기기와 동기화하지 않음)
- 자동 출처: 인천국제공항공사 공식 RSS, 보건복지부 채용 공식 RSS
- 공식 원문을 직접 확인한 초기 공고 2건 포함 (자동 갱신 대상 아님)
- 공개 주소: https://temporarykorean.github.io/health-manager-jobs/
- GitHub Actions 첫 실행에서 RSS 2곳 수신 및 공개 배포 성공을 확인했습니다.
- 매일 한국 시간 오전 9시 17분 수집·배포 예약이 main 브랜치에 연결되어 있습니다.
- 첫 수집은 게시물 47개 중 관련 신규 공고 0개이며, 직접 확인한 기존 공고 2건을 보존했습니다.
- 배포 후 인증 없이 HTML·정적 파일·최신 데이터 일치를 자동 검증합니다.

## 내 컴퓨터에서 결과 보기

`dist/index.html`을 브라우저로 열면 됩니다. 데이터가 포함되어 있어 더블클릭으로도 볼 수 있습니다.
파일 공유는 현재 화면만 전달합니다. 최신 공고가 자동으로 전달되는 공유 링크를 만들려면 아래 인터넷 배포가 필요합니다.

```bash
cd /Users/jang-ujin/health-manager-jobs/site
python3 collector.py
python3 build.py
```

수집기가 종료 코드 2를 반환하면 모든 출처에 접속하지 못한 것입니다.
이때도 기존 데이터는 보존되며, `build.py`를 실행하면 실패 상태를 함께 표시합니다.
웹페이지의 ‘화면 새로고침’은 배포된 데이터를 다시 읽으며, 수집기를 새로 실행하는 버튼은 아닙니다.

## GitHub로 인터넷 공개 및 매일 자동 실행

이 **site 폴더 안의 파일**을 GitHub 저장소 루트에 업로드합니다. `site`라는 하위 폴더로 업로드하면 현재 워크플로 경로와 맞지 않습니다.
`.github/workflows/daily-jobs.yml`도 포함해야 합니다. `dist`, `.git`, `.openai`, `.sites-runtime`은 GitHub 배포에 필요 없습니다.

1. GitHub 계정에 공개 저장소를 만듭니다. 기본 브랜치는 `main`으로 사용합니다.
2. 위 파일들을 올립니다. GitHub Actions에 저장소 데이터 파일을 커밋할 수 있는 권한이 필요합니다. 브랜치 보호 정책이 봇 커밋을 막으면 수집 기록 저장이 실패합니다.
3. 저장소 **Settings → Pages → Source → GitHub Actions**를 선택합니다.
4. **Actions → 보건관리자 공고 수집 및 웹페이지 배포 → Run workflow**로 첫 실행을 시작합니다.
5. 성공하면 Settings → Pages 또는 실행 기록의 `github-pages`에 공개 주소가 나옵니다. 아내에게 그 링크를 공유합니다.

설정 후 매일 **한국 시간 오전 9시 17분**에 수집·배포를 시도합니다. GitHub 상황에 따라 지연될 수 있으며, 장기간 활동이 없는 공개 저장소는 예약 실행이 중단될 수 있습니다.
내 컴퓨터가 꺼져 있어도 GitHub가 실행합니다. GPT 사용량은 들지 않으며 GitHub 자체 요금·한도·정책을 따릅니다.

전체 수집이 실패해도 기존 공고와 수집 실패 상태를 배포한 다음, 실행 기록에는 실패를 표시합니다.
이전 데이터는 `data/jobs.json`으로 저장소에 커밋해 다음 실행에 사용합니다.

## 분류의 범위와 한계

- 고용형태는 RSS의 명시 항목이 있으면 그 값을, 없으면 제목을 사용합니다. 불분명하거나 정규직/비정규직이 혼재하면 확인 필요입니다.
- 정규직 전환 가능 계약직은 현재 비정규직입니다. 무기계약직·공무직은 기관별 정의가 달라 확인 필요로 둡니다.
- 지역은 명시된 근무지에서 판단합니다. 회사 주소나 회사명으로 추측하지 않습니다. 인천은 요청 기준상 기타 지역입니다.
- RSS에 근무지나 마감일이 없으면 확인 필요가 많을 수 있습니다. 상세 첨부파일/PDF는 현재 분석하지 않습니다.
- 마감일은 명시된 마감일/접수기간에서만 추출합니다. 시각이 없으면 해당 날짜의 한국 시간 23:59:59를 기준으로 표시합니다.
- RSS에서 사라진 공고를 바로 삭제하지 않습니다. 마감일 미기재 공고가 계속 보일 수 있으며, 접수 여부는 원문에서 확인해야 합니다.
- 검색 키워드: 보건관리자, 산업간호사 (띄어쓰기 변형 포함).
- 사람인 공식 API 수집을 준비했습니다. 승인 후 발급받은 키를 GitHub 저장소 Settings → Secrets and variables → Actions에 `SARAMIN_ACCESS_KEY`라는 이름으로 등록하고 워크플로를 실행하면 연결됩니다. 키는 채팅이나 소스에 넣지 않습니다. 키 미설정 시 화면에 연결 대기로 표시합니다.
- 사람인 키워드별 최대 10페이지(110건씩)를 수집하며 초과 시 실패로 표시하고 이전 데이터를 보존합니다.
- 잡코리아 공식 API는 개인 사용 승인 제한으로 미연결입니다. 두 사이트의 키워드 검색 링크를 제공합니다.

## 검증

```bash
python3 -m unittest discover -s tests -v
node --check web/app.js
node tests/test_frontend.mjs
python3 build.py
```

테스트는 고용형태 오분류, 복수 지역, RSS/Atom 처리, 잘못된 응답, 수집 실패 시 데이터 보존, 중복 제거를 확인합니다.
실제 사이트 접속 및 GitHub 배포는 인터넷에서 별도 확인해야 합니다.

## 주요 파일

| 파일 | 역할 |
| --- | --- |
| `collector.py` | 공고 수집과 분류 |
| `sources.json` | 공식 RSS 출처 목록 |
| `data/jobs.json` | 공고와 수집 상태 |
| `web/` | 화면과 필터 |
| `build.py` | 배포용 HTML과 데이터를 생성 |
| `.github/workflows/daily-jobs.yml` | 매일 수집하고 GitHub Pages로 배포 |

출처: [공항 채용 게시판](https://www.airport.kr/co_ko/849/subview.do?FNCT_CODE=229), [보건복지부 RSS 안내](https://www.mohw.go.kr/menu.es?mid=a10807000000), [캐논코리아 원문](https://recruit.lotte.co.kr/apply/announcement/detail/21988537?compcd=60005), [서울신문 원문](https://recruit.seoul.co.kr/recruit/view.php?idx=266).
배포 설정 참고: [GitHub Pages 공식 안내](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

## 추가 채용 사이트

LinkedIn은 보건관리자·산업간호사 검색 바로가기를, CATCH는 채용 검색 페이지 바로가기를 제공합니다. 공고 데이터 자동 수집은 연결하지 않았습니다. CATCH 공식 Open API 안내는 기업정보용이며 채용공고 제공 API는 확인되지 않았습니다.
