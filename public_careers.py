"""키 없이 읽는 ALIO 및 공통 채용 플랫폼. 승인된 경로에만 낮은 빈도로 접근."""
import hashlib
import html
import json
import re
import time
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urljoin, urlencode
from urllib.robotparser import RobotFileParser
from urllib.request import Request, build_opener
from source_adapters import NoRedirect, USER_AGENT, MAX_BYTES
from source_policy import direct_url_allowed


class PublicSession:
    def __init__(self, source):
        self.source = source
        self.policy = None
        self.last = 0
        self.count = 0
        self.started = time.monotonic()
        self.base = 'https://' + urlsplit(source['url']).netloc
        try:
            try:
                raw = self._read(self.base + '/robots.txt')
            except (URLError, TimeoutError) as error:
                if isinstance(error, HTTPError):
                    raise
                # 일시적인 기관 서버 지연만 한 차례 재시도. 차단 응답은 재시도하지 않음.
                time.sleep(1)
                raw = self._read(self.base + '/robots.txt')
            text = raw.decode('utf-8')
            if '<html' in text.lower() or not re.search(r'^\s*User-agent\s*:', text, re.I | re.M):
                raise ValueError('robots.txt 대신 오류 응답 · 접근 정책 미확인')
            self.policy = RobotFileParser()
            self.policy.parse(text.splitlines())
        except HTTPError as error:
            if error.code != 404 or source.get('robots_missing') != 'allow_with_review':
                raise ValueError(f'robots.txt 확인 실패 (HTTP {error.code})') from None
            # ALIO 공개데이터 이용정책을 검토한 경우에만 404(규칙 없음)를 허용합니다.

    def _read(self, url):
        with build_opener(NoRedirect()).open(Request(url, headers={'User-Agent': USER_AGENT}), timeout=self.source.get('request_timeout_seconds', 15)) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('응답 크기 초과')
        self.last = time.monotonic()
        return raw

    def get(self, url):
        if time.monotonic() - self.started > self.source.get('max_seconds', 180):
            raise TimeoutError('출처별 실행 시간 한도')
        if not direct_url_allowed(url, self.source):
            raise ValueError('승인된 호스트 외 접근 차단')
        if urlsplit(url).path not in self.source.get('allowed_paths', []):
            # Greeting 공고 상세 경로만 허용하고 지원/계정 페이지는 요청하지 않습니다.
            if self.source.get('adapter') != 'greeting' or not re.fullmatch(r'/ko/o/\d+', urlsplit(url).path):
                raise ValueError('승인된 채용 경로 외 접근 차단')
        if self.policy and not self.policy.can_fetch(USER_AGENT, url):
            raise ValueError('robots.txt 접근 비허용')
        interval = max(1.0, float(self.source.get('min_interval_seconds', 1)))
        if self.policy:
            interval = max(interval, self.policy.crawl_delay(USER_AGENT) or 0)
            rate = self.policy.request_rate(USER_AGENT)
            if rate:
                interval = max(interval, rate.seconds / rate.requests)
        if interval > 60:
            raise ValueError('요청 간격 한도 초과')
        self.count += 1
        if self.count > self.source.get('max_requests', 65):
            raise ValueError('출처별 요청 한도 초과')
        time.sleep(max(0, interval - (time.monotonic() - self.last)))
        return self._read(url).decode('utf-8')


def iso_date(value, end=False):
    from collector import KST
    match = re.search(r'(?<!\d)(\d{4}|\d{2})[./-](\d{1,2})[./-](\d{1,2})(?!\d)', value)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    year = year + 2000 if year < 100 else year
    try:
        date = datetime(year, month, day, tzinfo=KST)
        if end:
            date = date.replace(hour=23, minute=59, second=59)
            return date.isoformat(timespec='seconds')
        return date.date().isoformat()
    except ValueError:
        return None


