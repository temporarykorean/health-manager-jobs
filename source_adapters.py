"""검토된 기관 페이지 및 공식 검색 API. 검색 결과 원문은 자동 방문하지 않습니다."""
from job_target import qualify_job
import hashlib
import json
import os
import re
import time
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener, urlopen
from urllib.robotparser import RobotFileParser
from source_policy import direct_url_allowed, domain_matches, public_url, PORTAL_DOMAINS, SEARCH_DOMAINS

USER_AGENT = 'HealthJobsCollector/1.0'
MAX_BYTES = 3_000_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 다른 경로의 robots/조건 확인 없이 리디렉션을 따라가지 않습니다.
        return None


def read_direct(url):
    with build_opener(NoRedirect()).open(Request(url, headers={'User-Agent': USER_AGENT}), timeout=20) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('응답 크기 초과')
    return raw


def fetch_pages(source):
    documents = []
    robots_by_host = {}
    last_request = {}
    for url in source['page_urls']:
        if not direct_url_allowed(url, source):
            raise ValueError('페이지 호스트 정책 위반')
        parts = urlsplit(url)
        host = parts.netloc
        if host not in robots_by_host:
            robots_url = 'https://' + host + '/robots.txt'
            # 404/403/접속 실패도 허용으로 추정하지 않습니다.
            text = read_direct(robots_url).decode('utf-8', errors='strict')
            if '<html' in text.lower() or not re.search(r'^\s*User-agent\s*:', text, re.I | re.M):
                raise ValueError('robots.txt 정책 확인 실패')
            policy = RobotFileParser(robots_url)
            policy.parse(text.splitlines())
            robots_by_host[host] = policy
            last_request[host] = time.monotonic()
        policy = robots_by_host[host]
        if not policy.can_fetch(USER_AGENT, url):
            raise ValueError('robots.txt에서 페이지 접근 비허용')
        delay = max(2.0, float(source.get('min_interval_seconds', 2)), float(policy.crawl_delay(USER_AGENT) or 0))
        rate = policy.request_rate(USER_AGENT)
        if rate:
            delay = max(delay, rate.seconds / rate.requests)
        if delay > 60:
            raise ValueError('출처 요청 간격이 실행 한도를 초과함')
        time.sleep(max(0, delay - (time.monotonic() - last_request[host])))
        documents.append({'url': url, 'html': read_direct(url).decode('utf-8')})
        last_request[host] = time.monotonic()
    return json.dumps(documents, ensure_ascii=False).encode()


class StructuredData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []
        self.documents = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('type', '').lower() == 'application/ld+json':
            self.active = True
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.active:
            self.active = False
            self.documents.append(json.loads(''.join(self.parts)))


def posting_nodes(value):
    if isinstance(value, list):
        for child in value:
            yield from posting_nodes(child)
    elif isinstance(value, dict):
        types = value.get('@type', [])
        if 'JobPosting' in (types if isinstance(types, list) else [types]):
            yield value
        if '@graph' in value:
            yield from posting_nodes(value['@graph'])


