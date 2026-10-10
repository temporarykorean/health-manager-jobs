"""API·RSS·검토된 채용페이지·검색 링크 수집기. Python 3.10 이상, 추가 패키지와 GPT/API 키 불필요."""

import hashlib
import html
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen
from source_policy import kind, adapter, pending_reason, PRIORITIES
from job_target import qualify_job
from public_careers import fetch_alio, parse_alio, fetch_greeting, parse_greeting
from source_adapters import fetch_pages, parse_pages, fetch_search, parse_search

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
MAX_BYTES = 3_000_000
SEARCH_KEYWORDS = ("보건관리자", "보건 관리자", "산업간호사", "산업 간호사", "보건관리원", "사업장 간호사", "산업보건", "EHS 보건", "안전보건")
RELATED_PATTERN = r"보건\s*관리(?:자|원)?|산업\s*간호(?:사)?|사업장\s*간호사|산업\s*보건|EHS\s*보건|안전\s*보건"


def now_iso():
    return datetime.now(KST).isoformat(timespec="seconds")


def clean_text(value):
    value = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", value, flags=re.S | re.I)
    value = re.sub(r"<(?:br\b[^>]*|/p|/div|/tr|/li|/h[1-6])\s*>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]*>", " ", value)
    return "\n".join(re.sub(r"[ \t]+", " ", html.unescape(line)).strip()
                     for line in value.splitlines()).strip()


def recruitment_evidence(text):
    # 모든 현장직의 공통 법규/기초교육 문구를 보건 직무 요구로 오인하지 않습니다.
    return re.sub(r"산업안전보건법|건설업\s*기초\s*안전보건교육|안전보건교육\s*이수(?:자|\s*가능자)?", "", text)


def specific_original(url):
    parts = urlsplit(url)
    return bool(re.search(r"/(?:o/)?\d+/?$", parts.path) or any(re.search(r"(?:idx|id|sn|seq|no|num)$", key, re.I) and value for key, value in parse_qsl(parts.query)))


def employment_type(text):
    # 미래의 정규직 전환과 '전환 대상이 아님'은 현재 채용형태가 아닙니다.
    text = re.sub(r"정규직\s*(?:전환|채용전환)[^\n,;]*", "", text)
    text = re.sub(r"(?:정규직|비정규직|계약직)\s*(?:이\s*)?(?:아님|아닌|제외)", "", text)
    regular = "정규직" in text.replace("비정규직", "")
    non_regular = bool(re.search(r"비정규직|계약직|기간제|파견직|인턴|일용직|임시직|시간제|프로젝트\s*계약|대체\s*인력|휴직\s*대체|촉탁직", text))
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
        return "기타"
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
        return "기타"
    name = found.pop()
    return name if name in {"서울", "경기", "인천"} else "기타"


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


def deduplicate_jobs(jobs):
    """원문/기관 제공 별칭 및 회사·공고명·근무지·게시일 일치 중복만 제거."""
    kept = []
    seen = set()
    def normalize(value):
        return re.sub(r"[\s\W_]+", "", value.casefold().replace("(주)", "").replace("주식회사", ""))
    for job in sorted(jobs, key=lambda j: (j.get("source_priority", 99), j.get("id", ""))):
        keys = {("url", canonical_url(job["url"]))}
        if job.get("employer_url") and specific_original(job["employer_url"]):
            keys.add(("url", canonical_url(job["employer_url"])))
        if all(job.get(key) for key in ("company", "title", "location", "published_at")) and "확인 필요" not in job["location"]:
            keys.add(("posting", normalize(job["company"]), normalize(job["title"]), normalize(job["location"]), job["published_at"][:10]))
        if not keys & seen:
            kept.append(job)
        seen.update(keys)
    return kept


def active_job(job, checked_at):
    try:
        return not job.get("deadline") or datetime.fromisoformat(job["deadline"].replace("Z", "+00:00")) >= datetime.fromisoformat(checked_at)
    except (ValueError, TypeError):
        return True


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
        if not re.search(RELATED_PATTERN, title + "\n" + description):
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
            "first_seen": checked_at, "last_seen": checked_at, "collected_at": checked_at, "location_detail": location or "상세 근무지 원문 확인 필요", "origin": "rss", "_qualification_text": description,
        })
    return [qualified for job in jobs if (qualified := qualify_job(job))], len(items)