def alio_rows(text):
    from collector import clean_text
    rows = []
    for row in re.findall(r'<tr\b[^>]*>([\s\S]*?)</tr>', text, re.I):
        match = re.search(r'/recruitview\.do\?idx=(\d+)', row)
        if not match:
            continue
        cells = re.findall(r'<td\b[^>]*>([\s\S]*?)</td>', row, re.I)
        if len(cells) < 9:
            continue
        values = [clean_text(cell) for cell in cells]
        rows.append({'idx': match[1], 'title': values[2], 'company': values[3],
                     'location': values[4], 'employment': values[5],
                     'published_at': iso_date(values[6]), 'deadline': iso_date(values[7], True)})
    return rows


def fetch_alio(source):
    from collector import KST
    session = PublicSession(source)
    now = datetime.now(KST)
    documents = {}
    rows = {}
    scanned = 0
    partial = []
    # 전체 검색은 제목뿐 아니라 응시자격/우대조건/우대내용을 검색합니다.
    for keyword in ('보건관리자', '보건 관리자', '산업간호사', '산업 간호사', '보건관리원', '사업장 간호사', '산업보건', 'EHS 보건', '안전보건'):
        for page in range(1, 3):
            query = urlencode({'keyword': keyword, 'search_type': '', 'pageSet': 50, 'pageNo': page,
                               's_date': (now-timedelta(days=120)).strftime('%Y.%m.%d'),
                               'e_date': now.strftime('%Y.%m.%d'), 'ing': '2', 'order': 'REG_DATE', 'sort': 'DESC'})
            try:
                text = session.get(session.base + '/recruit.do?' + query)
                if '채용정보' not in text or 'pageNo' not in text:
                    raise ValueError('ALIO 검색 응답 형식 변경')
                found = alio_rows(text)
                scanned += len(found)
                for row in found:
                    rows[row['idx']] = row
                if len(found) < 50:
                    break
                if page == 2:
                    partial.append(f'{keyword}: 100건 조회 한도')
            except Exception as error:
                partial.append(f'{keyword}: {type(error).__name__} {error}')
                break
    if not rows and partial:
        raise ValueError('ALIO 검색 실패: ' + '; '.join(partial)[:200])
    consecutive_failures = 0
    for idx, row in sorted(rows.items(), key=lambda item: item[1].get("published_at") or "", reverse=True)[:100]:
        url = session.base + '/recruitview.do?' + urlencode({'idx': idx})
        try:
            documents[idx] = {'url': url, 'row': row, 'html': session.get(url)}
            consecutive_failures = 0
        except Exception as error:
            partial.append(f'{idx}: {type(error).__name__}')
            consecutive_failures += 1
            if consecutive_failures >= 3 or isinstance(error, TimeoutError):
                partial.append('연속 실패 또는 실행 시간 한도 · 다른 출처로 진행')
                break
    if len(rows) > 100:
        partial.append('상세 조회 100건 한도 · 최신 100건 우선')
    if rows and not documents:
        raise ValueError('ALIO 상세 공고 조회 전체 실패')
    return json.dumps({'documents': list(documents.values()), 'scanned': scanned, 'warnings': partial}, ensure_ascii=False).encode()


