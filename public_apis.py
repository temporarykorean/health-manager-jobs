"""공식 공공 채용 API. 키는 환경변수에서만 읽고 원문 사이트는 방문하지 않는다."""
import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import urlencode, unquote, urlsplit, parse_qs
from urllib.request import Request, build_opener
from source_adapters import NoRedirect
from job_target import qualify_job

ENDPOINTS = {
    'alio_api': 'https://apis.data.go.kr/1051000/recruitment/list',
    'kto_api': 'https://apis.data.go.kr/B551011/ktorecruitment/getDatament',
    'gg_jobaba': 'https://openapi.gg.go.kr/GGJOBABARECRUSTM',
    'gg_worknet': 'https://openapi.gg.go.kr/EmplmntInfoStus',
}


def read_api(url, params):
    # urllib의 HTTPError에는 인증키가 들어간 URL이 포함된다. 외부에 원본 예외를 노출하지 않는다.
    try:
        with build_opener(NoRedirect()).open(Request(url + '?' + urlencode(params), headers={
                'User-Agent': 'HealthJobsCollector/1.0', 'Accept': 'application/json, application/xml'}), timeout=15) as response:
            raw = response.read(5_000_001)
        if len(raw) > 5_000_000:
            raise ValueError('응답 크기 한도')
        return raw
    except Exception as error:
        raise ValueError('공공 API 요청 실패 (' + type(error).__name__ + ')') from None


def iso_day(value, end=False):
    from collector import KST
    value = str(value or '')
    match = re.search(r'(20\d{2})[-/.]?(\d{2})[-/.]?(\d{2})', value)
    if not match:
        return None
    try:
        date = datetime(*map(int, match.groups()), tzinfo=KST)
        return date.replace(hour=23, minute=59, second=59).isoformat(timespec='seconds') if end else date.date().isoformat()
    except ValueError:
        return None


def api_employment(value):
    from collector import employment_type
    # 부정문이 붙은 '파견/대체 비희망'을 계약직으로 오인하지 않는다.
    text = re.sub(r'[^/\n,]*(?:비희망|희망하지 않음)', '', str(value or ''))
    if '기간의 정함이 없는' in text:
        return '확인 필요' if '시간' in text or '단시간' in text else '정규직'
    if '기간의 정함이 있는' in text:
        return '비정규직'
    return employment_type(text)


def original_url(value):
    from collector import safe_url
    url = safe_url(str(value or ''))
    p = urlsplit(url)
    if p.hostname and (p.hostname == 'work.go.kr' or p.hostname.endswith('.work.go.kr')):
        no = parse_qs(p.query).get('wantedAuthNo', [''])[0]
        if re.fullmatch(r'[A-Za-z0-9]{1,40}', no):
            return 'https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?' + urlencode({
                'wantedAuthNo': no, 'infoTypeCd': 'VALIDATION', 'infoTypeGroup': 'tb_workinfoworknet'})
    return url


def job(source, checked_at, title, company, url, location='', employment='', published=None, deadline=None, body='', identifier=None):
    from collector import clean_text, region_type
    url = original_url(url)
    if not url or not title:
        return None
    text = clean_text(str(body or ''))
    evidence = '\n'.join(line for line in text.splitlines() if re.search(r'보건\s*관리|산업\s*간호|사업장\s*간호|간호사\s*면허', line))[:800]
    value = {'id': source['id'] + '-' + (str(identifier) if identifier else hashlib.sha256(url.encode()).hexdigest()[:20]),
             'title': clean_text(str(title)), 'company': clean_text(str(company or '기관명 확인 필요')),
             'url': url, 'source_id': source['id'], 'source': source['name'], 'origin': 'api',
             'location': location or '근무지 확인 필요', 'location_detail': location or '상세 근무지 원문 확인 필요',
             'region': region_type(location), 'employment': api_employment(employment),
             'employment_evidence': employment or 'API에 고용형태 없음 · 원문 확인 필요',
             'published_at': iso_day(published), 'deadline': iso_day(deadline, True),
             'first_seen': checked_at, 'last_seen': checked_at, 'keyword_evidence': evidence,
             '_qualification_text': text}
    return qualify_job(value)


