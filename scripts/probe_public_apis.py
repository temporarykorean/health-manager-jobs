import os,json,urllib.request,urllib.parse
key=urllib.parse.unquote(os.environ['DATA_GO_KR_SERVICE_KEY'].strip())
params={'serviceKey':key,'resultType':'json','ongoingYn':'Y','numOfRows':100,'pageNo':1}
def shape(v,depth=0):
 if depth>4: return type(v).__name__
 if isinstance(v,dict): return {k:shape(x,depth+1) for k,x in v.items()}
 if isinstance(v,list): return {'length':len(v),'first':shape(v[0],depth+1) if v else None}
 return type(v).__name__
try:
 with urllib.request.urlopen(urllib.request.Request('https://apis.data.go.kr/1051000/recruitment/list?'+urllib.parse.urlencode(params),headers={'Accept':'application/json','User-Agent':'HealthJobsCollector/1.0'}),timeout=20) as response: d=json.load(response)
 print(json.dumps({'shape':shape(d),'resultCode':d.get('resultCode'),'totalCount':d.get('totalCount')},ensure_ascii=False))
except Exception as e: print('API inspection failure: '+type(e).__name__)
