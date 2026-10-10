"use strict";

const employmentOptions = ["전체", "정규직", "비정규직", "확인 필요"];
const regionOptions = ["전체", "서울", "경기", "인천", "기타"];
const state = { employment: "전체", region: "전체", query: "", savedOnly: false, includeClosed: false, sort: "recent" };
let data = window.INITIAL_JOBS || { jobs: [], sources: [] };
let favorites = new Set();
try { favorites = new Set(JSON.parse(localStorage.getItem("health-jobs-favorites") || "[]")); } catch { /* 저장 불가 환경에서도 조회 가능 */ }
const $ = (id) => document.getElementById(id);

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

function safeLink(url) {
  try { const parsed = new URL(url); return ["https:", "http:"].includes(parsed.protocol) && !parsed.username ? parsed.href : ""; } catch { return ""; }
}

function dateText(value, withTime = false) {
  if (!value || Number.isNaN(Date.parse(value))) return "확인 기록 없음";
  return new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}) }).format(new Date(value));
}

function closed(job, now = Date.now()) { return !!job.withdrawn_at || (!!job.deadline && Date.parse(job.deadline) < now); }

function daysUntil(value, now = Date.now()) {
  if (!value || Number.isNaN(Date.parse(value))) return null;
  const kstDay = (milliseconds) => Math.floor((milliseconds + 9 * 3600000) / 86400000);
  return kstDay(Date.parse(value)) - kstDay(now);
}

function isNew(job, now = Date.now()) {
  const first = Date.parse(job.first_seen);
  return Number.isFinite(first) && first <= now && now - first < 3 * 86400000;
}

function filteredJobs(jobs, filters, saved, now = Date.now()) {
  const query = filters.query.toLocaleLowerCase().trim();
  return jobs.filter(job => (filters.employment === "전체" || job.employment === filters.employment)
    && (filters.region === "전체" || job.region === filters.region)
    && (!filters.savedOnly || saved.has(job.id))
    && (filters.includeClosed || !closed(job, now))
    && (!query || `${job.title} ${job.company} ${job.location} ${job.source}`.toLocaleLowerCase().includes(query)))
    .sort((a, b) => filters.sort === "deadline"
      ? (Date.parse(a.deadline) || Infinity) - (Date.parse(b.deadline) || Infinity)
      : (Date.parse(b.published_at || b.first_seen) || 0) - (Date.parse(a.published_at || a.first_seen) || 0));
}

function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { $("toast").hidden = true; }, 3200);
}

function renderChips(id, options, key) {
  const container = $(id);
  container.replaceChildren();
  options.forEach(option => {
    const button = element("button", "chip", option);
    button.type = "button";
    button.setAttribute("aria-pressed", String(state[key] === option));
    button.onclick = () => { state[key] = option; render(); };
    container.append(button);
  });
}

