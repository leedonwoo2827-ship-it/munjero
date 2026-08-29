/* 문제로 — 채점기.
   데이터는 window.MUNJERO 에 구워져 있다. 서버도 fetch 도 없다
   (file:// 문서는 origin 이 null 이라 fetch 가 CORS 로 막힌다). */
"use strict";

var D = window.MUNJERO || {items: [], exam_id: "exam"};
var ITEMS = D.items || [];
var CIRC = "①②③④⑤⑥⑦⑧⑨⑩";
var $ = function (s) { return document.querySelector(s); };

var answers = {}, graded = false, filter = "all", revealed = false;
var ANSKEY = "munjero:ans:" + (D.exam_id || "exam");

/* file:// 은 origin 이 null 이라 모든 로컬 HTML 이 저장소를 공유한다.
   exam_id 로 네임스페이스를 나누지 않으면 두 시험의 답안이 섞인다. */
function loadAns() {
  try {
    var o = JSON.parse(localStorage.getItem(ANSKEY) || "null");
    return (o && typeof o === "object" && !Array.isArray(o)) ? o : {};
  } catch (e) { return {}; }
}
function saveAns() {
  try {
    if (Object.keys(answers).length) localStorage.setItem(ANSKEY, JSON.stringify(answers));
    else localStorage.removeItem(ANSKEY);
  } catch (e) {}
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
    return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c];
  });
}

/* 해설은 마크다운으로 온다 — 표·불릿·강조·인라인코드만 다룬다. */
function mdInline(s) {
  s = esc(s);
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  return s;
}
function mdBlocks(src) {
  var L = String(src || "").split("\n"), out = [], i = 0;
  while (i < L.length) {
    var line = L[i];
    if (!line.trim()) { i++; continue; }
    if (/^\s*\|.*\|\s*$/.test(line)) {
      var rows = [];
      while (i < L.length && /^\s*\|.*\|\s*$/.test(L[i])) rows.push(L[i++]);
      out.push(mdTable(rows));
      continue;
    }
    if (/^\s*([-*•]|\d+[.)])\s+/.test(line)) {
      var items = [];
      while (i < L.length && /^\s*([-*•]|\d+[.)])\s+/.test(L[i]))
        items.push(L[i++].replace(/^\s*([-*•]|\d+[.)])\s+/, ""));
      out.push("<ul>" + items.map(function (t) { return "<li>" + mdInline(t) + "</li>"; }).join("") + "</ul>");
      continue;
    }
    var para = [];
    while (i < L.length && L[i].trim() && !/^\s*\|/.test(L[i])
           && !/^\s*([-*•]|\d+[.)])\s+/.test(L[i])) para.push(L[i++]);
    out.push("<p>" + mdInline(para.join(" ")) + "</p>");
  }
  return out.join("");
}
function mdTable(rows) {
  var cells = rows.map(function (r) {
    return r.trim().replace(/^\||\|$/g, "").split("|").map(function (c) { return c.trim(); });
  });
  var head = [];
  if (cells.length > 1 && cells[1].every(function (c) { return /^:?-{2,}:?$/.test(c || "-"); })) {
    head = cells[0]; cells.splice(0, 2);
  }
  return '<div class="q-table-wrap"><table class="q-table">'
    + (head.length ? "<thead><tr>" + head.map(function (c) { return "<th>" + mdInline(c) + "</th>"; }).join("") + "</tr></thead>" : "")
    + "<tbody>" + cells.map(function (r) {
        return "<tr>" + r.map(function (c) { return "<td>" + mdInline(c) + "</td>"; }).join("") + "</tr>";
      }).join("") + "</tbody></table></div>";
}

function tableHtml(t) {
  var cols = t.columns || [], rows = t.rows || [];
  var h = '<div class="q-table-wrap"><table class="q-table">';
  if (cols.length) h += "<thead><tr>" + cols.map(function (c) { return "<th>" + esc(c) + "</th>"; }).join("") + "</tr></thead>";
  h += "<tbody>" + rows.map(function (r) {
    return "<tr>" + r.map(function (c) { return "<td>" + esc(c).replace(/\n/g, "<br>") + "</td>"; }).join("") + "</tr>";
  }).join("") + "</tbody></table></div>";
  return h;
}

