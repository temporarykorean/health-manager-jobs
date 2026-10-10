import json
import os
import unittest
from unittest.mock import patch
from collector import parse_feed, parse_saramin, collect, fetch_saramin

SOURCE = {'id': 'saramin', 'name': '사람인', 'type': 'saramin', 'url': 'https://oapi.saramin.co.kr/job-search', 'homepage': 'https://www.saramin.co.kr', 'company': '확인 필요'}
CHECKED = '2026-10-10T20:00:00+09:00'

class SaraminTests(unittest.TestCase):
    def test_industrial_nurse_spacing_and_result_notice(self):
        for title, expected in [('산업간호사 채용', 1), ('산업 간호사 계약직 모집', 1), ('산업간호사 합격자 발표', 0)]:
            raw = f'<rss><channel><item><title>{title}</title><link>https://example.org/1</link></item></channel></rss>'.encode()
            self.assertEqual(len(parse_feed(raw, SOURCE, CHECKED)[0]), expected)

    def test_fields_and_open_deadline(self):
        item = {'url': 'https://www.saramin.co.kr/jobs/1', 'active': 1, 'company': {'detail': {'name': '예시회사'}}, 'position': {'title': '산업간호사 모집', 'location': {'name': '경기 > 안산시'}, 'job-type': {'name': '계약직 (정규직 전환가능)'}}, 'expiration-timestamp': 2000000000, 'close-type': {'code': '2'}}
        jobs, count = parse_saramin(json.dumps({'jobs': {'job': [item]}}).encode(), SOURCE, CHECKED)
        self.assertEqual(count, 1)
        self.assertEqual(jobs[0]['employment'], '비정규직')
        self.assertEqual(jobs[0]['region'], '경기')
        self.assertIsNone(jobs[0]['deadline'])
        with self.assertRaises(ValueError):
            parse_saramin(b'{"code":2}', SOURCE, CHECKED)
        self.assertEqual(parse_saramin(b'{"jobs":{"job":[]}}', SOURCE, CHECKED), ([], 0))

    def test_pending_and_no_secret_in_error(self):
        with patch.dict(os.environ, {}, clear=True):
            data, _ = collect({}, [SOURCE], lambda _: self.fail('미연결 요청'), CHECKED)
            self.assertEqual(data['sources'][0]['status'], 'pending')
        with patch.dict(os.environ, {'SARAMIN_ACCESS_KEY': 'private-key'}), patch('collector.urlopen', side_effect=OSError('URL private-key')):
            with self.assertRaises(ValueError) as error:
                fetch_saramin(SOURCE)
            self.assertNotIn('private-key', str(error.exception))
