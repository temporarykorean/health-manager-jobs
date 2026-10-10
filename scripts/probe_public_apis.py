"""공식 API와 명세의 일회성 읽기 조사. 인증정보/원문 전체는 출력하지 않는다."""
import json,re,urllib.request,concurrent.futures
URLS=[
'https://openapi.gg.go.kr/GGJOBABARECRUSTM?Type=json&pIndex=1&pSize=5',
'https://openapi.gg.go.kr/EmplmntInfoStus?Type=json&pIndex=1&pSize=5',
'https://www.data.go.kr/data/15125273/openapi.do',
'https://www.data.go.kr/data/15097328/openapi.do',
'https://www.data.go.kr/data/15043125/openapi.do',
'https://www.data.go.kr/data/15047488/openapi.do',
'https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=BF99Q5LCFU0G5XMU9B8L31468278&infSeq=3',
'https://m.work24.go.kr/cm/c/a/0410/selectBbttList.do?bbsClCd=OosccI71O3P2dBxVz5A40Q%3D%3D&bbsUrl=/c/a/0410/selectBbttListPost.do&currentPageNo=1&recordCountPerPage=10',
]
def probe(url):
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'HealthJobsCollector/1.0'}),timeout=20) as r: s=r.read(2500000).decode('utf-8')
  if 'openapi.gg.go.kr' in url: return {'url':url,'response':json.loads(s)}
  lines=s.splitlines(); selected=[l.strip() for l in lines if re.search('apis.data.go.kr|swagger|openapi.gg.go.kr|GGJOB|RECRU|EMPLOY|채용정보|개인회원|bbsId|ntceStno|dataSetId|infId|apiKey|serviceUrl|serviceName|serviceId|JO_RCT',l,re.I)]
  return {'url':url,'selected':selected[:100]}
 except Exception as e: return {'url':url,'error':type(e).__name__}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for result in pool.map(probe,URLS): print(json.dumps(result,ensure_ascii=False))
