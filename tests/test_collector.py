import unittest
from collector import collect, employment_type, region_type, parse_feed, deadline_value


SOURCE = {"id": "example", "name": "예시 RSS", "company": "예시기관", "url": "https://example.org/rss", "homepage": "https://example.org"}
CHECKED = "2026-10-10T20:00:00+09:00"


def feed(title="보건관리자 계약직 채용", link="https://example.org/jobs/1", description=""):
    return f'<rss version="2.0"><channel><item><title>{title}</title><link>{link}</link><description><![CDATA[{description}]]></description><pubDate>Sat, 10 Oct 2026 00:00:00 GMT</pubDate></item></channel></rss>'.encode()


class ClassificationTests(unittest.TestCase):
    def test_current_employment_and_ambiguity(self):
        cases = {
            "보건관리자 정규직 채용": "정규직",
            "비정규직 채용": "비정규직",
            "계약직, 추후 정규직 전환 가능": "비정규직",
            "기간제 · 정규직 전환 대상 아님": "비정규직",
            "정규직 또는 계약직": "확인 필요",
            "보건관리자 채용": "확인 필요",
            "무기계약직": "확인 필요",
            "공무직": "확인 필요",
            "정규직 아님": "확인 필요",
            "파견직 채용": "비정규직",
            "인턴 채용": "비정규직",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(employment_type(text), expected)

    def test_region_does_not_guess_city_or_multiple_regions(self):
        cases = {"서울특별시 강서구": "서울", "경기도 광주시": "경기",
                 "광주광역시": "기타 지역", "인천광역시": "기타 지역",
                 "수원시": "확인 필요", "서울 / 경기": "확인 필요",
                 "전국": "확인 필요", "": "확인 필요"}
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(region_type(text), expected)

    def test_deadline_uses_end_of_explicit_range(self):
        self.assertEqual(deadline_value("접수기간: 2026-10-02 14:00 ~ 2026-10-15 23:00"),
                         "2026-10-15T23:00:00+09:00")
        self.assertIsNone(deadline_value("게시일: 2026-10-10"))


class FeedTests(unittest.TestCase):
    def test_html_and_labeled_fields(self):
        jobs, count = parse_feed(feed(description="<p>고용형태: 계약직</p><p>근무지: 경기 안산시</p>"), SOURCE, CHECKED)
        self.assertEqual(count, 1)
        self.assertEqual(jobs[0]["employment"], "비정규직")
        self.assertEqual(jobs[0]["region"], "경기")
        self.assertEqual(jobs[0]["published_at"], "2026-10-10")

    def test_html_error_and_external_entities_rejected(self):
        for raw in [b"<html><body>error</body></html>", b"<rss><channel/></rss>",
                    b'<!DOCTYPE rss [<!ENTITY x "bad">]><rss><channel/></rss>']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_feed(raw, SOURCE, CHECKED)

    def test_atom_and_safe_links(self):
        raw = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>\xeb\xb3\xb4\xea\xb1\xb4\xea\xb4\x80\xeb\xa6\xac\xec\x9e\x90</title><link href="https://example.org/jobs/1"/><published>2026-10-10T01:00:00Z</published></entry></feed>'
        jobs, _ = parse_feed(raw, SOURCE, CHECKED)
        self.assertEqual(jobs[0]["url"], "https://example.org/jobs/1")
        self.assertEqual(parse_feed(feed(link="javascript:alert(1)"), SOURCE, CHECKED)[0], [])

    def test_unrelated_and_result_notices_excluded(self):
        self.assertEqual(parse_feed(feed(title="회계 담당자 채용"), SOURCE, CHECKED)[0], [])
        self.assertEqual(parse_feed(feed(title="보건관리자 최종합격자 발표"), SOURCE, CHECKED)[0], [])

    def test_failure_preserves_previous_jobs_and_success_time(self):
        jobs, _ = parse_feed(feed(), SOURCE, CHECKED)
        previous = {"jobs": jobs, "last_success_at": CHECKED,
                    "sources": [{"id": SOURCE["id"], "last_success_at": CHECKED}]}

        def unavailable(source):
            raise OSError("offline")

        result, successes = collect(previous, [SOURCE], unavailable, "2026-10-11T09:17:00+09:00")
        self.assertEqual(successes, 0)
        self.assertEqual(result["jobs"], jobs)
        self.assertEqual(result["last_success_at"], CHECKED)
        self.assertEqual(result["sources"][0]["status"], "error")
        self.assertEqual(result["sources"][0]["last_success_at"], CHECKED)

    def test_same_url_deduplicated_and_first_seen_preserved(self):
        first, _ = collect({}, [SOURCE], lambda source: feed(), CHECKED)
        second, successes = collect(first, [SOURCE], lambda source: feed(link="https://example.org/jobs/1?utm_source=test"), "2026-10-11T09:17:00+09:00")
        self.assertEqual(successes, 1)
        self.assertEqual(len(second["jobs"]), 1)
        self.assertEqual(second["jobs"][0]["first_seen"], CHECKED)


if __name__ == "__main__":
    unittest.main()
