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

class PreservedQualificationTests(unittest.TestCase):
 def test_separate_health_and_license_evidence_retained(self):
  job={'title':'간호직 직원 채용','nursing_eligibility':'간호사 면허 자격 명시','qualification_evidence':'간호사 면허증 소지자','keyword_evidence':'보건관리자 근무 경력 3년 이상'}
  self.assertIsNotNone(qualify_job(job))

class WorkplaceNurseTests(unittest.TestCase):
 def test_employee_health_nurse_without_literal_health_manager(self):
  job={'title':'본사 임직원 건강관리 담당자 (간호사)','_qualification_text':'임직원 건강상담 및 응급처치. 간호사 면허증 소지자'}
  self.assertEqual(qualify_job(job)['nursing_eligibility'],'간호사 면허 자격 명시')
 def test_clinical_nurse_is_not_workplace_nurse(self):
  self.assertIsNone(qualify_job({'title':'병동 간호사 채용','_qualification_text':'간호사 면허증 소지자'}))
