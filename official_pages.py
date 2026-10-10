"""공개 표 기반 공식 채용페이지. 목록에서 직무 후보를 찾고 상세를 확인합니다."""
import hashlib
import html
import json
import re
from urllib.parse import urljoin, urlsplit, parse_qsl, urlencode
from public_careers import PublicSession, iso_date
from job_target import qualify_job, HEALTH_ROLE


def dl_rows(text, base):
    from collector import clean_text
    rows=[]
    for row in re.findall(r'<tr\b[^>]*>([\s\S]*?)</tr>',text,re.I):
        link=re.search(r'href=["\']([^"\']*FieldEmpView(?:PJ)?\.do[^"\']*)["\'][^>]*>([\s\S]*?)</a>',row,re.I)
        if not link: continue
        url=urljoin(base,html.unescape(link[1])); parts=urlsplit(url)
        values=dict(parse_qsl(parts.query)); job_id=values.get('no_empt_anct','')
        if not re.fullmatch(r'\d{12}',job_id): continue
        # 페이지番号等の一覧パラメータを取り除き原文URLを安定化します。
        url=parts._replace(query=urlencode({'no_empt_anct':job_id}),fragment='').geturl()
        dates=re.findall(r'\d{4}\.\d{2}\.\d{2}',clean_text(row))
        rows.append({'id':job_id,'url':url,'title':clean_text(link[2]),
                     'published_at':iso_date(dates[0]) if dates else None,
                     'deadline':None if not dates or dates[-1].startswith('9999') else iso_date(dates[-1],True)})
    return rows


def fetch_dlenc(source):
    from collector import RELATED_PATTERN
    session=PublicSession(source); rows={}; warnings=[]; scanned=0
    for url in source['page_urls']:
        for page in range(1,3):
            try:
                text=session.get(url+'?'+urlencode({'currentPage':page}))
                if '채용공고' not in text: raise ValueError('공식 목록 형식 변경')
                found=dl_rows(text,url); scanned+=len(found)
                rows.update((r['id'],r) for r in found)
                if len(found)<10: break
                if page==2: warnings.append('목록 페이지 조회 한도')
            except Exception as error:
                warnings.append(f'목록: {type(error).__name__}'); break
    documents=[]
    candidates=[r for r in rows.values() if re.search(RELATED_PATTERN+r'|전체\s*직무',r['title'],re.I)]
    for row in candidates[:20]:
        try: documents.append({'row':row,'html':session.get(row['url'])})
        except Exception as error: warnings.append(f"{row['id']}: {type(error).__name__}")
    if not rows and warnings: raise ValueError('공식 채용 목록 조회 실패')
    if candidates and not documents: raise ValueError('공식 채용 상세 조회 실패')
    return json.dumps({'documents':documents,'scanned':scanned,'warnings':warnings},ensure_ascii=False).encode()


def parse_dlenc(raw,source,checked_at):
    from collector import clean_text, employment_type, region_type
    payload=json.loads(raw); jobs=[]
    for doc in payload['documents']:
        tables=re.findall(r'<table\b[^>]*>([\s\S]*?)</table>',doc['html'],re.I)
        fields={}; health=[]
        for table in tables:
            rows=re.findall(r'<tr\b[^>]*>([\s\S]*?)</tr>',table,re.I)
            cells=[[clean_text(c) for c in re.findall(r'<t[hd]\b[^>]*>([\s\S]*?)</t[hd]>',r,re.I)] for r in rows]
            for index, header_row in enumerate(cells):
                headers=[re.sub(r'\s+','',c) for c in header_row]
                if '채용대상' in headers:
                    value=next((v for v in cells[index+1:] if len(v)==len(headers)),[])
                    fields.update(zip(headers,value))
                if '모집분야' in headers:
                    for values_row in cells[index+1:]:
                        active_headers=headers
                        if len(values_row)!=len(headers):
                            # 구형 템플릿은 숨김 직군/직렬/직무 헤더만 있고 대응 셀은 생략합니다.
                            active_headers=[h for h in headers if h not in {'직군','직렬','직무'}]
                        if len(values_row)!=len(active_headers): continue
                        mapping=dict(zip(active_headers,values_row))
                        if re.search(HEALTH_ROLE,mapping.get('모집분야','')):
                            health.append(mapping)
        # 다른 직렬, 메뉴, 이전/다음 공고에서 키워드를 가져오지 않습니다.
        if not health: continue
        row=doc['row']; location=' / '.join(dict.fromkeys(h.get('근무지','') for h in health))
        employment=fields.get('채용대상','')
        if 'PJT' in employment: employment='프로젝트계약직 (PJT직)'
        elif '현채' in employment: employment='계약직 (현채직)'
        deadline=fields.get('마감일','')
        # 9999.12.31은 상시채용 표시이며 실제 마감일로 저장하지 않습니다.
        deadline=None if deadline.startswith('9999') else iso_date(deadline,True) or row['deadline']
        evidence='\n'.join(' · '.join(h.values()) for h in health)
        job={'id':'dlenc-'+row['id'],'title':row['title'],'company':source['company'],'url':row['url'],
             'source_id':source['id'],'source':source['name'],'employment':employment_type(employment),
             'employment_evidence':employment or '명시 정보 없음','region':region_type(location),
             'location':location or '근무지 확인 필요','location_detail':location or '상세 근무지 원문 확인 필요',
             'published_at':iso_date(fields.get('공고일','')) or row['published_at'],'deadline':deadline,
             'first_seen':checked_at,'last_seen':checked_at,'collected_at':checked_at,'origin':'page',
             'keyword_evidence':evidence[:160],'_qualification_text':evidence}
        qualified=qualify_job(job)
        if qualified: jobs.append(qualified)
    return jobs,payload['scanned']
