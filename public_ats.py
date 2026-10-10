"""인증 없이 GET 조회를 공식 지원하는 ATS의 공개 채용 API."""
import html
import json
import re
import time
from urllib.parse import urlsplit
from source_adapters import read_direct
from source_policy import public_url, domain_matches, PORTAL_DOMAINS
from job_target import qualify_job


def greenhouse_endpoint(source):
    token = source.get('board_token', '')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', token):
        raise ValueError('Greenhouse 공개 보드 토큰 형식 오류')
    endpoint = f'https://boards-api.greenhouse.io/v1/boards/{token}/jobs'
    if source.get('url') != endpoint:
        raise ValueError('Greenhouse 공식 공개 GET 주소만 허용')
    return endpoint


def fetch_greenhouse(source):
    from collector import RELATED_PATTERN
    endpoint = greenhouse_endpoint(source)
    result = json.loads(read_direct(endpoint))
    rows = result.get('jobs')
    if not isinstance(rows, list):
        raise ValueError('Greenhouse 공개 목록 형식 변경')
    candidates = [r for r in rows if r.get('internal_job_id') is not None
                  and re.search(RELATED_PATTERN + r'|간호사|\bEHS\b|occupational.*health|health.*safety', r.get('title', ''), re.I)]
    documents, warnings = [], []
    started = time.monotonic()
    limit = min(60, int(source.get('max_details', 40)))
    failures = 0
    for row in candidates[:limit]:
        if time.monotonic() - started > source.get('max_seconds', 150):
            warnings.append('출처별 실행 시간 한도'); break
        job_id = str(row.get('id', ''))
        if not re.fullmatch(r'\d+', job_id):
            warnings.append('공고 ID 형식 변경'); continue
        time.sleep(max(1, source.get('min_interval_seconds', 1)))
        try:
            job = json.loads(read_direct(endpoint + '/' + job_id))
            if str(job.get('id')) != job_id or not isinstance(job.get('content'), str):
                raise ValueError('공개 상세 형식 변경')
            documents.append(job); failures = 0
        except Exception as error:
            warnings.append(f'{job_id}: {type(error).__name__}')
            failures += 1
            if failures >= 3:
                warnings.append('연속 3회 실패 · 다른 출처로 진행'); break
    if len(candidates) > limit:
        warnings.append(f'상세 {limit}건 한도')
    if candidates and not documents:
        raise ValueError('Greenhouse 관련 상세 조회 전체 실패')
    return json.dumps({'documents':documents, 'scanned':len(rows), 'warnings':warnings,
                       'listed_ids':[str(r['id']) for r in rows if r.get('id') is not None],
                       'complete_listing':True}, ensure_ascii=False).encode()


def metadata_value(job, labels):
    values = []
    for item in job.get('metadata') or []:
        name = str(item.get('name', ''))
        if any(re.search(label, name, re.I) for label in labels):
            value = item.get('value')
            if isinstance(value, list): value = ', '.join(map(str,value))
            if value is not None: values.append(str(value))
    return ' / '.join(values)


def parse_greenhouse(raw, source, checked_at):
    from collector import clean_text, employment_type, region_type
    payload = json.loads(raw); jobs = []
    for item in payload['documents']:
        body = clean_text(html.unescape(html.unescape(item['content'])))
        title = clean_text(item.get('title', ''))
        url = source.get('original_url_overrides', {}).get(str(item['id'])) or item.get('absolute_url', '')
        if not public_url(url) or domain_matches(urlsplit(url).hostname,PORTAL_DOMAINS) or urlsplit(url).hostname not in source.get('allowed_hosts', []):
            continue
        # 공개 API는 updated_at을 제공하지만 최초 게시일과 같다고 단정하지 않습니다.
        location = str((item.get('location') or {}).get('name') or '')
        address = re.search(r'(?:근무지(?:\s*주소)?|근무\s*장소)\s*[:：]\s*([^\n]+)', body)
        if not address:
            address = re.search(r'근무지[ \t]*\n+[ \t]*([^\n]+)',body)
        detail = address[1].strip(' -•')[:180] if address else location
        translated = location
        for en, ko in [('Seoul','서울'), ('Gyeonggi','경기'), ('Incheon','인천')]:
            translated = re.sub(r'\b'+en+r'\b', ko, translated, flags=re.I)
        region = region_type(detail)
        if region == '기타' and not address: region = region_type(translated)
        evidence = metadata_value(item, [r'employment',r'고용형태',r'contract type'])
        if not evidence:
            match = re.search(r'(?:고용\s*형태|채용\s*형태|계약\s*형태)\s*[:：]?\s*\n?\s*([^\n]+)',body)
            evidence = match[1][:120] if match else ''
        if not evidence:
            evidence = ' / '.join(dict.fromkeys(re.findall(r'비정규직|정규직(?:\s*전환[^\n]*)?|계약직|기간제|파견직|휴직\s*대체', title+'\n'+body)))
        company_match = re.match(r'\[([^\]]+)\]',title)
        job = {'id':f"greenhouse-{source['board_token']}-{item['id']}",
               'title':title, 'company':company_match[1] if company_match else source['company'],
               'url':url, 'source_id':source['id'], 'source':source['name'],
               'employment':employment_type(evidence), 'employment_evidence':evidence or '명시 정보 없음',
               'region':region, 'location':(detail if address else translated) or '근무지 확인 필요',
               'location_detail':detail or '상세 근무지 원문 확인 필요',
               'published_at':None, 'deadline':None, 'first_seen':checked_at,
               'last_seen':checked_at, 'collected_at':checked_at, 'origin':'api',
               '_qualification_text':body}
        qualified = qualify_job(job)
        if qualified: jobs.append(qualified)
    return jobs, payload['scanned']
