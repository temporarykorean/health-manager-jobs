import json
import unittest
from unittest.mock import patch
from public_ats import parse_greenhouse, fetch_greenhouse
from official_pages import dl_rows, parse_dlenc, fetch_dlenc
from collector import collect
from robots_policy import RobotsPolicy

NOW='2026-10-10T22:00:00+09:00'
SOURCE={'id':'gh','name':'공개 API','type':'api','adapter':'greenhouse','board_token':'company','company':'기업','url':'https://boards-api.greenhouse.io/v1/boards/company/jobs','homepage':'https://company.kr/jobs','allowed_hosts':['company.kr']}

def payload(title='보건관리자',content='간호사 면허 또는 산업위생관리기사. 고용형태: 정규직',location='Seoul'):
 return json.dumps({'scanned':2,'documents':[{'id':1,'title':title,'content':content,'absolute_url':'https://company.kr/jobs/1','location':{'name':location},'updated_at':'2026-10-10T00:00:00Z'}],'warnings':[],'listed_ids':['1'],'complete_listing':True}).encode()

class PublicATSTests(unittest.TestCase):
 def test_nurse_alternative_and_seoul_english(self):
  jobs,count=parse_greenhouse(payload(),SOURCE,NOW)
  self.assertEqual(count,2); self.assertEqual(jobs[0]['region'],'서울')
  self.assertEqual(jobs[0]['location'],'서울')
  self.assertEqual(jobs[0]['employment'],'정규직')
  self.assertEqual(jobs[0]['published_at'],None,'갱신일을 게시일로 표시하지 않음')
  self.assertEqual(jobs[0]['deadline'],None)
  self.assertEqual(jobs[0]['nursing_eligibility'],'간호사 면허 자격 명시')
 def test_non_nurse_safety_roles_excluded(self):
  self.assertEqual(parse_greenhouse(payload('산업안전기사','보건관리 업무 우대'),SOURCE,NOW)[0],[])
 def test_explicit_workplace_address(self):
  jobs,_=parse_greenhouse(payload(content='간호사 면허. 근무지\n인천 서구 중봉대로 19\n고용형태: 계약직',location='South Korea'),SOURCE,NOW)
  self.assertEqual(jobs[0]['region'],'인천');self.assertEqual(jobs[0]['employment'],'비정규직')
 def test_api_url_policy(self):
  with patch('public_ats.read_direct',side_effect=AssertionError('외부 요청 금지')):
   with self.assertRaises(ValueError): fetch_greenhouse(dict(SOURCE,url='https://company.kr/private'))
 def test_api_listing_is_not_detail_mass_crawl(self):
  listing={'jobs':[{'id':1,'internal_job_id':1,'title':'산업간호사'},{'id':2,'internal_job_id':2,'title':'개발자'},{'id':3,'internal_job_id':None,'title':'보건관리 인재풀'}]}
  detail={'id':1,'title':'산업간호사','content':'간호사 면허','absolute_url':'https://company.kr/jobs/1'}
  with patch('public_ats.read_direct',side_effect=[json.dumps(listing).encode(),json.dumps(detail).encode()]) as read,patch('public_ats.time.sleep'):
   result=json.loads(fetch_greenhouse(SOURCE))
  self.assertEqual(read.call_count,2);self.assertEqual(result['scanned'],3)
 def test_dl_detail_only_actual_health_row(self):
  page='<table><tr><th>채용대상</th><th>공고일</th><th>마감일</th></tr><tr><td>PJT</td><td>2026.10.01</td><td>9999.12.31</td></tr></table><table><tr><th>번호</th><th>모집분야</th><th>자격요건</th><th>근무지</th></tr><tr><td>1</td><td>보건관리</td><td>간호사 면허</td><td>경기도 안산시</td></tr><tr><td>2</td><td>안전관리</td><td>산업안전기사 필수</td><td>서울</td></tr></table>'
  source=dict(SOURCE,id='dlenc',name='DL이앤씨',company='DL이앤씨')
  data={'documents':[{'row':{'id':'261001123456','url':'https://www.dlenc.co.kr/careers/job/FieldEmpViewPJ.do?no_empt_anct=261001123456','title':'전체직무 상시채용','published_at':None,'deadline':None},'html':page}],'scanned':1,'warnings':[]}
  jobs,count=parse_dlenc(json.dumps(data).encode(),source,NOW)
  self.assertEqual(count,1);self.assertEqual(jobs[0]['employment'],'비정규직');self.assertEqual(jobs[0]['region'],'경기')
  self.assertIsNone(jobs[0]['deadline']);self.assertIn('간호사 면허',jobs[0]['qualification_evidence'])
  data['documents'][0]['html']=page.replace('보건관리','안전관제')+'<nav>보건관리자</nav>'
  self.assertEqual(parse_dlenc(json.dumps(data).encode(),source,NOW)[0],[])
 def test_dl_url_and_dates(self):
  text='<tr><td><a href="FieldEmpViewPJ.do?currentPage=1&amp;no_empt_anct=261001123456">전체직무 상시채용</a></td><td>2026.10.01 ~ 9999.12.31</td></tr>'
  rows=dl_rows(text,'https://www.dlenc.co.kr/careers/job/')
  self.assertEqual(rows[0]['url'],'https://www.dlenc.co.kr/careers/job/FieldEmpViewPJ.do?no_empt_anct=261001123456')
  self.assertIsNone(rows[0]['deadline']);self.assertEqual(rows[0]['published_at'],'2026-10-01')
 def test_dl_relative_detail_uses_listing_directory(self):
  source=dict(SOURCE,url='https://www.dlenc.co.kr/careers/job/FieldEmpListPJ.do',page_urls=['https://www.dlenc.co.kr/careers/job/FieldEmpListPJ.do'])
  class Session:
   base='https://www.dlenc.co.kr'
   def get(self,url):
    if 'FieldEmpListPJ.do' in url:
     return '<h1>채용공고</h1><table><tr><td><a href="FieldEmpViewPJ.do?no_empt_anct=261001123456">전체직무 상시채용</a></td></tr></table>'
    if url=='https://www.dlenc.co.kr/careers/job/FieldEmpViewPJ.do?no_empt_anct=261001123456': return '<p>보건관리</p>'
    raise ValueError('잘못된 원문 경로')
  with patch('official_pages.PublicSession',return_value=Session()):
   data=json.loads(fetch_dlenc(source))
  self.assertEqual(len(data['documents']),1)
  self.assertEqual(data['warnings'],[])
 def test_robots_wildcards_groups_and_allow_specificity(self):
  policy=RobotsPolicy();policy.parse(['User-agent: *','Disallow: /app*','Allow: /appsite/','Disallow: /*?secret=','User-agent: Googlebot','Allow: /'])
  self.assertFalse(policy.can_fetch('HealthJobsCollector/1.0','https://x.kr/app/jobnotice/1'))
  self.assertTrue(policy.can_fetch('HealthJobsCollector/1.0','https://x.kr/appsite/home'))
  self.assertFalse(policy.can_fetch('HealthJobsCollector/1.0','https://x.kr/job?secret=1'))
  self.assertTrue(policy.can_fetch('Googlebot','https://x.kr/app/jobnotice/1'))