function card(job) {
  const article = element("article", `job-card${isNew(job) && !closed(job) ? " is-new" : ""}${closed(job) ? " is-closed" : ""}`);
  const top = element("div", "card-top");
  const save = element("button", "save-button", favorites.has(job.id) ? "★ 관심" : "☆ 관심");
  save.setAttribute("aria-pressed", String(favorites.has(job.id)));
  save.setAttribute("aria-label", `${job.title} 관심 공고 ${favorites.has(job.id) ? "해제" : "저장"}`);
  save.onclick = () => {
    if (favorites.has(job.id)) favorites.delete(job.id); else favorites.add(job.id);
    try { localStorage.setItem("health-jobs-favorites", JSON.stringify([...favorites])); }
    catch { toast("이 브라우저에서는 관심 공고가 영구 저장되지 않습니다."); }
    render();
  };
  const company = element("div", "company-line");
  company.append(element("span", "company", job.company));
  if (isNew(job) && !closed(job)) company.append(element("span", "new-badge", "NEW"));
  top.append(company, save);
  const heading = element("h3", "job-title");
  const link = element("a", "", job.title);
  link.href = safeLink(job.url); link.target = "_blank"; link.rel = "noopener noreferrer";
  heading.append(link);
  const badges = element("div", "badges");
  const employmentClass = job.employment === "정규직" ? "regular" : job.employment === "비정규직" ? "nonregular" : "";
  badges.append(element("span", `badge ${employmentClass}`, job.employment), element("span", "badge", job.region));
  if (job.relevance) badges.append(element("span", "badge", job.relevance));
  if (job.origin === "manual") badges.append(element("span", "badge", "초기 직접 확인"));
  const bottom = element("div", "card-bottom");
  const days = daysUntil(job.deadline);
  const end = element("span", `deadline ${days !== null && days <= 3 && days >= 0 ? "urgent" : ""}`,
    job.withdrawn_at ? "채용 목록에서 내려감" : closed(job) ? "마감일 경과" : days === null ? "마감일 확인 필요" : days === 0 ? "오늘 마감" : `${days <= 3 ? "마감 임박 · " : ""}D-${days}`);
  if (job.deadline) end.append(element("small", "", `${dateText(job.deadline, true)} 마감`));
  const original = element("a", "original-link", "원문 보기 ↗");
  original.href = safeLink(job.url); original.target = "_blank"; original.rel = "noopener noreferrer";
  bottom.append(end, original);
  const metadata = element("div", "job-meta");
  metadata.append(element("span", "", `출처 · ${job.source}`), element("span", "", `게시 · ${job.published_at ? dateText(job.published_at) : "확인 필요"}`));
  const evidence = element("details", "evidence");
  evidence.append(element("summary", "", "출처와 분류 기준 확인"));
  const ul = element("ul");
  [`출처: ${job.source}`, `게시일: ${dateText(job.published_at)}`, `상세 근무지: ${job.location_detail || "원문 확인 필요"}`, `간호사 자격 근거: ${job.qualification_evidence || "원문 확인 필요"}`, `키워드 근거: ${job.keyword_evidence || "제목 또는 출처의 직무명"}`, `고용형태 근거: ${job.employment_evidence || "명시 정보 없음"}`, `마지막 확인: ${dateText(job.last_seen, true)}`,
    job.origin === "manual" ? "초기 공고는 직접 확인한 자료입니다. 자동 갱신 대상이 아닙니다." : "연결된 출처에서 확인한 정보입니다. 최신 접수 여부는 원문을 확인해주세요."].forEach(text => ul.append(element("li", "", text)));
  evidence.append(ul);
  article.append(top, heading, badges, element("p", "job-location", job.location), bottom, metadata, evidence);
  return article;
}

function renderSources() {
  $("sources").replaceChildren();
  data.sources.forEach(source => {
    const section = element("div", "source-card");
    const top = element("div", "source-card-top");
    const link = element("a", "", source.name);
    link.href = safeLink(source.homepage); link.target = "_blank"; link.rel = "noopener noreferrer";
    top.append(link, element("span", `source-status ${source.status !== "ok" ? "error" : ""}`, source.status === "ok" ? "수집 성공" : source.status === "partial" ? "부분 수집" : source.status === "error" ? "수집 실패" : source.status === "pending" ? "연결 대기" : "접속 확인 전"));
    const kinds = { api: "공식 API", rss: "공개 RSS", atom: "공개 Atom", page: "검토된 채용페이지", search: "검색 원문 후보" };
    if (source.type) section.append(element("p", "", `${source.priority}순위 · ${kinds[source.type] || source.type}`));
    section.append(top, element("p", "", source.message || "자동 수집 확인 전"), element("p", "", `최근 성공: ${dateText(source.last_success_at, true)}`));
    $("sources").append(section);
  });
}

function renderDiscoveries() {
  const candidates = (data.discoveries || []).filter(item => safeLink(item.url));
  $("discoveries").replaceChildren();
  if (!candidates.length) $("discoveries").append(element("p", "", "아직 발견한 원문 후보가 없습니다. 검색 API 연결 상태를 확인해주세요."));
  candidates.forEach(item => {
    const section = element("div", "source-card");
    const link = element("a", "", item.title);
    link.href = safeLink(item.url); link.target = "_blank"; link.rel = "noopener noreferrer";
    section.append(link, element("p", "", item.verification), element("p", "", `처음 발견: ${dateText(item.first_seen, true)}`));
    $("discoveries").append(section);
  });
}

