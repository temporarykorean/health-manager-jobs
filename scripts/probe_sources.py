"""일회성 후보 조사. robots 허용 페이지만 읽고 원문 HTML은 저장하지 않습니다."""
import concurrent.futures
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from robots_policy import RobotsPolicy
from source_adapters import read_direct, USER_AGENT
from collector import clean_text, RELATED_PATTERN
from public_careers import greeting_rows

CANDIDATES = [
 ('GS건설','https://gsenc.recruiter.co.kr/career/home'),
 ('SK 채용목록','https://www.skcareers.com/Recruit'),
 ('DN 개인정보','https://dnautomotive.career.greetinghr.com/ko/personal-info'),
 ('11번가 개인정보','https://11st.career.greetinghr.com/ko/privacy'),
 ('하나머티리얼즈 개인정보','https://hanamts.career.greetinghr.com/privacypolicy'),
 ('DL 플랜트 상시채용','https://www.dlenc.co.kr/careers/job/FieldEmpViewPJ.do?no_empt_anct=260916161205'),
 ('DL 주택 상시채용','https://www.dlenc.co.kr/careers/job/FieldEmpViewPJ.do?no_empt_anct=260825194751'),
 ('DL 토목 상시채용','https://www.dlenc.co.kr/careers/job/FieldEmpViewPJ.do?no_empt_anct=260730165347'),
]

def probe(item):
 name,url=item; base='https://'+urlsplit(url).netloc
 result={'name':name,'url':url}
 try:
  robots=read_direct(base+'/robots.txt').decode('utf-8')
  if '<html' in robots.lower() or not re.search(r'^\s*User-agent\s*:',robots,re.I|re.M): raise ValueError('robots 형식 미확인')
  result['robots']=robots[:2500]
  policy=RobotsPolicy();policy.parse(robots.splitlines())
  if not policy.can_fetch(USER_AGENT,url): raise ValueError('robots 비허용')
  delay=max(2,policy.crawl_delay(USER_AGENT) or 0)
  if delay>30: raise ValueError('요청 간격 한도')
  time.sleep(delay)
  text=read_direct(url).decode('utf-8')
  result['bytes']=len(text)
  result['title']=clean_text(re.search(r'<title[^>]*>([\s\S]*?)</title>',text,re.I)[1]) if '<title' in text else ''
  rows=greeting_rows(text,base)
  result['list_count']=len(rows)
  result['relevant_rows']=[r for r in rows if re.search(RELATED_PATTERN+'|EHS|환경안전',r['title']+' '+str(r['fields']),re.I)][:10]
  links=[(html_url,clean_text(label)) for html_url,label in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',text,re.I)]
  result['policy_links']=[(urljoin(url,u),t) for u,t in links if re.search(r'이용약관|이용조건|개인정보|privacy|terms',u+' '+t,re.I)][:10]
  result['career_links']=[(urljoin(url,u),t[:150]) for u,t in links if re.search(r'FieldEmp|jobnotice|보건|간호|JobPosting',u+' '+t,re.I)][:25]
  result['scripts']=[u for u in re.findall(r'<script[^>]*src=["\']([^"\']+)',text) if re.search(r'career|recruit|job',u,re.I)][:8]
  result['table_rows']=[clean_text(r)[:350] for r in re.findall(r'<tr\b[^>]*>([\s\S]*?)</tr>',text,re.I) if re.search(r'채용|보건|현채직|PJT',clean_text(r))][:12]
  result['jsonld']='application/ld+json' in text
  result['relevant_context']=[clean_text(text)[max(0,m.start()-100):m.end()+300] for m in re.finditer(r'보건관리|산업간호|간호사',clean_text(text))][:8]
  if 'recruiter.co.kr' in base or 'skcareers' in base:
   result['public_markers']=[text[max(0,m.start()-60):m.end()+300] for m in re.finditer(r'jobnoticeSn|채용공고|recruitList|RecruitList|JobPosting|application/ld',text)][:8]
  for term_url,label in result['policy_links'][:1]:
   if urlsplit(term_url).netloc!=urlsplit(url).netloc or not policy.can_fetch(USER_AGENT,term_url): continue
   time.sleep(delay)
   try:
    terms=clean_text(read_direct(term_url).decode('utf-8'))
    result['policy_checked']=term_url
    result['policy_automation_context']=[terms[max(0,m.start()-100):m.end()+160] for m in re.finditer(r'크롤|스크래|로봇|자동화|자동 수집|무단|복제',terms)][:5]
   except Exception as e: result['policy_error']=str(e)
  result['status']='ok'
 except Exception as e: result.update(status='unavailable',reason=str(e))
 return result

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for result in pool.map(probe,CANDIDATES): print('SOURCE_PROBE '+json.dumps(result,ensure_ascii=False),flush=True)

from public_ats import fetch_greenhouse, parse_greenhouse
source={'id':'coupang-greenhouse','name':'쿠팡 · Greenhouse 공개 API','type':'api','adapter':'greenhouse','board_token':'coupang','company':'쿠팡','url':'https://boards-api.greenhouse.io/v1/boards/coupang/jobs','allowed_hosts':['www.coupang.jobs','boards.greenhouse.io','job-boards.greenhouse.io'],'max_details':40}
try:
 raw=fetch_greenhouse(source)
 from collector import now_iso
 jobs,count=parse_greenhouse(raw,source,now_iso())
 payload=json.loads(raw)
 print('ATS_PROBE '+json.dumps(dict(scanned=count,warnings=payload['warnings'],jobs=jobs),ensure_ascii=False),flush=True)
except Exception as e: print('ATS_PROBE '+json.dumps({'error':str(e)}),flush=True)
