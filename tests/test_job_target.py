import unittest
from job_target import qualify_job

class NursingTargetTests(unittest.TestCase):
    def job(self, title, body):
        return qualify_job({'title':title,'_qualification_text':body})
    def test_excludes_other_professions(self):
        for title in ('산업위생사 채용','산업위생관리기사 모집','계약직 산업안전기사(안전보건팀)','기간제 안전관리자 채용'):
            self.assertIsNone(self.job(title,'타 직렬 간호사 면허. 보건관리자 경력 우대'))
    def test_alternative_license_retained(self):
        result=self.job('기업 보건관리자','필수: 간호사 면허 또는 산업위생관리기사 자격증 소지자')
        self.assertEqual(result['nursing_eligibility'],'간호사 면허 자격 명시')
        self.assertNotIn('_qualification_text',result)
    def test_certificate_only_requirement_excluded(self):
        self.assertIsNone(self.job('보건관리자 모집','필수: 산업위생관리기사 자격증 소지자'))
    def test_unclear_health_role_flagged(self):
        self.assertEqual(self.job('사업장 보건관리자','보건관리자 선임 가능자')['nursing_eligibility'],'간호사 지원자격 확인 필요')
    def test_safety_keyword_alone_excluded(self):
        self.assertIsNone(self.job('시설직 모집','안전보건 관련 교육 이수자'))

    def test_two_required_credentials_are_not_nurse_only(self):
        self.assertIsNone(self.job('보건관리자','필수: 간호사 면허 및 산업안전기사 모두 보유'))