function badges(it) {
  var b = [];
  if (it.answer_type === "free") b.push('<span class="q-badge q-badge--free">해설만</span>');
  if (it.needs_review) b.push('<span class="q-badge q-badge--review">확인 필요</span>');
  if (it.confidence === "low") b.push('<span class="q-badge q-badge--low">확신 낮음</span>');
  if (it.answer_index == null && it.answer_type === "single")
    b.push('<span class="q-badge q-badge--none">정답 없음</span>');
  return b.join("");
}

function visible() {
  return ITEMS.filter(function (it) {
    if (filter === "all") return true;
    if (filter === "review") return it.needs_review;
    if (filter === "low") return it.confidence === "low";
    if (filter === "none") return it.answer_index == null && it.answer_type === "single";
    return it.subject === filter;
  });
}

function render() {
  var rows = visible(), h = [];
  rows.forEach(function (it) {
    var sel = answers[it.id];
    h.push('<div class="q-card" data-id="' + esc(it.id) + '" data-number="' + esc(it.number) + '">');
    h.push('<div class="q-head"><span class="q-number">' + esc(it.number) + "번</span>");
    if (it.subject) h.push('<span class="q-pill">' + esc(it.subject) + "</span>");
    h.push(badges(it));
    if (it.source && it.source.page) h.push('<span class="q-src">p.' + it.source.page + "</span>");
    h.push("</div>");
    h.push('<p class="q-stem">' + esc(it.question) + "</p>");
    if (it.passage) h.push('<div class="q-passage">' + esc(it.passage) + "</div>");
    (it.tables || []).forEach(function (t) { h.push(tableHtml(t)); });
    (it.figures || []).forEach(function (f) {
      h.push('<div class="q-figure"><img src="' + esc(f) + '" alt="" loading="lazy"></div>');
    });
    if (it.choices && it.choices.length) {
      h.push('<ol class="q-choices">');
      it.choices.forEach(function (c, i) {
        var cls = "q-choice" + (sel === i ? " q-choice--selected" : "");
        h.push('<li class="' + cls + '" data-i="' + i + '" onclick="pick(this)">'
          + '<span class="q-choice__marker">' + (it.markers && it.markers[i] || CIRC[i]) + "</span>"
          + "<span>" + esc(c) + "</span></li>");
      });
      h.push("</ol>");
    } else if (it.answer_type === "free") {
      h.push('<div class="q-free-note">서술형 문항 — 채점 대상이 아닙니다. 정답과 풀이만 제공됩니다.</div>');
    }
    h.push('<div class="q-explain"></div>');
    h.push("</div>");
  });
  var figs = D.appendix_figures || [];
  if (figs.length && filter === "all") {
    h.push('<div class="q-card"><div class="q-head">'
      + '<span class="q-number">부록</span>'
      + '<span class="q-badge q-badge--free">배치 미확정</span></div>'
      + '<p class="q-stem">원본에 포함된 이미지 ' + figs.length + '개</p>'
      + '<div class="q-free-note">어느 문항에 붙는지 원본 정보만으로 확정할 수 없어'
      + ' 여기에 모아 둡니다. 배치가 정해지면 시험지 HTML의 해당 문항으로 옮기세요.</div>'
      + '<div class="q-appendix">'
      + figs.map(function (f) {
          return '<figure><img src="' + esc(f.src) + '" alt="" loading="lazy">'
            + '<figcaption>' + esc(f.caption || "") + "</figcaption></figure>";
        }).join("")
      + "</div></div>");
  }
  $("#exList").innerHTML = h.join("") ||
    '<div class="q-card">해당하는 문항이 없습니다.</div>';
  if (graded || revealed) applyResults();
  updateScore();
}

