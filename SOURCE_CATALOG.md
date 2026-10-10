# 출처 및 공통 플랫폼 조사 (2026-10-10)

자동 수집 활성 여부와 단순 회사/플랫폼 발견을 구별합니다. 회사마다 별도 수집기를 복제하지 않고, 플랫폼 어댑터 + 호스트별 설정으로 확장합니다.

| 공통 플랫폼/출처 | 확인된 감시 대상 | 현재 연결 |
|---|---|---|
| [JOB-ALIO](https://job.alio.go.kr/recruit.do) | 한국철도공사, IBK기업은행, 한국중소벤처기업유통원 및 모든 등재 공공기관의 키워드 공고 | 키 없이 구조화된 목록·상세 연결. 기관별 크롤러 불필요. |
| [Greeting](https://www.greetinghr.com/) | [HYBE](https://careers.hybecorp.com/ko/home), [스마트스코어](https://smartscore.career.greetinghr.com/ko/home) | 공통 수집기 구현, HYBE 활성. 스마트스코어는 공개 목록 5건에서 관련 제목 없음, 별도 이용조건 검토 전 미연결. |
| recruiter.co.kr | GS건설(gsenc), 현대엔지니어링(hec), HDC현대산업개발(hdcr), 한국중소벤처기업유통원(kodma) | 도메인 공통 확인. kodma robots는 일반 봇 `/` 비허용, `/appsite/`와 `/bbs/appsite/`만 허용. `/app/jobnotice/` 직접 수집 제외. hec는 `/career/home`으로 변경되어 기존 파서 재사용을 보장할 수 없음. 허용된 공통 목록 데이터 구조를 검증하기 전 대기. |
| Incruit 계열 | IBK기업은행(ibk/ibk4.incruit.com) | 공개 목록 확인. robots의 `/Hire/` 비허용 경로와 실제 경로 구별 및 이용조건/상세 파서 검토 전 직접 연결 대기. ALIO에 게시된 IBK 공고는 ALIO로 감시. |
| [삼성 Careers](https://www.samsungcareers.com/) | 삼성 계열·삼성E&A | 공식 FAQ가 그룹 채용사이트를 안내. 그룹 사이트 하나로 연결할 후보, 동적 목록·접근조건 검증 전 대기. |
| [SK Careers](https://www.skcareers.com/) | SK 계열·SK에코플랜트 | 그룹 공통 채용사이트 후보. 조건/데이터 검증 전 대기. |
| [LG Careers](https://careers.lg.com/) | LG 계열 | 공통 사이트 확인, 동적 목록 파서/접근조건 검증 전 대기. |
| [롯데 채용](https://recruit.lotte.co.kr/) | 롯데 계열 | 공개 목록 확인. robots 요청에 정상 규칙 대신 접근 오류 HTML이 와 자동 접속 허용으로 해석하지 않음. 초기 직접 확인 캐논 공고는 보존. |
| [CJ RECRUIT](https://recruit.cj.net/recruit/ko/recruit/process/process_info.fo) | CJ 계열·CJ대한통운 건설부문 | 그룹 공통 사이트 후보. 조건/목록 구조 검증 전 대기. |
| [현대자동차 채용](https://recruit.hyundai.com/) | 현대자동차 | talent.hyundai.com으로 이동 및 대기 처리 화면. 그룹 전체가 같은 ATS를 쓴다고 가정하지 않음. |
| [KT 채용](https://recruit.kt.com/) | KT | 동적 사이트, 공개 데이터/조건 확인 전 대기. |
| [DL이앤씨 공식 현장 채용](https://www.dlenc.co.kr/careers/job/FieldEmpList.do) | DL이앤씨 현채직/PJT직 | 자체 사이트 확인. 직렬별 표·첨부파일 및 이용조건 검토 전 대기. |
| [원에이치알 기반 대우건설 채용](https://recruit.daewooenc.com/) | 대우건설 | 공식 홈페이지에서 원에이치알 표기 확인. 여러 고객이 함께 쓰는 솔루션 후보, robots/조건/목록 파서 검증 전 대기. |
| [롯데건설 공식 채용](https://career.lottecon.co.kr/) | 롯데건설 | 그룹 사이트 외 현장 별도 사이트 후보, 자동 미연결. |

공식 연결 근거:

- [GS건설 공식 인재채용](https://www.gsconst.co.kr/Recruit/RecruitGuide.aspx?inner=1&type=5)의 채용공고 링크 → gsenc.recruiter.co.kr.
- [현대엔지니어링 공식 채용 보도자료](https://m.hec.co.kr/ko/pr/press-news/press-release/7655) → hec.recruiter.co.kr/appsite/company/index.
- [HDC현대산업개발 채용 담당자 공지](https://hdcr.recruiter.co.kr/bbs/appsite/notice/read/386652).
- [삼성E&A 공식 FAQ](https://www.samsungena.com/kr/careers/join-us/careers-faq?target=all) → samsungcareers.com.
- [HYBE 공개 개인정보 방침](https://careers.hybecorp.com/privacypolicy)은 두들린의 채용 플랫폼 이용을 명시. 공개 HTML도 Greeting임을 확인.

현대건설, 포스코이앤씨, SGC E&C, 한국GM은 이번 최소 완성본에서 사용 가능한 공통 ATS와 접근 조건까지 검증하지 못했습니다. 미연결을 '공고 없음' 또는 '수집 성공'이라고 표시하지 않습니다. 한국GM의 Workday 사용은 추가 공식 확인 대상입니다. 모든 요청 회사에 대해 공고 수집을 완료한 버전은 아닙니다.

## 허용/제외 정책

- LinkedIn 제외. 사람인·잡코리아 공식 API 승인 대기. CATCH는 채용용 공개 API 확인되지 않아 직접 수집 없음.
- robots 허용만으로 이용조건 허가를 단정하지 않으며, 기록된 범위의 공개 메타데이터만 처리합니다.
- 로그인, CAPTCHA, 접근 차단, 비공개 API, User-Agent 위장, PDF 대량 다운로드를 우회 수단으로 사용하지 않습니다.
- 네이버 공식 검색 API는 인증 대기. `discovery_domains`에 공식 도메인 추가 후 검색 결과 링크만 별도 후보로 저장하며 원문 방문은 안 합니다.
- 기관 페이지 검토는 90일 후 갱신 필요. 만료 시 연결 대기로 전환합니다.
