"""공개 출처 1회 조사. 인증정보나 개인회원 페이지를 요청하지 않습니다."""
import json
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser
from pathlib import Path

results = {}
def fetch(url):
    try:
        with urlopen(Request(url, headers={'User-Agent': 'HealthJobsCollector/1.0'}), timeout=12) as response:
            data = response.read(400000).decode('utf-8', errors='replace')
            results[url] = {'url': response.url, 'text': data}
            print('PROBE',url, 'OK',len(data))
            return data
    except Exception as error:
        results[url] = {'error': str(error)}
        print('PROBE',url,'ERROR',str(error))
        return ''

hosts = ['https://job.alio.go.kr','https://careers.hybecorp.com','https://kodma.recruiter.co.kr','https://ibk4.incruit.com','https://recruit.lotte.co.kr','https://recruit.greetinghr.com']
for base in hosts:
    robots = fetch(base + '/robots.txt')
    print('ROBOTS',base,robots[:2000])
    policy = RobotFileParser()
    policy.parse(robots.splitlines())
    paths = ['/recruit.do','/recruitview.do?idx=305608'] if 'alio' in base else ['/ko/home'] if 'hybe' in base else ['/app/jobnotice/list'] if 'recruiter' in base else ['/hire/hirelist.asp'] if 'incruit' in base else ['/apply/announcement/list'] if 'lotte' in base else ['/']
    for path in paths:
        url=base+path
        if robots and not policy.can_fetch('HealthJobsCollector/1.0',url):
            print('EXCLUDED ROBOTS',url)
            continue
        text=fetch(url)
        print('SCRIPTS',url,re.findall(r'<script[^>]+src=["\']([^"\']+)',text))
        print('LINKS',url,re.findall(r'href=["\']([^"\']+)',text)[-30:])
        print('INPUTS',url,re.findall(r'<(?:input|select|form)[^>]+>',text)[:80])
        print('HINTS',url,'\n'.join(line[:700] for line in text.splitlines() if re.search(r'ajax|url\s*:|recruit|fetch\(|__NEXT_DATA__|copyright',line,re.I))[:14000])
Path('data/source_probe.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
