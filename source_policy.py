"""출처 종류, 우선순위와 자동 접근 정책. 검토되지 않은 페이지는 요청하지 않습니다."""
import os
from datetime import datetime, timedelta
from urllib.parse import urlsplit

PRIORITIES = {'api': 1, 'rss': 2, 'atom': 2, 'page': 3, 'search': 4}
PORTAL_DOMAINS = ('linkedin.com', 'jobkorea.co.kr', 'saramin.co.kr', 'catch.co.kr')
SEARCH_DOMAINS = ('naver.com', 'google.com', 'bing.com', 'daum.net')


def kind(source):
    return 'api' if source.get('type') == 'saramin' else source.get('type', 'rss')


def adapter(source):
    return source.get('adapter', source.get('type', 'rss'))


def domain_matches(host, domains):
    return any(host == domain or host.endswith('.' + domain) for domain in domains)


def public_url(url):
    try:
        parts = urlsplit(url)
        return parts.scheme == 'https' and bool(parts.hostname) and not parts.username and not parts.password and parts.port in (None, 443)
    except (ValueError, TypeError):
        return False


def direct_url_allowed(url, source):
    if not public_url(url):
        return False
    host = urlsplit(url).hostname
    return not domain_matches(host, PORTAL_DOMAINS) and host in source.get('allowed_hosts', [])


def pending_reason(source, checked_at, available_adapters):
    source_kind = kind(source)
    if source_kind not in PRIORITIES:
        return '지원하지 않는 출처 종류'
    host = urlsplit(source.get('url', '')).hostname or ''
    if domain_matches(host, ('linkedin.com',)):
        return 'LinkedIn은 자동 수집 대상에서 제외'
    if source.get('enabled', True) is not True:
        return source.get('pending_message', '출처 활성화 대기')
    if source_kind in ('page', 'rss', 'atom') and domain_matches(host, PORTAL_DOMAINS):
        return '취업포털 직접 수집 제외 · 승인된 공식 API만 연결'
    if adapter(source) not in available_adapters:
        return '공식 API 승인·명세에 맞는 어댑터 연결 대기'
    if source_kind == 'page':
        review = source.get('access_review', {})
        try:
            reviewed = datetime.fromisoformat(review['reviewed_at'])
            now = datetime.fromisoformat(checked_at)
            fresh = reviewed <= now and now - reviewed <= timedelta(days=90)
        except (KeyError, ValueError, TypeError):
            fresh = False
        if not (review.get('decision') == 'allowed' and review.get('terms_url') and review.get('notes') and fresh):
            return '기관·기업 페이지 이용조건 검토 필요 (90일 이내 기록)'
        urls = source.get('page_urls', [])
        if not urls or len(urls) > 10 or not all(direct_url_allowed(url, source) for url in urls):
            return '승인된 HTTPS 호스트·페이지 목록 필요 (최대 10개)'
    from public_apis import ENDPOINTS
    approved_endpoints = {**ENDPOINTS, 'saramin': 'https://oapi.saramin.co.kr/job-search', 'naver_search': 'https://openapi.naver.com/v1/search/webkr.json'}
    if adapter(source) in approved_endpoints and source.get('url') != approved_endpoints[adapter(source)]:
        return '공식 API 승인된 주소만 요청 가능'
    if adapter(source) == 'greenhouse':
        token = source.get('board_token', '')
        import re
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', token) or source.get('url') != f'https://boards-api.greenhouse.io/v1/boards/{token}/jobs':
            return 'Greenhouse 공식 공개 GET 주소만 요청 가능'
    required = source.get('required_env', [])
    if adapter(source) == 'saramin':
        required = ['SARAMIN_ACCESS_KEY']
    if any(not os.environ.get(name, '').strip() for name in required):
        return source.get('pending_message', 'API 인증 정보 연결 대기')
    return None