def parse_alio(raw, source, checked_at):
    from collector import clean_text, employment_type, region_type, safe_url, RELATED_PATTERN
    payload = json.loads(raw)
    jobs = []
    for doc in payload['documents']:
        text = doc['html']
        # 진행중인 다른 공고 배너나 공통 메뉴로부터 키워드를 가져오지 않습니다.
        content = re.search(r'<div id="tab-1"[^>]*>([\s\S]*?)<div id="tab-2"', text)
        body = clean_text(content[1] if content else '')
        row = doc['row']
        title_match = re.search(r'<p[^>]*class="titleH2"[^>]*>([\s\S]*?)</p>', text)
        title = clean_text(title_match[1]) if title_match else row['title']
        fields = {clean_text(key): clean_text(value) for key, value in re.findall(r'<th[^>]*>([\s\S]*?)</th>\s*<td[^>]*>([\s\S]*?)</td>', text)}
        evidence = title + '\n' + body + '\n' + fields.get('우대조건','') + '\n' + fields.get('근무분야','')
        match = re.search(RELATED_PATTERN, evidence)
        if not match:
            continue
        location = fields.get('근무지', row['location'])
        employment = fields.get('고용형태', row['employment'])
        # 다직렬 공고의 구조화된 고용형태는 직무별 형태를 보장하지 않습니다.
        if '외 ' in employment:
            classification = '확인 필요'
        else:
            classification = employment_type(employment)
        external = re.search(r'<p class="infoLink">[\s\S]*?<a[^>]*href="([^"]+)"', text)
        original = safe_url(html.unescape(external[1])) if external else ''
        period = fields.get('채용기간', '')
        dates = re.findall(r'(?<!\d)(?:\d{4}|\d{2})[./-]\d{1,2}[./-]\d{1,2}(?!\d)', period)
        deadline = iso_date(dates[-1], True) if dates else row['deadline']
        published = iso_date(fields.get('등록일','')) or row['published_at']
        # 상세 근무지 미기재 시 기관 주소를 근무지로 추정하지 않습니다.
        detail_location = re.search(r'(?:근무장소|근무지역|근무지)\s*[:：]\s*([^\n]+)', body)
        jobs.append({'id': 'alio-' + row['idx'], 'title': title, 'company': row['company'],
                     'url': doc['url'], 'employer_url': original, 'source_id': source['id'], 'source': source['name'],
                     'employment': classification, 'employment_evidence': employment,
                     'employment_confidence': 'structured' if classification!='확인 필요' else 'uncertain',
                     'region': region_type(location), 'location': location,
                     'location_detail': detail_location[1][:160] if detail_location else '상세 근무지 원문 확인 필요',
                     'deadline': deadline, 'published_at': published,
                     'first_seen': checked_at, 'last_seen': checked_at, 'collected_at': checked_at,
                     'origin': 'page', 'keyword_evidence': clean_text(evidence[max(0,match.start()-30):match.end()+100])[:160]})
    # 메타는 fetcher가 전달한 경고를 collect에서 별도로 읽습니다.
    return jobs, payload['scanned']


def greeting_rows(text, base):
    from collector import clean_text
    rows = []
    for block in re.findall(r'<a\b[^>]*data-testid="공고_아이템"[\s\S]*?</a>',text):
        link = re.search(r'href="([^"]+)"',block)
        title = re.search(r'<span[^>]*OpeningListItemTitle[^>]*>([\s\S]*?)</span>',block)
        if not link or not title:
            continue
        fields = {key: clean_text(value) for key,value in re.findall(r'data-testid="공고리스트_subtext_([^"]+)"[^>]*>([\s\S]*?)</span>',block)}
        rows.append({'url': urljoin(base,html.unescape(link[1])), 'title': clean_text(title[1]), 'fields': fields})
    return rows


def fetch_greeting(source):
    from collector import RELATED_PATTERN
    session = PublicSession(source)
    text = session.get(source['url'])
    rows = greeting_rows(text, session.base)
    if not rows:
        raise ValueError('Greeting 공개 목록 형식 변경 또는 빈 응답')
    documents, warnings = [], []
    # 관련 제목 + EHS 직무명 후보의 상세만 방문합니다. 모든 직무 상세 대량 요청은 하지 않습니다.
    candidates = [row for row in rows if re.search(RELATED_PATTERN+'|EHS|환경안전', row['title']+' '+row['fields'].get('직군',''),re.I)]
    for row in candidates[:20]:
        try:
            documents.append(dict(row,html=session.get(row['url'])))
        except Exception as error:
            warnings.append(f"공고 조회 실패: {type(error).__name__}")
    if candidates and not documents:
        raise ValueError('Greeting 관련 공고 상세 조회 전체 실패')
    return json.dumps({'documents':documents,'scanned':len(rows),'warnings':warnings},ensure_ascii=False).encode()