def parse_saramin(raw, source, checked_at):
    payload = json.loads(raw)
    if not isinstance(payload.get("jobs"), dict):
        raise ValueError("사람인 API 응답 오류")
    items = payload["jobs"].get("job", [])
    if not isinstance(items, list):
        raise ValueError("사람인 공고 목록 형식 오류")
    jobs = []
    for item in items:
        position = item.get("position", {})
        title = clean_text(position.get("title", ""))
        evidence = title + " " + str(item.get("keyword", "")) + " " + position.get("job-code", {}).get("name", "")
        if not re.search(RELATED_PATTERN, evidence):
            continue
        link = safe_url(item.get("url", ""))
        if not link or not title:
            continue
        location = clean_text(position.get("location", {}).get("name", ""))
        employment = clean_text(position.get("job-type", {}).get("name", ""))
        def timestamp(name):
            try:
                value = int(item.get(name, 0))
                return datetime.fromtimestamp(value, KST).isoformat(timespec="seconds") if value > 0 else None
            except (ValueError, TypeError, OverflowError, OSError):
                return None
        deadline = timestamp("expiration-timestamp") if str(item.get("close-type", {}).get("code")) == "1" else None
        if str(item.get("active")) == "0" and not deadline:
            deadline = checked_at
        jobs.append({
            "id": hashlib.sha256(canonical_url(link).encode()).hexdigest()[:20],
            "title": title, "company": clean_text(item.get("company", {}).get("detail", {}).get("name", "")) or "회사명 확인 필요",
            "url": link, "source_id": source["id"], "source": source["name"],
            "employment": employment_type(employment), "employment_evidence": employment or "명시 정보 없음",
            "region": region_type(location), "location": location or "근무지 확인 필요",
            "deadline": deadline, "published_at": timestamp("posting-timestamp"),
            "first_seen": checked_at, "last_seen": checked_at, "collected_at": checked_at, "location_detail": location or "상세 근무지 원문 확인 필요", "origin": "api", "_qualification_text": evidence,
        })
    return [qualified for job in jobs if (qualified := qualify_job(job))], len(items)


def fetch_saramin(source):
    key = os.environ.get("SARAMIN_ACCESS_KEY", "").strip()
    if not key:
        raise ValueError("사람인 API 키 미설정")
    combined = []
    # 키워드를 따로 요청하여 두 단어를 모두 요구하는 AND 검색을 피합니다.
    for keyword in SEARCH_KEYWORDS:
        for page in range(10):
            query = urlencode({"access-key": key, "keywords": keyword, "start": page, "count": 110, "sort": "pd"})
            request = Request(source["url"] + "?" + query, headers={"Accept": "application/json", "User-Agent": "HealthJobs/1.0"})
            try:
                with urlopen(request, timeout=20) as response:
                    raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("응답 크기 초과")
                data = json.loads(raw)
                if not isinstance(data.get("jobs"), dict):
                    raise ValueError("응답 형식 오류")
                items = data["jobs"].get("job", [])
                if not isinstance(items, list):
                    raise ValueError("공고 목록 형식 오류")
                combined.extend(items)
                if (page + 1) * 110 >= int(data["jobs"].get("total", len(items))):
                    break
                if page == 9:
                    raise ValueError("페이지 수집 한도 초과")
            except Exception:
                # URL에 API 키가 있으므로 원본 예외나 응답 내용을 출력하지 않습니다.
                raise ValueError("사람인 API 요청 실패 · 키/승인/호출 한도 확인") from None
    return json.dumps({"jobs": {"job": combined}}, ensure_ascii=False).encode()


def fetch_feed(source):
    source_adapter = ADAPTERS[adapter(source)]
    if source_adapter[0] is not None:
        return source_adapter[0](source)
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


# 어댑터는 (가져오기, 해석하기) 계약을 공유합니다.
# 잡코리아는 승인 후 실제 제공 명세에 맞춘 어댑터를 등록합니다.
ADAPTERS = {
    "alio": (fetch_alio, parse_alio),
    "greeting": (fetch_greeting, parse_greeting),
    "rss": (None, parse_feed),
    "atom": (None, parse_feed),
    "saramin": (fetch_saramin, parse_saramin),
    "jobposting": (fetch_pages, parse_pages),
    "naver_search": (fetch_search, parse_search),
}