function render() {
  renderChips("employment-filters", employmentOptions, "employment");
  renderChips("region-filters", regionOptions, "region");
  const open = data.jobs.filter(job => !closed(job));
  $("stat-open").textContent = open.length;
  $("stat-new").textContent = open.filter(job => isNew(job)).length;
  $("stat-urgent").textContent = open.filter(job => { const days = daysUntil(job.deadline); return days !== null && days >= 0 && days <= 3; }).length;
  $("stat-saved").textContent = data.jobs.filter(job => favorites.has(job.id)).length;
  const jobs = filteredJobs(data.jobs, state, favorites);
  $("count").textContent = jobs.length;
  $("list").replaceChildren(...jobs.map(card));
  $("empty").hidden = jobs.length > 0;
  const failed = data.sources.filter(source => ["error", "partial"].includes(source.status));
  const pending = data.sources.filter(source => source.status === "pending");
  const manualCount = data.jobs.filter(job => job.origin === "manual").length;
  const stale = data.last_success_at && Date.now() - Date.parse(data.last_success_at) > 36 * 3600000;
  const messages = [];
  if (!data.last_success_at) messages.push("자동 수집 성공 기록이 아직 없습니다.");
  else if (stale) messages.push("자동 수집 성공 후 36시간 이상 지났습니다. 최신 공고가 누락될 수 있습니다.");
  if (failed.length) messages.push(`${failed.length}곳의 수집이 완료되지 않았습니다. 아래 수집 상태를 확인해주세요.`);
  if (pending.length) messages.push(`${pending.length}곳은 연결 대기 중입니다.`);
  if (manualCount) messages.push(`초기 공고 ${manualCount}건은 직접 확인한 자료이며 자동 갱신되지 않습니다.`);
  $("notice").hidden = !messages.length;
  $("notice").textContent = messages.join(" ");
  $("updated").textContent = data.last_success_at ? `자동 수집 최근 성공 ${dateText(data.last_success_at, true)}` : `자동 수집 미확인${data.attempted_at ? ` · 최근 시도 ${dateText(data.attempted_at, true)}` : ""}`;
  renderSources();
  renderDiscoveries();
}

function reset() {
  Object.assign(state, { employment: "전체", region: "전체", query: "", savedOnly: false, includeClosed: false, sort: "recent" });
  $("query").value = ""; $("saved-only").checked = false; $("include-closed").checked = false; $("sort").value = "recent";
  render();
}

async function reload() {
  if (location.protocol === "file:") { toast("로컬 파일은 다시 열면 갱신됩니다. 인터넷 배포 후에는 새로고침할 수 있습니다."); return; }
  const button = $("reload"); button.disabled = true; button.textContent = "확인 중…";
  try {
    const response = await fetch(`data/jobs.json?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error("data fetch failed");
    const incoming = await response.json();
    if (!Array.isArray(incoming.jobs) || !Array.isArray(incoming.sources)) throw new Error("invalid data");
    data = incoming; render();
  } catch { toast("최신 데이터를 읽지 못했습니다. 현재 표시 중인 공고를 유지합니다."); }
  finally { button.disabled = false; button.textContent = "화면 새로고침 ↻"; }
}

$("query").oninput = (event) => { state.query = event.target.value; render(); };
$("saved-only").onchange = (event) => { state.savedOnly = event.target.checked; render(); };
$("include-closed").onchange = (event) => { state.includeClosed = event.target.checked; render(); };
$("sort").onchange = (event) => { state.sort = event.target.value; render(); };
$("reset").onclick = reset; $("empty-reset").onclick = reset; $("reload").onclick = reload;
$("share").onclick = async () => {
  if (location.protocol === "file:" || ["localhost", "127.0.0.1"].includes(location.hostname)) { toast("인터넷에 배포한 뒤 공유 링크를 사용할 수 있습니다."); return; }
  try {
    if (navigator.share) await navigator.share({ title: document.title, url: location.href });
    else { await navigator.clipboard.writeText(location.href); toast("링크를 복사했습니다. 카카오톡으로 보내주세요."); }
  } catch (error) { if (error.name !== "AbortError") toast("주소창의 링크를 복사해 공유해주세요."); }
};
render();
if (location.protocol !== "file:") reload();