def alio_rows(value):
    code = str(value.get('resultCode', ''))
    if code not in ('0', '00', '0000', '200'):
        raise ValueError('ALIO API 응답 오류 (코드 ' + code[:10] + ')')
    result = value.get('result', [])
    if isinstance(result, dict):
        result = result.get('item', result)
    if isinstance(result, dict):
        result = [result]
    if not isinstance(result, list):
        raise ValueError('ALIO API 목록 형식 확인 필요')
    return [row.get('item', row) for row in result]


def fetch_alio_api(source):
    key = unquote(os.environ[source['required_env'][0]].strip())
    today = datetime.now().date()
    params = {'serviceKey': key, 'resultType': 'json', 'ongoingYn': 'Y', 'numOfRows': 100,
              'pbancBgngYmd': (today - timedelta(days=120)).isoformat(), 'pbancEndYmd': today.isoformat()}
    # 제목 검색만 하면 다직렬 채용의 자격요건에 있는 보건관리자를 놓치므로 전체 진행중 목록을 조회한다.
    rows, warnings = [], []
    max_pages = min(20, max(1, int(source.get('max_pages', 10))))
    started = time.monotonic()
    for page in range(1, max_pages + 1):
        value = json.loads(read_api(ENDPOINTS['alio_api'], dict(params, pageNo=page)))
        batch = alio_rows(value)
        rows.extend(batch)
        total = int(value.get('totalCount', len(rows)))
        if len(rows) >= total or not batch:
            break
        if page == max_pages or time.monotonic() - started > 110:
            warnings.append('ALIO API 조회 한도 · 전체 진행중 목록 일부만 확인')
            break
        time.sleep(0.5)
    return json.dumps({'rows': rows, 'warnings': warnings}, ensure_ascii=False).encode()


def parse_alio_api(raw, source, checked_at):
    from collector import clean_text
    rows = json.loads(raw)['rows']
    jobs = []
    for row in rows:
        sn = str(row.get('recrutPblntSn', ''))
        if not sn.isdigit():
            continue
        url = 'https://job.alio.go.kr/recruitview.do?idx=' + sn
        body = '\n'.join(clean_text(str(row.get(k) or '')) for k in ('aplyQlfcCn', 'prefCn', 'prefCondCn', 'scrnprcdrMthdExpln'))
        value = job(source, checked_at, row.get('recrutPbancTtl'), row.get('instNm'), url,
                    str(row.get('workRgnNmLst') or ''), str(row.get('hireTypeNmLst') or ''),
                    row.get('pbancBgngYmd'), row.get('pbancEndYmd'), body, sn)
        if value:
            # 기존 ALIO HTML 수집과 같은 ID/원문 URL로 중복 및 즐겨찾기 유지.
            value['id'] = 'alio-' + sn
            employer = original_url(row.get('srcUrl'))
            if employer:
                value['employer_url'] = employer
            jobs.append(value)
    return jobs, len(rows)


def fetch_kto_api(source):
    today = datetime.now().date()
    return read_api(ENDPOINTS['kto_api'], {'serviceKey': unquote(os.environ[source['required_env'][0]].strip()),
                   'startdt': (today - timedelta(days=120)).strftime('%Y%m%d'), 'enddt': today.strftime('%Y%m%d')})


def parse_kto_api(raw, source, checked_at):
    root = ET.fromstring(raw)
    def field(node, name):
        return next((''.join(e.itertext()).strip() for e in node.iter() if e.tag.rsplit('}', 1)[-1] == name), '')
    code = field(root, 'resultCode')
    if code not in ('0', '00', '0000', 'INFO-000'):
        raise ValueError('관광공사 API 응답 오류 (코드 ' + code[:10] + ')')
    rows = [e for e in root.iter() if e.tag.rsplit('}', 1)[-1] == 'resultItem']
    jobs = []
    for row in rows:
        if field(row, 'itemStatus') == 'N':
            continue
        value = job(source, checked_at, field(row, 'title'), field(row, 'orgNm'), field(row, 'itemUrl'),
                    published=field(row, 'regDate'), deadline=field(row, 'endDate'), identifier=field(row, 'itemId'))
        if value:
            jobs.append(value)
    return jobs, len(rows)