class WithdrawalTests(unittest.TestCase):
 def test_missing_api_job_hidden_and_reopen(self):
  previous,_=collect({},[SOURCE],lambda source:payload(),NOW)
  raw=json.dumps({'documents':[],'scanned':0,'warnings':[],'complete_listing':True,'listed_ids':[]}).encode()
  gone,_=collect(previous,[SOURCE],lambda source:raw,'2026-10-11T22:00:00+09:00')
  self.assertEqual(gone['sources'][0]['active_count'],0)
  self.assertEqual(gone['jobs'][0]['withdrawn_at'],'2026-10-11T22:00:00+09:00')
  reopened,_=collect(gone,[SOURCE],lambda source:payload(),'2026-10-12T22:00:00+09:00')
  self.assertEqual(reopened['sources'][0]['active_count'],1)
  self.assertNotIn('withdrawn_at',reopened['jobs'][0])
 def test_failure_does_not_close_existing_jobs(self):
  previous,_=collect({},[SOURCE],lambda source:payload(),NOW)
  def failing(source): raise TimeoutError('timeout')
  result,_=collect(previous,[SOURCE],failing,'2026-10-11T22:00:00+09:00')
  self.assertNotIn('withdrawn_at',result['jobs'][0])
  self.assertEqual(result['sources'][0]['active_count'],1)

if __name__=='__main__': unittest.main()
