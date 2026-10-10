import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from collector import ADAPTERS, collect
from public_apis import (parse_alio_api, parse_gg_api, parse_kto_api, fetch_alio_api,
                         fetch_gg_api, read_api, api_employment, gg_rows, iso_day, alio_rows)
from source_policy import pending_reason

CHECKED = '2026-10-10T22:00:00+09:00'
ALIO = {'id':'alio-api','name':'ALIO API','type':'api','adapter':'alio_api',
        'url':'https://apis.data.go.kr/1051000/recruitment/list','homepage':'https://www.data.go.kr/data/15125273/openapi.do',
        'required_env':['DATA_GO_KR_SERVICE_KEY']}
GG = dict(ALIO,id='gg-jobaba',name='GG',adapter='gg_jobaba',url='https://openapi.gg.go.kr/GGJOBABARECRUSTM',required_env=['GG_API_KEY'])
ROW = {'recrutPblntSn':123,'recrutPbancTtl':'본사 직원 채용','instNm':'기업 A',
       'workRgnNmLst':'서울','hireTypeNmLst':'비정규직','pbancBgngYmd':'20261001','pbancEndYmd':'20261015',
       'aplyQlfcCn':'보건관리자 직무: 간호사 면허 소지자 또는 산업위생관리기사',
       'srcUrl':'https://example.org/jobs/123'}

def raw(rows):
    return json.dumps({'rows':rows,'warnings':[]}).encode()