function pick(el) {
  if (graded) return;
  var card = el.closest(".q-card");
  var id = card.getAttribute("data-id");
  answers[id] = +el.getAttribute("data-i");
  Array.prototype.forEach.call(card.querySelectorAll(".q-choice"), function (c) {
    c.classList.remove("q-choice--selected");
  });
  el.classList.add("q-choice--selected");
  saveAns();
  updateScore();
}

/* 채점은 전부 이 함수 안에서 끝난다. 정답이 MUNJERO 안에 있기 때문이다.
   나중에 서버 채점이 필요해지면 이 함수만 async 로 바꾸고 fetch 를 넣으면 된다.
   반환 형태 {correct,total,results} 를 유지하면 화면 코드는 한 줄도 안 바뀐다. */
function gradeLocal(showAll) {
  var rows = visible(), results = [], ok = 0, tot = 0;
  rows.forEach(function (it) {
    if (it.answer_type !== "single" || it.answer_index == null) {
      results.push({id: it.id, scored: false, item: it});
      return;
    }
    tot++;
    var chosen = (it.id in answers) ? answers[it.id] : -1;
    var good = chosen === it.answer_index;
    if (good) ok++;
    results.push({id: it.id, scored: true, ok: good, chosen: chosen, item: it});
  });
  return {correct: ok, total: tot, results: results};
}

function applyResults() {
  var r = gradeLocal();
  r.results.forEach(function (res) {
    var card = $('.q-card[data-id="' + cssEsc(res.id) + '"]');
    if (!card) return;
    card.classList.add("is-graded");
    var it = res.item;
    Array.prototype.forEach.call(card.querySelectorAll(".q-choice"), function (el) {
      var i = +el.getAttribute("data-i");
      el.classList.remove("q-choice--selected");
      var chip = el.querySelector(".q-choice__chip");
      if (chip) chip.remove();
      if (it.answer_index === i) {
        el.classList.add("q-choice--correct");
        el.insertAdjacentHTML("beforeend", '<span class="q-choice__chip">정답</span>');
      } else if (res.scored && res.chosen === i) {
        el.classList.add("q-choice--wrong");
        el.insertAdjacentHTML("beforeend", '<span class="q-choice__chip">내가 고른 답</span>');
      }
    });
    var ex = card.querySelector(".q-explain");
    if (ex && it.explanation) {
      var label = it.answer_type === "free" ? "정답 · 풀이"
        : "해설 (정답 " + (CIRC[it.answer_index] || "?") + ")";
      var why = (it.wrong_reasons || []).filter(function (w) { return w && w.trim(); });
      ex.innerHTML = '<span class="q-explain__label">' + label + "</span>"
        + mdBlocks(it.explanation)
        + (why.length ? '<div class="q-why"><ul>' + why.map(function (w) {
            return "<li>" + mdInline(w) + "</li>"; }).join("") + "</ul></div>" : "");
      ex.classList.add("is-open");
    }
  });
  var pct = r.total ? Math.round(r.correct / r.total * 100) : 0;
  $("#scoreNum").textContent = r.correct;
  $("#scoreTot").textContent = r.total;
  $("#scoreK").textContent = "정답률 " + pct + "%";
  drawRing(pct);
}

