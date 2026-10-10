import json
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
results={}
def fetch(url,data=None):
 try:
  with urlopen(Request(url,data=data,headers={'User-Agent':'HealthJobsCollector/1.0'}),timeout=15) as response:
   raw=response.read(700000)
   text=raw.decode('utf-8',errors='replace')
   results[url]={'url':response.url,'text':text}
   print('OK',url,len(raw),text[:250])
 except Exception as e:
  results[url]={'error':str(e)}
  print('ERROR',url,str(e))
fetch('https://job.alio.go.kr/getCSVRecruitList.do',urlencode({'fileName':'채용정보목록'}).encode())
fetch('https://job.alio.go.kr/recruit.do?'+urlencode({'keyword':'보건','search_type':'','pageSet':50,'pageNo':1,'s_date':'2026.06.01','e_date':'2026.10.10'}))
fetch('https://job.alio.go.kr/right.do')
fetch('https://careers.hybecorp.com/ko/o/234375')
fetch('https://careers.hybecorp.com/sitemap.xml')
fetch('https://smartscore.career.greetinghr.com/robots.txt')
fetch('https://smartscore.career.greetinghr.com/ko/home')
fetch('https://www.greetinghr.com/terms')
Path('data/source_probe.json').write_text(json.dumps(results,ensure_ascii=False))
