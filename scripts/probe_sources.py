"""일회성 후보 조사. robots 허용 페이지만 읽고 원문 HTML은 저장하지 않습니다."""
import concurrent.futures
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source_adapters import read_direct, USER_AGENT
from collector import clean_text, RELATED_PATTERN
from public_careers import greeting_rows

CANDIDATES = [
 ('DN오토모티브','https://dnautomotive.career.greetinghr.com/ko/home'),
 ('하나머티리얼즈','https://hanamts.career.greetinghr.com/ko/home'),
 ('11번가','https://11st.career.greetinghr.com/ko/career'),
 ('휴젤','https://hugel.career.greetinghr.com/ko/home'),
 ('동국제강','https://dongkuksteel.career.greetinghr.com/ko/home'),
 ('오늘의집','https://bucketplace.career.greetinghr.com/ko/home'),
 ('DL이앤씨','https://www.dlenc.co.kr/careers/job/FieldEmpList.do'),
 ('DL이앤씨 PJT','https://www.dlenc.co.kr/careers/job/FieldEmpListPJ.do'),
 ('GS건설','https://gsenc.recruiter.co.kr/appsite/company/index'),
 ('현대엔지니어링','https://hec.recruiter.co.kr/career/home'),
 ('HDC현대산업개발','https://hdcr.recruiter.co.kr/appsite/company/index'),
 ('GM','https://generalmotors.wd5.myworkdayjobs.com/ko-KR/Careers_GM'),
 ('SK','https://www.skcareers.com/'),
]

def probe(item):
 name,url=item; base='https://'+urlsplit(url).netloc
 result={'name':name,'url':url}
 try:
  robots=read_direct(base+'/robots.txt').decode('utf-8')
  if '<html' in robots.lower() or not re.search(r'^\s*User-agent\s*:',robots,re.I|re.M): raise ValueError('robots 형식 미확인')
  result['robots']=robots[:2500]
  policy=RobotFileParser();policy.parse(robots.splitlines())
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
