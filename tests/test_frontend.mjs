import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

// 최소 DOM으로 실제 앱을 실행합니다. 브라우저의 시각 검증은 별도입니다.
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.hidden = false; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
}
const ids = new Map();
const document = { createElement: tag => new Element(tag), getElementById: id => {
  if (!ids.has(id)) ids.set(id, new Element("div"));
  return ids.get(id);
}};
const fixture = {
  jobs: [
    { id: "a", company: "회사A", title: "보건관리자 정규직", employment: "정규직", region: "서울", location: "서울 강서구", source: "RSS", url: "https://example.org/a", deadline: "2099-10-15T18:00:00+09:00", last_seen: "2026-10-10T20:00:00+09:00" },
    { id: "b", company: "회사B", title: "보건관리 계약직", employment: "비정규직", region: "경기", location: "경기 안산시", source: "RSS", url: "https://example.org/b", deadline: null, last_seen: "2026-10-10T19:00:00+09:00" },
    { id: "c", company: "회사C", title: "보건관리자", employment: "확인 필요", region: "확인 필요", location: "미기재", source: "RSS", url: "https://example.org/c", deadline: "2000-10-15T18:00:00+09:00", last_seen: "2026-10-10T18:00:00+09:00" },
  ], sources: [], last_success_at: null,
};
const stored = new Map();
const context = vm.createContext({ document, window: { INITIAL_JOBS: fixture }, URL, Intl, Date, console,
  location: { protocol: "file:", hostname: "", href: "file:///index.html" }, navigator: {},
  localStorage: { getItem: key => stored.get(key), setItem: (key, value) => stored.set(key, value) },
  setTimeout: () => 1, clearTimeout: () => {},
});
vm.runInContext(readFileSync(new URL("../web/app.js", import.meta.url), "utf8"), context);
assert.equal(ids.get("count").textContent, 2, "마감 공고는 기본적으로 숨김");
ids.get("employment-filters").children.find(button => button.textContent === "정규직").onclick();
assert.equal(ids.get("count").textContent, 1);
ids.get("region-filters").children.find(button => button.textContent === "경기").onclick();
assert.equal(ids.get("count").textContent, 0, "고용형태와 지역 조건을 함께 적용");
assert.equal(ids.get("empty").hidden, false);
ids.get("reset").onclick();
ids.get("query").oninput({ target: { value: "회사B" } });
assert.equal(ids.get("count").textContent, 1, "회사명 검색");
ids.get("list").children[0].children[0].children[1].onclick();
assert.deepEqual(JSON.parse(stored.get("health-jobs-favorites")), ["b"]);
ids.get("reset").onclick();
ids.get("saved-only").onchange({ target: { checked: true } });
assert.equal(ids.get("count").textContent, 1, "관심 공고만 보기");
ids.get("reset").onclick();
ids.get("include-closed").onchange({ target: { checked: true } });
assert.equal(ids.get("count").textContent, 3, "마감 공고 포함");
assert.equal(vm.runInContext('safeLink("javascript:alert(1)")', context), "", "스크립트 URL 차단");
assert.equal(vm.runInContext('daysUntil("2026-10-15T23:00:00+09:00", Date.parse("2026-10-15T09:00:00+09:00"))', context), 0, "한국 날짜 기준 오늘 마감");
assert.equal(vm.runInContext('daysUntil("2026-10-16T09:00:00+09:00", Date.parse("2026-10-15T23:00:00+09:00"))', context), 1, "한국 날짜 기준 내일 마감");
assert.equal(ids.get("notice").hidden, false, "수집 미확인 상태 표시");
console.log("필터 조합·검색·관심 저장·마감 표시·안전한 링크 검증 통과 (브라우저 시각 검증 제외)");
assert.equal(ids.get('region-filters').children.some(button => button.textContent === '인천'), true, '인천 독립 필터');
const newest = vm.runInContext(`filteredJobs([
 {id:'old',title:'산업간호사',company:'A',source:'ALIO',location:'인천',region:'인천',employment:'정규직',published_at:'2026-10-01'},
 {id:'new',title:'산업간호사',company:'B',source:'ALIO',location:'인천',region:'인천',employment:'정규직',published_at:'2026-10-09'}
], {...state, sort:'recent', region:'인천', employment:'전체', query:'', savedOnly:false}, new Set())`, context);
assert.equal(newest[0].id, 'new', '게시일 최신순');
assert.equal(vm.runInContext('isNew({first_seen:"2026-10-10T10:00:00+09:00"}, Date.parse("2026-10-11T10:00:00+09:00"))', context), true, '최근 3일 처음 수집 NEW');
assert.equal(vm.runInContext('isNew({first_seen:"2026-10-08T10:00:00+09:00"}, Date.parse("2026-10-11T10:00:00+09:00"))', context), false, '3일 경과 NEW 해제');
assert.equal(vm.runInContext('isNew({first_seen:"2099-10-10"}, Date.parse("2026-10-11"))', context), false, '미래 수집일 NEW 제외');
assert.equal(ids.get('stat-saved').textContent, 1, '관심공고 요약');
const byDeadline = vm.runInContext(`filteredJobs([
 {id:'none',title:'A',company:'A',source:'A',location:'서울',deadline:null},
 {id:'later',title:'B',company:'B',source:'A',location:'서울',deadline:'2099-12-31'},
 {id:'sooner',title:'C',company:'C',source:'A',location:'서울',deadline:'2099-11-01'}
], {...state, sort:'deadline', region:'전체', employment:'전체', query:'', savedOnly:false}, new Set())`, context);
assert.equal(byDeadline[0].id, 'sooner', '마감 임박순');
assert.equal(byDeadline[2].id, 'none', '마감일 미기재 마지막');
console.log('NEW 기간·관심 요약·마감순 검증 통과');
