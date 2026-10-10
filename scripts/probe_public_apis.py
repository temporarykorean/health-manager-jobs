"""공식 API와 명세의 일회성 읽기 조사. 인증정보/원문 전체는 출력하지 않는다."""
import json,re,urllib.request,concurrent.futures
URLS=[
'https://openapi.gg.go.kr/GGJOBABARECRUSTM?Type=json&pIndex=1&pSize=100&PBANC_CONT=%EB%B3%B4%EA%B1%B4',
'https://openapi.gg.go.kr/EmplmntInfoStus?Type=json&pIndex=1&pSize=100&EMPLMNT_TITLE=%EB%B3%B4%EA%B1%B4',
'https://openapi.gg.go.kr/EmplmntInfoStus?Type=json&pIndex=2&pSize=5',
'https://apis.data.go.kr/1051000/recruitment/list?resultType=json&numOfRows=1&ongoingYn=Y',
'https://m.work24.go.kr/cm/c/a/0410/selectBbttInfo.do?ntceStno=9&bbsClCd=OosccI71O3P2dBxVz5A40Q%3D%3D',
'https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=BF99Q5LCFU0G5XMU9B8L31468278&infSeq=2',
'https://data.seoul.go.kr/dataList/OA-133/S/1/datasetView.do',
]

def probe(url):
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'HealthJobsCollector/1.0'}),timeout=20) as r: s=r.read(2500000).decode('utf-8')
  if 'openapi.gg.go.kr' in url: return {'url':url,'response':json.loads(s)}
  lines=s.splitlines(); selected=[l.strip() for l in lines if re.search('apis.data.go.kr|swagger|openapi.gg.go.kr|GGJOB|RECRU|EMPLOY|채용정보|개인회원|bbsId|ntceStno|dataSetId|infId|apiKey|serviceUrl|serviceName|serviceId|JO_RCT',l,re.I)]
  return {'url':url,'selected':selected[:100], 'context':re.sub('<[^>]+>', ' ', s)[-20000:] if 'selectBbttInfo' in url else ''}
 except Exception as e: return {'url':url,'error':type(e).__name__}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for result in pool.map(probe,URLS): print(json.dumps(result,ensure_ascii=False))