def collect(previous, sources, fetcher=fetch_feed, checked_at=None):
    checked_at = checked_at or now_iso()
    prior_jobs = [qualified for job in previous.get("jobs", []) if (qualified := qualify_job(job))]
    for job in prior_jobs:
        job["region"] = region_type(job.get("location", ""))
        job.setdefault("location_detail", job.get("location", "상세 근무지 원문 확인 필요"))
        job.setdefault("collected_at", job.get("last_seen"))
    existing = {job["id"]: dict(job) for job in prior_jobs}
    prior_status = {source["id"]: source for source in previous.get("sources", [])}
    discoveries = {qualified["id"]: qualified for item in previous.get("discoveries", []) if (qualified := qualify_job(item))}
    statuses = []
    successes = 0
    for source in sorted(sources, key=lambda item: PRIORITIES.get(kind(item), 99)):
        old = prior_status.get(source["id"], {})
        status = {"id": source["id"], "name": source["name"], "homepage": source["homepage"],
                  "attempted_at": checked_at, "last_success_at": old.get("last_success_at"),
                  "type": kind(source), "priority": PRIORITIES.get(kind(source), 99)}
        reason = pending_reason(source, checked_at, ADAPTERS)
        if reason:
            status.update(status="pending", message=reason)
            statuses.append(status)
            continue
        try:
            parser = ADAPTERS[adapter(source)][1]
            raw = fetcher(source)
            jobs, count = parser(raw, source, checked_at)
            warnings = json.loads(raw).get("warnings", []) if adapter(source) in {"alio", "greeting"} else []
            if adapter(source) == "alio":
                accepted_ids = {job["id"] for job in jobs}
                # 이번 실행에서 상세를 다시 확인한 비관련 공고만 제거. 접속 실패 자료는 보존.
                for document in json.loads(raw)["documents"]:
                    rejected = "alio-" + document["row"]["idx"]
                    if rejected not in accepted_ids:
                        existing.pop(rejected, None)
            destination = discoveries if kind(source) == "search" else existing
            for job in jobs:
                prior = destination.get(job["id"], {})
                job["first_seen"] = prior.get("first_seen", checked_at)
                job["source_priority"] = PRIORITIES[kind(source)]
                job["collected_at"] = checked_at
                job.setdefault("location_detail", job.get("location", "상세 근무지 원문 확인 필요"))
                # 같은 원문 URL은 더 높은 우선순위의 출처를 유지합니다.
                if not prior or job["source_priority"] <= prior.get("source_priority", 99):
                    destination[job["id"]] = job
            status.update(status="partial" if warnings else "ok", warnings=warnings, last_success_at=checked_at, feed_count=count,
                          matched_count=len(jobs), message=("일부 조회 실패/한도 · " if warnings else "") + f"게시물 {count}개 확인 · 관련 {'원문 후보' if kind(source) == 'search' else '공고'} {len(jobs)}개")
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
        if not prior or (job.get("source_priority", 99), -datetime.fromisoformat(job["last_seen"]).timestamp()) < (prior.get("source_priority", 99), -datetime.fromisoformat(prior["last_seen"]).timestamp()):
            jobs_by_url[key] = job
    final_jobs = deduplicate_jobs(jobs_by_url.values())
    for status in statuses:
        saved = [job for job in final_jobs if job.get("source_id") == status["id"]]
        status["saved_count"] = len(saved)
        status["active_count"] = sum(active_job(job, checked_at) for job in saved)
        status["message"] += f" · 중복 제거 후 저장 {len(saved)}건"
    return {
        "schema_version": 2, "attempted_at": checked_at,
        "last_success_at": checked_at if successes else previous.get("last_success_at"),
        "jobs": sorted(final_jobs, key=lambda job: job.get("published_at") or job.get("first_seen", ""), reverse=True),
        "discoveries": sorted((item for item in discoveries.values() if canonical_url(item["url"]) not in jobs_by_url),
                              key=lambda item: item.get("first_seen", ""), reverse=True)[:500],
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