class PublicApiTests(unittest.TestCase):
    def test_alio_body_match_structured_fields_and_existing_id(self):
        jobs,count=parse_alio_api(raw([ROW]),ALIO,CHECKED)
        self.assertEqual(count,1)
        j=jobs[0]
        self.assertEqual(j['id'],'alio-123')
        self.assertEqual(j['employment'],'비정규직')
        self.assertEqual(j['region'],'서울')
        self.assertEqual(j['published_at'],'2026-10-01')
        self.assertEqual(j['deadline'],'2026-10-15T23:59:59+09:00')
        self.assertEqual(j['nursing_eligibility'],'간호사 면허 자격 명시')
        self.assertNotIn('_qualification_text',j)
    def test_alio_live_success_code_200(self):
        self.assertEqual(alio_rows({'resultCode':200,'result':[{'item':ROW}]}),[ROW])
        with self.assertRaises(ValueError): alio_rows({'resultCode':401,'result':[]})
    def test_alio_live_flat_list_and_ongoing_without_date_filter(self):
        payload={'resultCode':200,'result':[ROW],'totalCount':1}
        with patch.dict(os.environ,{'DATA_GO_KR_SERVICE_KEY':'test'}), patch('public_apis.read_api',return_value=json.dumps(payload).encode()) as read:
            collected=fetch_alio_api(ALIO)
        self.assertEqual(parse_alio_api(collected,ALIO,CHECKED)[0][0]['id'],'alio-123')
        params=read.call_args.args[1]
        self.assertEqual(params['ongoingYn'],'Y')
        self.assertNotIn('pbancBgngYmd',params)
        self.assertNotIn('pbancEndYmd',params)
    def test_cert_only_and_general_safety_excluded(self):
        row=dict(ROW,recrutPbancTtl='산업안전기사',aplyQlfcCn='자격요건: 산업안전기사 필수')
        self.assertEqual(parse_alio_api(raw([row]),ALIO,CHECKED)[0],[])
    def test_api_key_absent_does_not_request_or_remove_existing(self):
        existing=parse_alio_api(raw([ROW]),ALIO,CHECKED)[0]
        with patch.dict(os.environ,{},clear=True):
            with patch('public_apis.read_api',side_effect=AssertionError('no requests')):
                result,count=collect({'jobs':existing},[ALIO],checked_at=CHECKED)
        self.assertEqual(count,0)
        self.assertEqual(len(result['jobs']),1)
        self.assertEqual(result['sources'][0]['status'],'pending')
    def test_endpoint_override_rejected(self):
        with patch.dict(os.environ,{'DATA_GO_KR_SERVICE_KEY':'test-key'}):
            self.assertIsNotNone(pending_reason(dict(ALIO,url='https://example.org'),CHECKED,ADAPTERS))
    def test_api_key_not_in_network_error(self):
        with patch('public_apis.build_opener') as opener:
            opener.return_value.open.side_effect=HTTPError('https://example.org?serviceKey=private-key',403,'bad',{},None)
            with self.assertRaises(ValueError) as error: read_api(ALIO['url'],{'serviceKey':'private-key'})
        self.assertNotIn('private-key',str(error.exception))
    def test_alio_pagination_warning_and_key_single_encoding(self):
        payload={'resultCode':0,'totalCount':250,'result':[dict(item=ROW)]*100}
        with patch.dict(os.environ,{'DATA_GO_KR_SERVICE_KEY':'abc%2B%2F%3D'}):
            with patch('public_apis.read_api',return_value=json.dumps(payload).encode()) as read:
                value=json.loads(fetch_alio_api(dict(ALIO,max_pages=1)))
        self.assertTrue(value['warnings'])
        self.assertEqual(read.call_args.args[1]['serviceKey'],'abc+/=')
    def test_api_employment_fixed_term_negative_and_part_time(self):
        for text,expected in [('기간의 정함이 없는 근로계약/ 파견근로 비희망/ 대체인력채용 비희망','정규직'),
                              ('기간의 정함이 있는 근로계약 24개월','비정규직'),
                              ('기간의 정함이 없는 근로계약(시간선택제)','확인 필요'),('무기계약직','확인 필요')]:
            self.assertEqual(api_employment(text),expected)
    def test_jobaba_portal_link_is_saved_without_visiting_portal(self):
        row={'ENTRPRS_NM':'한신공영','PBANC_CONT':'보건관리자 모집','PBANC_FORM_DIV':'계약직',
             'WORK_REGION_CD_CONT':'4139','WORK_REGION_CONT':'시흥시','RCPT_BGNG_DE':'20260901','RCPT_END_DE':'20261015',
             'URL':'https://www.jobkorea.co.kr/Recruit/GI_Read/123'}
        jobs,count=parse_gg_api(raw([row]),GG,CHECKED)
        self.assertEqual(count,1)
        self.assertEqual(jobs[0]['region'],'경기')
        self.assertIsNone(jobs[0]['published_at'])
        self.assertEqual(jobs[0]['nursing_eligibility'],'간호사 지원자격 확인 필요')
    def test_gg_no_data_and_permission_error(self):
        self.assertEqual(gg_rows({'RESULT':{'CODE':'INFO-200'}},'GGJOBABARECRUSTM'),([],0))
        with self.assertRaises(ValueError): gg_rows({'RESULT':{'CODE':'ERROR-290'}},'GGJOBABARECRUSTM')
    def test_gg_repeated_page_reported_partial(self):
        v={'GGJOBABARECRUSTM':[{'head':[{'list_total_count':250},{'RESULT':{'CODE':'INFO-000'}}]},
                                     {'row':[{'URL':'https://example.org/123','PBANC_CONT':'보건관리자'}]}]}
        with patch.dict(os.environ,{'GG_API_KEY':'real-test'}), patch('public_apis.read_api',return_value=json.dumps(v).encode()), patch('public_apis.time.sleep'):
            value=json.loads(fetch_gg_api(GG))
        self.assertEqual(len(value['rows']),1)
        self.assertTrue(any('반복' in w for w in value['warnings']))
    def test_kto_xml_omitted_fields_stay_unknown(self):
        xml=b'<response><result><resultCode>00</resultCode><resultItem><orgNm>KTO</orgNm><itemId>1</itemId><itemStatus>Y</itemStatus><title>\xeb\xb3\xb4\xea\xb1\xb4\xea\xb4\x80\xeb\xa6\xac\xec\x9e\x90</title><itemUrl>https://example.org/1</itemUrl><regDate>2026/10/01 09:00:00</regDate><endDate>2026/10/15</endDate></resultItem></result></response>'
        jobs,count=parse_kto_api(xml,dict(ALIO,id='kto'),CHECKED)
        self.assertEqual(count,1)
        self.assertEqual(jobs[0]['employment'],'확인 필요')
        self.assertEqual(jobs[0]['region'],'기타')
        self.assertEqual(jobs[0]['published_at'],'2026-10-01')
    def test_invalid_date_not_fabricated(self):
        self.assertIsNone(iso_day('채용시까지'))
        self.assertIsNone(iso_day('20261399'))

if __name__=='__main__': unittest.main()