def parse_pages(raw, source, checked_at):
    from collector import clean_text, employment_type, region_type, canonical_url, published_date, KST, RELATED_PATTERN
    jobs, count = [], 0
    for doc in json.loads(raw):
        parser = StructuredData()
        parser.feed(doc['html'])
        postings = list(posting_nodes(parser.documents))
        if not postings:
            raise ValueError('JobPosting 구조화 데이터 없음 · 전용 파서 검토 필요')
        for posting in postings:
            count += 1
            title = clean_text(posting.get('title', ''))
            description = clean_text(posting.get('description', ''))
            if not re.search(RELATED_PATTERN, title + '\n' + description):
                continue
            url = posting.get('url') or doc['url']
            if not direct_url_allowed(url, source):
                continue
            locations = posting.get('jobLocation', [])
            if isinstance(locations, dict):
                locations = [locations]
            location = ' / '.join(' '.join(str(place.get('address', {}).get(key, '')) for key in ('addressRegion', 'addressLocality', 'streetAddress')) for place in locations)
            evidence = posting.get('employmentType', '')
            evidence = ', '.join(evidence) if isinstance(evidence, list) else evidence
            # FULL_TIME만으로 국내 정규직이라고 단정하지 않습니다.
            evidence = re.sub(r'CONTRACTOR|TEMPORARY|INTERN|PART_TIME', lambda m: {'CONTRACTOR':'계약직','TEMPORARY':'임시직','INTERN':'인턴','PART_TIME':'시간제'}[m[0]], evidence)
            deadline = None
            value = posting.get('validThrough')
            if value:
                try:
                    end = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    if end.tzinfo is None:
                        end = end.replace(tzinfo=KST)
                    if len(value) == 10:
                        end = end.replace(hour=23, minute=59, second=59)
                    deadline = end.isoformat(timespec='seconds')
                except ValueError:
                    pass
            jobs.append({'id': hashlib.sha256(canonical_url(url).encode()).hexdigest()[:20], 'title': title,
                         'company': clean_text(posting.get('hiringOrganization', {}).get('name', '')) or source['company'],
                         'url': url, 'source_id': source['id'], 'source': source['name'],
                         'employment': employment_type(evidence), 'employment_evidence': evidence or '명시 정보 없음',
                         'region': region_type(location), 'location': location.strip() or '근무지 확인 필요',
                         'deadline': deadline, 'published_at': published_date(posting.get('datePosted', '')),
                         'first_seen': checked_at, 'last_seen': checked_at, 'origin': 'page', '_qualification_text':description})
    return [qualified for job in jobs if (qualified := qualify_job(job))], count


def fetch_search(source):
    from collector import SEARCH_KEYWORDS
    items = []
    # 하루 최대 27회, 최대 2700개 검색 결과. 원문 사이트 요청은 0회입니다.
    for keyword in SEARCH_KEYWORDS:
        for start in (1, 101, 201):
            query = urlencode({'query': keyword + ' 채용 모집', 'display': 100, 'start': start})
            request = Request(source['url'] + '?' + query, headers={
                'X-Naver-Client-Id': os.environ['NAVER_SEARCH_CLIENT_ID'],
                'X-Naver-Client-Secret': os.environ['NAVER_SEARCH_CLIENT_SECRET'],
                'Accept': 'application/json', 'User-Agent': USER_AGENT})
            try:
                with urlopen(request, timeout=20) as response:
                    raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError('응답 크기 초과')
                result = json.loads(raw)
                if not isinstance(result.get('items'), list):
                    raise ValueError('검색 응답 형식 오류')
                items.extend(result['items'])
                if start + 99 >= int(result['total']):
                    break
            except Exception:
                raise ValueError('네이버 검색 API 요청 실패 · 인증/권한/한도 확인') from None
    return json.dumps({'items': items}, ensure_ascii=False).encode()


def parse_search(raw, source, checked_at):
    from collector import clean_text, canonical_url, RELATED_PATTERN
    payload = json.loads(raw)
    if not isinstance(payload.get('items'), list):
        raise ValueError('검색 결과 형식 오류')
    candidates = []
    for item in payload['items']:
        url = item.get('link', '')
        if not public_url(url):
            continue
        host = urlsplit(url).hostname
        # 검색엔진 추적 링크 및 취업포털을 원문 링크로 오인하지 않습니다.
        if domain_matches(host, PORTAL_DOMAINS + SEARCH_DOMAINS):
            continue
        if not domain_matches(host, source.get('discovery_domains', [])):
            continue
        title = clean_text(item.get('title', ''))
        if not re.search(RELATED_PATTERN, title):
            continue
        if re.search(r'합격자|합격발표|결과발표|연간.*계획', title):
            continue
        if not re.search(r'채용|모집|구인', title):
            continue
        candidates.append({'id': hashlib.sha256(canonical_url(url).encode()).hexdigest()[:20],
                           'title': title, 'url': url, 'source_id': source['id'], 'source': source['name'],
                           'first_seen': checked_at, 'last_seen': checked_at, 'origin': 'search',
                           'verification': '원문 미검증 · 접수 여부 확인 필요'})
    return [qualified for item in candidates if (qualified := qualify_job(item))], len(payload['items'])
