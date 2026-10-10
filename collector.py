"""공식 RSS 수집기. Python 3.10 이상, 추가 패키지와 GPT/API 키 불필요."""

import hashlib
import html
import json
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
MAX_BYTES = 3_000_000


def now_iso():
    return datetime.now(KST).isoformat(timespec="seconds")


def clean_text(value):
    value = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", value, flags=re.S | re.I)
    value = re.sub(r"<(?:br\b[^>]*|/p|/div|/tr|/li|/h[1-6])\s*>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]*>", " ", value)
    return "\n".join(re.sub(r"[ \t]+", " ", html.unescape(line)).strip()
                     for line in value.splitlines()).strip()


def employment_type(text):
    # 미래의 정규직 전환과 '전환 대상이 아님'은 현재 채용형태가 아닙니다.
    text = re.sub(r"정규직\s*(?:전환|채용전환)[^\n,;]*", "", text)
    text = re.sub(r"(?:정규직|비정규직|계약직)\s*(?:이\s*)?(?:아님|아닌|제외)", "", text)
    regular = "정규직" in text.replace("비정규직", "")
    non_regular = bool(re.search(r"비정규직|계약직|기간제|파견직|인턴|일용직|임시직|시간제", text))
    # 무기계약직은 기관별 정의가 달라 정규직으로 단정하지 않습니다.
    if "무기계약" in text or "공무직" in text:
        return "확인 필요"
    if regular and non_regular:
        return "확인 필요"
    if non_regular:
        return "비정규직"
    return "정규직" if regular else "확인 필요"


def region_type(location):
    if not location or re.search(r"전국|미정|협의|확인 필요", location):
        return "확인 필요"
    names = {
        "서울": r"서울(?:특별시|시)?",
        "경기": r"경기(?:도)?",
        "인천": r"인천(?:광역시|시)?", "부산": r"부산(?:광역시|시)?",
        "대구": r"대구(?:광역시|시)?", "대전": r"대전(?:광역시|시)?",
        "광주": r"광주광역시", "울산": r"울산(?:광역시|시)?",
        "세종": r"세종(?:특별자치시|시)?", "강원": r"강원(?:특별자치도|도)?",
        "충북": r"충북|충청북도", "충남": r"충남|충청남도",
        "전북": r"전북|전라북도", "전남": r"전남|전라남도",
        "경북": r"경북|경상북도", "경남": r"경남|경상남도",
        "제주": r"제주(?:특별자치도|도)?",
    }
    found = {name for name, pattern in names.items() if re.search(pattern, location)}
    if len(found) != 1:
        return "확인 필요"
    name = found.pop()
    return name if name in {"서울", "경기"} else "기타 지역"


def labeled_value(text, labels):
    match = re.search(r"(?:" + labels + r")\s*[:：]\s*([^\n]+)", text)
    return match.group(1).strip() if match else ""


def safe_url(value, base=""):
    url = urljoin(base, html.unescape(value.strip()))
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
        return ""
    return url


def canonical_url(url):
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path,
                      urlencode(sorted(query)), ""))


def local_name(element):
    return element.tag.rsplit("}", 1)[-1].lower()


def field(element, name):
    for child in element:
        if local_name(child) == name:
            return "".join(child.itertext()).strip()
    return ""


def published_date(value):
    if not value:
        return None
    try:
        result = parsedate_to_datetime(value)
    except (ValueError, TypeError):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=KST)
    return result.astimezone(KST).date().isoformat()


def deadline_value(text):
    # 공고 게시일을 마감일로 오인하지 않도록 명시된 필드만 사용합니다.
    value = labeled_value(text, r"접수마감|마감일|접수기간")
    matches = re.findall(r"(20\d{2})[./년-]\s*(\d{1,2})[./월-]\s*(\d{1,2})", value)
    if not matches:
        return None
    year, month, day = map(int, matches[-1])
    try:
        end = datetime(year, month, day, 23, 59, 59, tzinfo=KST)
        # 종료 시각이 명시된 경우에만 그 값을 사용합니다.
        time_match = re.search(r"(\d{1,2}):(\d{2})", value[value.rfind(matches[-1][0]):])
        if time_match:
            end = end.replace(hour=int(time_match[1]), minute=int(time_match[2]), second=0)
        return end.isoformat(timespec="seconds")
    except ValueError:
        return None