def gg_rows(value, name):
    if 'RESULT' in value:
        code = value['RESULT'].get('CODE')
        if code == 'INFO-200':
            return [], 0
        raise ValueError('경기 API 응답 오류 (코드 ' + str(code)[:15] + ')')
    blocks = value.get(name)
    if not isinstance(blocks, list):
        raise ValueError('경기 API 응답 형식 확인 필요')
    head = next((b['head'] for b in blocks if 'head' in b), [])
    meta = {key: val for part in head for key, val in part.items()}
    if meta.get('RESULT', {}).get('CODE') != 'INFO-000':
        raise ValueError('경기 API 처리 실패')
    return next((b['row'] for b in blocks if 'row' in b), []), int(meta.get('list_total_count', 0))


def fetch_gg_api(source):
    from collector import SEARCH_KEYWORDS
    name = ENDPOINTS[source['adapter']].rsplit('/', 1)[-1]
    title_field = 'PBANC_CONT' if source['adapter'] == 'gg_jobaba' else 'EMPLMNT_TITLE'
    # 키 없으면 페이지를 무시하고 고정 5건만 돌려주는 공개 샘플이므로 정식 키만 사용한다.
    key = os.environ['GG_API_KEY'].strip()
    if not key or key.lower() == 'sample':
        raise ValueError('경기 API 정식 인증키 필요 · 샘플은 수집에 사용하지 않음')
    found, warnings = {}, []
    started, requests = time.monotonic(), 0
    for keyword in SEARCH_KEYWORDS:
        last_signature = None
        for page in range(1, 6):
            if requests >= 35 or time.monotonic() - started > 110:
                warnings.append('경기 API 요청/시간 한도 · 키워드 조회 일부만 확인')
                break
            value = json.loads(read_api(ENDPOINTS[source['adapter']], {'KEY': key, 'Type': 'json',
                               'pIndex': page, 'pSize': 100, title_field: keyword}))
            requests += 1
            rows, total = gg_rows(value, name)
            signature = json.dumps(rows, ensure_ascii=False, sort_keys=True)
            if page > 1 and signature == last_signature:
                warnings.append('경기 API 페이지 응답 반복 · 전체 수집으로 처리하지 않음')
                break
            for row in rows:
                # 기업/담당자 연락처는 저장하지 않는다. URL 기반으로 키워드 간 중복 제거.
                url = row.get('URL') or row.get('EMPLMNT_INFO_URL')
                if url:
                    found[url] = row
            last_signature = signature
            if not rows or page * 100 >= total:
                break
            if page == 5:
                warnings.append('경기 API 키워드당 500건 한도')
            time.sleep(0.5)
        if requests >= 35 or time.monotonic() - started > 110:
            break
        time.sleep(0.5)
    return json.dumps({'rows': list(found.values()), 'warnings': sorted(set(warnings))}, ensure_ascii=False).encode()


def parse_gg_api(raw, source, checked_at):
    rows, jobs = json.loads(raw)['rows'], []
    for row in rows:
        if source['adapter'] == 'gg_jobaba':
            # 경기 시군 코드로 확인되는 경우에만 '경기'를 붙인다. 지역 미기재는 기타.
            loc = str(row.get('WORK_REGION_CONT') or '')
            code = str(row.get('WORK_REGION_CD_CONT') or '')
            if loc and code.startswith('41') and not re.search(r'경기|서울|인천|부산|대구|대전|전국', loc):
                loc = '경기 ' + loc
            value = job(source, checked_at, row.get('PBANC_CONT'), row.get('ENTRPRS_NM'), row.get('URL'),
                        loc, str(row.get('PBANC_FORM_DIV') or ''), None, row.get('RCPT_END_DE'),
                        str(row.get('RECRUT_FIELD_NM') or ''))
            # 접수시작일은 최초 게시일과 다르므로 published_at으로 사용하지 않는다.
        else:
            loc = ' '.join(str(row.get(k) or '') for k in ('WORKPLC_BASIS_ADDR', 'WORKPLC_DETAIL_ADDR')).strip()
            loc = loc or str(row.get('WORK_REGION_LOC') or '')
            value = job(source, checked_at, row.get('EMPLMNT_TITLE'), row.get('COMPNY_NM'), row.get('EMPLMNT_INFO_URL'),
                        loc, str(row.get('EMPLYMT_FORM') or ''), row.get('REGIST_DE'), row.get('CLOS_DE_INFO'),
                        str(row.get('JOBCLASS_DIV_NM') or ''), row.get('JOBOFFR_CERTFIY_NO'))
        if value:
            jobs.append(value)
    return jobs, len(rows)