function cssEsc(s) { return String(s).replace(/["\\]/g, "\\$&"); }

function updateScore() {
  if (graded || revealed) return;
  var rows = visible().filter(function (it) { return it.answer_type === "single"; });
  var n = rows.filter(function (it) { return it.id in answers; }).length;
  $("#scoreNum").textContent = "0";
  $("#scoreTot").textContent = rows.length;
  $("#scoreK").textContent = "입력한 문항 " + n;
  drawRing(rows.length ? Math.round(n / rows.length * 100) : 0, true);
}

function drawRing(pct, pale) {
  var r = 26, c = 2 * Math.PI * r;
  $("#ring").innerHTML =
    '<svg width="64" height="64" viewBox="0 0 64 64">'
    + '<circle cx="32" cy="32" r="' + r + '" fill="none" stroke="var(--soft2)" stroke-width="7"/>'
    + '<circle cx="32" cy="32" r="' + r + '" fill="none" stroke="'
    + (pale ? "var(--brand-300)" : "var(--brand-500)") + '" stroke-width="7"'
    + ' stroke-linecap="round" stroke-dasharray="' + c + '"'
    + ' stroke-dashoffset="' + (c * (1 - pct / 100)) + '"'
    + ' transform="rotate(-90 32 32)"/>'
    + '<text x="32" y="37" text-anchor="middle" font-size="15" font-weight="800"'
    + ' fill="var(--brand-700)">' + pct + "%</text></svg>";
}

function grade() { graded = true; render(); window.scrollTo({top: 0, behavior: "smooth"}); }
function reveal() { revealed = true; graded = true; render(); }
function resetAll() {
  answers = {}; graded = false; revealed = false; saveAns(); render();
}

function buildToolbar() {
  var subs = [], seen = {};
  ITEMS.forEach(function (it) {
    if (it.subject && !seen[it.subject]) { seen[it.subject] = 1; subs.push(it.subject); }
  });
  var nReview = ITEMS.filter(function (i) { return i.needs_review; }).length;
  var nLow = ITEMS.filter(function (i) { return i.confidence === "low"; }).length;
  var nNone = ITEMS.filter(function (i) {
    return i.answer_type === "single" && i.answer_index == null; }).length;

  var b = ['<button data-f="all">전체 ' + ITEMS.length + "</button>"];
  subs.forEach(function (s) { b.push('<button data-f="' + esc(s) + '">' + esc(s) + "</button>"); });
  b.push('<span class="spacer"></span>');
  if (nReview) b.push('<button data-f="review">확인 필요 ' + nReview + "</button>");
  if (nLow) b.push('<button data-f="low">확신 낮음 ' + nLow + "</button>");
  if (nNone) b.push('<button data-f="none">정답 없음 ' + nNone + "</button>");
  $("#exToolbar").innerHTML = b.join("");
  Array.prototype.forEach.call($("#exToolbar").querySelectorAll("button"), function (el) {
    el.onclick = function () {
      filter = el.getAttribute("data-f");
      Array.prototype.forEach.call($("#exToolbar").querySelectorAll("button"), function (x) {
        x.classList.toggle("on", x === el);
      });
      render();
    };
  });
  $("#exToolbar").querySelector("button").classList.add("on");

  var free = ITEMS.filter(function (i) { return i.answer_type === "free"; }).length;
  $("#exSub").textContent = D.exam_title + " · 문항 " + ITEMS.length
    + (free ? " (채점 " + (ITEMS.length - free) + " · 해설만 " + free + ")" : "");
  $("#sideNote").innerHTML =
    "정답과 해설은 <b>AI 가 생성</b>했습니다. 공식 정답표와 대조해 주세요.<br><br>"
    + "확인 필요 " + nReview + "건 · 확신 낮음 " + nLow + "건"
    + (nNone ? " · 정답 없음 " + nNone + "건" : "")
    + "<br><br>키보드: 1~4 보기 선택 · ↑↓ 이동 · Enter 채점";
}

/* 113문항을 마우스로만 도는 건 고문이다. */
var cursor = 0;
document.addEventListener("keydown", function (e) {
  if (/^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
  var cards = document.querySelectorAll(".q-card");
  if (!cards.length) return;
  if (e.key === "Enter") { grade(); return; }
  if (e.key === "ArrowDown") { cursor = Math.min(cursor + 1, cards.length - 1); }
  else if (e.key === "ArrowUp") { cursor = Math.max(cursor - 1, 0); }
  else if (/^[1-9]$/.test(e.key)) {
    var el = cards[cursor].querySelectorAll(".q-choice")[+e.key - 1];
    if (el) pick(el);
    return;
  } else return;
  e.preventDefault();
  cards[cursor].scrollIntoView({block: "center", behavior: "smooth"});
});

answers = loadAns();
buildToolbar();
if (/[?&]review=1/.test(location.search)) revealed = graded = true;
render();