def parse_feed(raw, source, checked_at):
    if re.search(br"<!DOCTYPE|<!ENTITY", raw, re.I):
        raise ValueError("외부 엔티티를 포함한 XML은 처리하지 않습니다")
    root = ET.fromstring(raw)
    if local_name(root) not in {"rss", "feed", "rdf"}:
        raise ValueError("RSS/Atom 데이터가 아닌 응답입니다")
    items = [item for item in root.iter() if local_name(item) in {"item", "entry"}]
    if not items:
        # HTML 오류나 비어 있는 응답으로 기존 공고가 지워지는 것을 막습니다.
        raise ValueError("게시물이 없는 피드입니다. 기존 공고를 유지합니다")
    jobs = []
    for item in items:
        title = clean_text(field(item, "title"))
        description = clean_text(field(item, "description") or field(item, "encoded")
                                 or field(item, "summary") or field(item, "content"))
        # 제목이 아닌 본문에서만 발견된 경우도 보조 키워드로 검색합니다.
        if not re.search(r"보건\s*관리(?:자|원)?|산업\s*간호", title + "\n" + description):
            continue
        if re.search(r"합격자|합격발표|결과발표|면접시험.*안내|연간.*계획", title):
            continue
        link = field(item, "link")
        if not link:
            link = next((child.get("href", "") for child in item
                         if local_name(child) == "link" and child.get("rel", "alternate") == "alternate"), "")
        link = safe_url(link, source["url"])
        if not link or not title:
            continue
        job_url = canonical_url(link)
        employment_evidence = labeled_value(description, r"고용형태|근무형태|채용형태") or title
        location = labeled_value(description, r"근무지역|근무지|근무장소")
        company = labeled_value(description, r"회사명|기업명|기관명") or source["company"]
        jobs.append({
            "id": hashlib.sha256(job_url.encode()).hexdigest()[:20],
            "title": title, "company": company, "url": link,
            "source_id": source["id"], "source": source["name"],
            "employment": employment_type(employment_evidence),
            "employment_evidence": employment_evidence[:160],
            "region": region_type(location), "location": location or "근무지 확인 필요",
            "deadline": deadline_value(description),
            "published_at": published_date(field(item, "pubdate") or field(item, "published") or field(item, "date")),
            "first_seen": checked_at, "last_seen": checked_at, "origin": "rss",
        })
    return jobs, len(items)


def fetch_feed(source):
    request = Request(source["url"], headers={"User-Agent": "HealthJobsRSS/1.0", "Accept": "application/rss+xml, application/xml, text/xml"})
    with urlopen(request, timeout=20) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("응답이 너무 큽니다")
    return data


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as output:
        json.dump(data, output, ensure_ascii=False, indent=2)
        output.write("\n")
        temporary = Path(output.name)
    temporary.replace(path)


def collect(previous, sources, fetcher=fetch_feed, checked_at=None):
    checked_at = checked_at or now_iso()
    prior_jobs = previous.get("jobs", [])
    existing = {job["id"]: dict(job) for job in prior_jobs}
    prior_status = {source["id"]: source for source in previous.get("sources", [])}
    statuses = []
    successes = 0
    for source in sources:
        old = prior_status.get(source["id"], {})
        status = {"id": source["id"], "name": source["name"], "homepage": source["homepage"],
                  "attempted_at": checked_at, "last_success_at": old.get("last_success_at")}
        try:
            jobs, count = parse_feed(fetcher(source), source, checked_at)
            for job in jobs:
                prior = existing.get(job["id"], {})
                job["first_seen"] = prior.get("first_seen", checked_at)
                existing[job["id"]] = job
            status.update(status="ok", last_success_at=checked_at, feed_count=count,
                          matched_count=len(jobs), message=f"게시물 {count}개 확인 · 관련 공고 {len(jobs)}개")
            successes += 1
        except Exception as error:
            status.update(status="error", message="접속 또는 데이터 처리 실패 · 이전 공고 유지",
                          detail=f"{type(error).__name__}: {error}"[:300])
            print(f"[{source['name']}] 수집 실패: {error}", file=sys.stderr)
        statuses.append(status)
    # 보존된 공고는 자동으로 모집중이라고 단정하지 않습니다. 화면에서 확인 시각 표시.
    jobs_by_url = {}
    for job in existing.values():
        key = canonical_url(job["url"])
        prior = jobs_by_url.get(key)
        if not prior or job.get("last_seen", "") > prior.get("last_seen", ""):
            jobs_by_url[key] = job
    return {
        "schema_version": 1, "attempted_at": checked_at,
        "last_success_at": checked_at if successes else previous.get("last_success_at"),
        "jobs": sorted(jobs_by_url.values(), key=lambda job: job.get("published_at") or job.get("first_seen", ""), reverse=True),
        "sources": statuses,
    }, successes


def main():
    path = ROOT / "data/jobs.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    sources = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    data, successes = collect(previous, sources)
    atomic_json(path, data)
    print(f"수집 성공 {successes}/{len(sources)}곳 · 저장된 공고 {len(data['jobs'])}개")
    # 전체 실패는 자동 실행 기록에서도 실패로 남기고, 웹페이지는 기존 데이터로 배포합니다.
    return 0 if successes else 2


if __name__ == "__main__":
    raise SystemExit(main())