def parse_greeting(raw,source,checked_at):
    from collector import clean_text, employment_type, region_type, RELATED_PATTERN
    from source_adapters import StructuredData, posting_nodes, parse_pages
    payload=json.loads(raw)
    jobs=[]
    for doc in payload['documents']:
        parser=StructuredData()
        parser.feed(doc['html'])
        postings=list(posting_nodes(parser.documents))
        # NEXT_DATA is the same public server-rendered page data; no private API calls.
        state_match=re.search(r'<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>',doc['html'])
        opening=None
        if state_match:
            state=json.loads(state_match[1])
            queries=state.get('props',{}).get('pageProps',{}).get('dehydratedState',{}).get('queries',[])
            opening=next((q['state']['data'].get('data') for q in queries if len(q.get('queryKey',[]))>1 and q['queryKey'][1]=='getOpeningById'),None)
        if opening:
            info=opening.get('openingsInfo',{})
            body=clean_text(info.get('detail',''))
            match=re.search(RELATED_PATTERN,doc['title']+' '+body,re.I)
            if not match:
                continue
            positions=opening.get('jobPositionSetting',{}).get('jobPositions',[])
            places=[p.get('workspacePlace') or {} for p in positions]
            addresses=list(dict.fromkeys((p.get('place','')+' '+p.get('detailPlace','')).strip() for p in places))
            location=' / '.join(a for a in addresses if a) or doc['fields'].get('근무지','')
            evidence=doc['fields'].get('고용형태','')
            employment=employment_type(evidence)
            date=info.get('dueDate')
            jobs.append({'id':hashlib.sha256(doc['url'].encode()).hexdigest()[:20],
                'title':doc['title'],'company':doc['fields'].get('구분') or source['company'],'url':doc['url'],
                'source_id':source['id'],'source':source['name'],'employment':employment,
                'employment_evidence':evidence or '명시 정보 없음','employment_confidence':'explicit' if employment!='확인 필요' else 'uncertain',
                'region':region_type(location),'location':location or '근무지 확인 필요','location_detail':location or '상세 근무지 원문 확인 필요',
                'deadline':date,'published_at':info.get('openDate'),'first_seen':checked_at,'last_seen':checked_at,
                'collected_at':checked_at,'origin':'page','keyword_evidence':body[:160]})
        elif postings:
            parsed,_=parse_pages(json.dumps([{'url':doc['url'],'html':doc['html']}]).encode(),source,checked_at)
            for job in parsed:
                job['location_detail']=job['location']
                job['collected_at']=checked_at
                job['employment_confidence']='explicit' if job['employment']!='확인 필요' else 'uncertain'
            jobs.extend(parsed)
        else:
            # 동적 상세에서 조건을 읽지 못하면 목록 명시값만 보존하고 날짜는 추정하지 않습니다.
            fields=doc['fields']
            if not re.search(RELATED_PATTERN,doc['title']):
                continue
            location=fields.get('근무지','')
            evidence=fields.get('고용형태','')
            jobs.append({'id':hashlib.sha256(doc['url'].encode()).hexdigest()[:20],'title':doc['title'],
                         'company':fields.get('구분') or source['company'],'url':doc['url'],
                         'source_id':source['id'],'source':source['name'],'employment':employment_type(evidence),
                         'employment_evidence':evidence,'employment_confidence':'explicit' if evidence else 'uncertain',
                         'region':region_type(location),'location':location or '근무지 확인 필요',
                         'location_detail':'상세 근무지 원문 확인 필요','deadline':None,'published_at':None,
                         'first_seen':checked_at,'last_seen':checked_at,'collected_at':checked_at,'origin':'page'})
    return jobs,payload['scanned']
