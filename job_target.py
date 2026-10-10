"""간호사 면허를 바탕으로 지원할 사업장 보건 직무를 선별합니다."""
import re
HEALTH_ROLE = r'보건\s*관리|산업\s*간호|사업장\s*간호|EHS\s*보건'
OTHER_ROLE = r'산업\s*위생(?:사|관리(?:산업)?기사)|산업\s*안전(?:산업)?기사|안전\s*관리자'
LICENSE = r'간호사\s*(?:면허(?:증)?|자격(?:증)?)(?:\s*(?:소지|보유|취득))?'


def qualify_job(job):
    job = dict(job)
    body = job.pop('_qualification_text', '')
    title = job.get('title', '')
    evidence = body or (job.get('qualification_evidence') if job.get('nursing_eligibility') == '간호사 면허 자격 명시' else '') or job.get('keyword_evidence', '')
    evidence = re.sub(r'[\u200b-\u200d\ufeff]', '', evidence)
    if re.search(OTHER_ROLE, title) and not re.search(HEALTH_ROLE + r'|간호(?:사|직)', title):
        return None
    if not re.search(HEALTH_ROLE, title + '\n' + evidence):
        return None
    if re.search(r'간호사\s*(?:면허(?:증)?\s*)?(?:지원\s*불가|제외|불인정)', evidence):
        return None
    nurse = re.search(LICENSE, evidence)
    if not nurse and re.search(r'(?:필수|응시자격|자격요건)[^\n]{0,100}(?:산업위생관리(?:산업)?기사|산업안전(?:산업)?기사)', evidence):
        return None
    if nurse and re.search(r'(?:간호사[^\n]{0,80}(?:및|동시|모두|[+&])[^\n]{0,60}산업(?:위생관리|안전)기사|산업(?:위생관리|안전)기사[^\n]{0,80}(?:및|동시|모두|[+&])[^\n]{0,60}간호사)', evidence) and not re.search(r'또는|중 하나|우대', evidence):
        return None
    if nurse:
        start = evidence.rfind('\n', 0, nurse.start()) + 1
        end = evidence.find('\n', nurse.end())
        job['qualification_evidence'] = evidence[start:end if end >= 0 else len(evidence)].strip()[:200]
        job['nursing_eligibility'] = '간호사 면허 자격 명시'
    else:
        job.setdefault('qualification_evidence', '원문의 자격요건 확인 필요(면허 인정 여부 미확인)')
        job['nursing_eligibility'] = '간호사 지원자격 확인 필요'
    job['relevance'] = job['nursing_eligibility']
    return job
