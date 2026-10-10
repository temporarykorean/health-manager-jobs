"""robots.txt의 그룹, 가장 구체적인 규칙, * 및 $ 패턴을 처리합니다."""
import re
from urllib.parse import urlsplit, unquote
from urllib.robotparser import RobotFileParser

class RobotsPolicy(RobotFileParser):
    def parse(self, lines):
        lines=list(lines)
        super().parse(lines)
        self.groups=[]; agents=[]; rules=[]; has_directives=False
        for raw in lines:
            line=raw.split('#',1)[0].strip()
            if ':' not in line: continue
            key,value=line.split(':',1); key=key.strip().lower(); value=value.strip()
            if key=='user-agent':
                if has_directives:
                    self.groups.append((agents,rules)); agents=[]; rules=[]; has_directives=False
                agents.append(value.lower())
            elif agents and key in ('allow','disallow','crawl-delay','request-rate'):
                has_directives=True
                if key in ('allow','disallow') and value:
                    rules.append((key=='allow',value))
        if agents: self.groups.append((agents,rules))

    def can_fetch(self, useragent, url):
        ua=useragent.lower().split('/')[0]
        matching=[]
        for agents,rules in self.groups:
            specificity=max((0 if a=='*' else len(a) for a in agents if a=='*' or a in ua),default=-1)
            if specificity>=0: matching.append((specificity,rules))
        if not matching: return True
        best=max(s for s,_ in matching)
        parts=urlsplit(url); path=unquote(parts.path or '/')
        if parts.query: path+='?'+unquote(parts.query)
        matches=[]
        for specificity,rules in matching:
            if specificity!=best: continue
            for allow,rule in rules:
                anchored=rule.endswith('$'); pattern=rule[:-1] if anchored else rule
                regex='^'+'.*'.join(re.escape(p) for p in unquote(pattern).split('*'))+('$' if anchored else '')
                if re.search(regex,path): matches.append((len(pattern.replace('*','')),allow))
        return max(matches,default=(0,True))[1]
