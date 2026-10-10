"""공식 API와 명세의 일회성 읽기 조사. 인증정보/원문 전체는 출력하지 않는다."""
import json,re,urllib.request,concurrent.futures
URLS=[
'https://www.data.go.kr/data/15031949/openapi.do',
'https://www.data.go.kr/data/15031950/openapi.do',
'https://m.work24.go.kr/cm/e/a/0110/selectOpenApiSvcInfo.do',
'https://www.data.go.kr/data/15000485/openapi.do',
'https://data.gg.go.kr/portal/openapi/insertApikeyPage.do',
'https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=VAFPYPI2D6NZ5H6KKAI629495055&infSeq=2',
]

def probe(url):
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'HealthJobsCollector/1.0'}),timeout=20) as r: s=r.read(2500000).decode('utf-8')
  if 'openapi.gg.go.kr' in url: return {'url':url,'response':json.loads(s)}
  lines=s.splitlines(); selected=[l.strip() for l in lines if re.search('apis.data.go.kr|swagger|openapi.gg.go.kr|GGJOB|RECRU|EMPLOY|채용정보|개인회원|bbsId|ntceStno|dataSetId|infId|apiKey|serviceUrl|serviceName|serviceId|JO_RCT|callOpenApi|fullApiSvcId|<option|자동승인|발급|sample|샘플|1000',l,re.I)]
  return {'url':url,'selected':selected[:100], 'context':re.sub('<[^>]+>', ' ', s)[-20000:] if 'selectBbttInfo' in url else ''}
 except Exception as e: return {'url':url,'error':type(e).__name__}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for result in pool.map(probe,URLS): print(json.dumps(result,ensure_ascii=False))
