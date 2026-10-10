import json
import unittest
from unittest.mock import patch
from collector import collect, parse_feed, SEARCH_KEYWORDS
from public_careers import parse_alio, parse_greeting, iso_date, PublicSession
from source_policy import pending_reason, public_url

CHECKED='2026-10-10T20:00:00+09:00'
SOURCE={'id':'alio','name':'ALIO','homepage':'https://job.alio.go.kr/recruit.do','url':'https://job.alio.go.kr/recruit.do','company':'기관','type':'page','adapter':'alio','allowed_hosts':['job.alio.go.kr'],'allowed_paths':['/recruit.do','/recruitview.do'],'page_urls':['https://job.alio.go.kr/recruit.do'],'access_review':{'decision':'allowed','reviewed_at':CHECKED,'terms_url':'https://job.alio.go.kr/right.do','notes':'공개 메타데이터'}}

def alio(title='직원 채용', employment='비정규직'):
    row={'idx':'123','title':title,'company':'공공기관','location':'인천','employment':employment,'published_at':'2026-10-01','deadline':None}
    text=f'<p class="titleH2">{title}</p><div id="tab-1"><table><tr><th>고용형태</th><td>{employment}</td></tr><tr><th>근무지</th><td>인천</td></tr><tr><th>채용기간</th><td>26.10.01~26.10.15</td></tr><tr><th>응시자격</th><td>보건관리자 선임 자격</td></tr></table></div><div id="tab-2">'
    return json.dumps({'documents':[{'row':row,'html':text,'url':'https://job.alio.go.kr/recruitview.do?idx=123'}],'scanned':1,'warnings':[]}).encode()

class PublicSourceTests(unittest.TestCase):
    def test_alio_body_qualification_structured_fields(self):
        jobs,count=parse_alio(alio(),SOURCE,CHECKED)
        self.assertEqual(count,1)
        self.assertEqual(jobs[0]['employment'],'비정규직')
        self.assertEqual(jobs[0]['region'],'인천')
        self.assertEqual(jobs[0]['deadline'],'2026-10-15T23:59:59+09:00')
        self.assertIn('보건관리자',jobs[0]['keyword_evidence'])
        self.assertEqual(jobs[0]['location_detail'],'상세 근무지 원문 확인 필요')
    def test_alio_mixed_employment_uncertain(self):
        self.assertEqual(parse_alio(alio(employment='정규직,비정규직'),SOURCE,CHECKED)[0][0]['employment'],'확인 필요')
    def test_all_keywords_in_feed_body(self):
        for keyword in SEARCH_KEYWORDS:
            raw=f'<rss><channel><item><title>직원 채용</title><link>https://example.org/1</link><description>{keyword} 자격</description></item></channel></rss>'.encode()
            self.assertEqual(len(parse_feed(raw,SOURCE,CHECKED)[0]),1,keyword)
    def test_terms_expiry_blocks_requests(self):
        with patch('collector.fetch_feed',side_effect=AssertionError('must not fetch')):
            result,_=collect({},[SOURCE],checked_at='2027-02-01T20:00:00+09:00')
        self.assertEqual(result['sources'][0]['status'],'pending')
    def test_linkedin_and_portal_direct_access_excluded(self):
        for host in ('www.linkedin.com','www.jobkorea.co.kr','www.saramin.co.kr'):
            source=dict(SOURCE,url='https://'+host+'/jobs')
            self.assertIsNotNone(pending_reason(source,CHECKED,{'alio':None}))
    def test_robots_denial_before_request(self):
        with patch.object(PublicSession,'_read',return_value=b'User-agent: *\nDisallow: /') as read:
            session=PublicSession(SOURCE)
            with self.assertRaisesRegex(ValueError,'robots'):
                session.get(SOURCE['url'])
            self.assertEqual(read.call_count,1)
    def test_partial_collection_retains_jobs_and_warning(self):
        payload=json.loads(alio());payload['warnings']=['조회 한도']
        data,success=collect({},[SOURCE],lambda s:json.dumps(payload).encode(),CHECKED)
        self.assertEqual(success,1)
        self.assertEqual(data['sources'][0]['status'],'partial')
        self.assertEqual(data['sources'][0]['active_count'],1)
    def test_greeting_public_page_state_not_headquarters_guess(self):
        opening={'openingsInfo':{'detail':'간호사 자격을 갖춘 산업간호사 모집','openDate':'2026-10-01T01:00:00Z','dueDate':None},'jobPositionSetting':{'jobPositions':[{'workspacePlace':{'place':'서울특별시 용산구 한강대로 42','detailPlace':'HYBE'}}]}}
        state={'props':{'pageProps':{'dehydratedState':{'queries':[{'queryKey':['career','getOpeningById'],'state':{'data':{'data':opening}}}]}}}}
        doc={'url':'https://careers.hybecorp.com/ko/o/1','title':'EHS 담당자','fields':{'구분':'HYBE','고용형태':'계약직','근무지':'용산'},'html':'<script id="__NEXT_DATA__">'+json.dumps(state)+'</script>'}
        jobs,_=parse_greeting(json.dumps({'documents':[doc],'scanned':1}).encode(),SOURCE,CHECKED)
        self.assertEqual(jobs[0]['region'],'서울')
        self.assertEqual(jobs[0]['employment'],'비정규직')
        self.assertIn('산업간호사',jobs[0]['keyword_evidence'])
    def test_short_year_and_malformed_url(self):
        self.assertEqual(iso_date('26.10.15'),'2026-10-15')
        self.assertFalse(public_url('https://example.org:bad/'))
