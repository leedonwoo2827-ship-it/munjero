/* 현황판 — 어느 문항의 무엇이 채워졌나.

   행은 요소 종류, 열은 문항 번호. 빈 칸을 누르면 그걸 고치는 화면으로 간다.
   표 하나로 "몇 번까지 있고 무엇이 비었나" 가 다 보인다. */
"use strict";

var Board = (function () {
  var PER_ROW = 20;              // 한 줄에 스무 칸. 넘으면 다음 블록으로 접는다

  /* 문항 하나에서 각 행의 상태를 읽는다.
     on = 채워짐, na = 이 문항엔 해당 없음, 빈칸 = 비어 있음 */
  var ROWS = [
    {key: "stem", name: "발문", of: function (it) {
      return it.question && it.question.trim() ? "on" : "";
    }},
    {key: "passage", name: "지문", of: function (it) {
      return it.passage && it.passage.trim() ? "on" : "na";
    }},
    {key: "table", name: "표", of: function (it) {
      return (it.tables || []).length ? "on" : "na";
    }},
    {key: "figure", name: "그림", of: function (it) {
      return (it.figures || []).length ? "on" : "na";
    }},
    {key: "choices", name: "보기", of: function (it) {
      if (it.answer_type !== "single") return "na";
      var n = (it.choices || []).length;
      if (!n) return "";
      return n === 4 ? "on" : "warn";
    }},
    {key: "answer", name: "정답", of: function (it) {
      if (it.answer_type !== "single") return "na";
      return it.answer_index != null && it.answer_index >= 0 ? "on" : "";
    }},
    {key: "explain", name: "해설", of: function (it) {
      return it.explanation && it.explanation.trim() ? "on" : "";
    }},
  ];

  function stats(items) {
    var filled = 0, total = 0, blank = 0;
    items.forEach(function (it) {
      ROWS.forEach(function (r) {
        var v = r.of(it);
        if (v === "na") return;
        total++;
        if (v === "on") filled++;
        else blank++;
      });
    });
    return {filled: filled, total: total, blank: blank};
  }

  function gridHtml(items, only) {
    var rows = only ? ROWS.filter(function (r) { return only.indexOf(r.key) >= 0; }) : ROWS;
    var blocks = [];
    for (var s = 0; s < items.length; s += PER_ROW) {
      var slice = items.slice(s, s + PER_ROW);
      var h = ['<div class="grid-blk"><table class="grid"><thead><tr><th class="rh"></th>'];
      slice.forEach(function (it) {
        h.push('<th class="h">' + esc(it.number) + "</th>");
      });
      h.push("</tr></thead><tbody>");
      rows.forEach(function (r) {
        var n = items.filter(function (it) { return r.of(it) === "on"; }).length;
        var d = items.filter(function (it) { return r.of(it) !== "na"; }).length;
        h.push('<tr><th class="rh">' + esc(r.name)
          + "<span>" + n + "/" + d + "</span></th>");
        slice.forEach(function (it) {
          var v = r.of(it);
          var cls = "cell" + (v ? " " + v : "");
          var t = v === "na" ? "" : (v === "on" ? "✓" : (v === "warn" ? "!" : ""));
          h.push("<td>" + (v === "na"
            ? '<span class="' + cls + '"></span>'
            : '<button class="' + cls + '" data-q="' + esc(it.id) + '" title="#'
              + esc(it.number) + " " + esc(r.name) + '">' + t + "</button>") + "</td>");
        });
        h.push("</tr>");
      });
      h.push("</tbody></table></div>");
      blocks.push(h.join(""));
    }
    return blocks.join("");
  }

  /* 현황판을 플로팅으로 띄운다 */
  function show(opt) {
    var items = State.items || [];
    if (!items.length) {
      toast("먼저 시험지를 넣어 주세요");
      return;
    }
    var st = stats(items);
    var s = State.summary || {};
    var free = items.filter(function (i) { return i.answer_type === "free"; }).length;
    var need = items.filter(function (i) { return i.needs_review; }).length;

    Panel.open({
      title: "현황판",
      sub: "어느 문항의 무엇이 채워졌나. 빈 칸을 누르면 그걸 고치는 화면으로 갑니다",
      body:
        '<div class="board-sum">'
        + "<b>" + items.length + "</b>문항 (" + numRange(items) + ")"
        + " &middot; 채움 <b>" + st.filled + "/" + st.total + "</b>"
        + " &middot; 남은 칸 <b>" + st.blank + "</b>개"
        + (free ? " &middot; 해설만 " + free : "")
        + (need ? ' &middot; <b style="color:var(--warn)">확인 필요 ' + need + "</b>" : "")
        + "</div>"
        + '<div class="board-filters">'
        + '<button class="pill on" data-only="">전체</button>'
        + '<button class="pill" data-only="stem,passage,table,figure">문제 재료</button>'
        + '<button class="pill" data-only="choices">보기</button>'
        + '<button class="pill" data-only="answer,explain">정답 · 해설</button>'
        + "</div>"
        + '<div id="gridWrap">' + gridHtml(items) + "</div>",
      foot:
        '<span style="font-size:12.5px;color:var(--text-2)">'
        + (s.confirmed ? "시험지 확정됨" : "시험지 확정 전입니다") + "</span>"
        + '<span class="spacer"></span>'
        + (s.confirmed ? "" : '<button class="btn btn--go" id="bdConfirm">시험지 확정</button>')
        + '<button class="btn" data-x>닫기</button>',
      after: function (l) {
        $$("[data-x]", l).forEach(function (b) { b.onclick = Panel.close; });
        $$("[data-only]", l).forEach(function (b) {
          b.onclick = function () {
            $$("[data-only]", l).forEach(function (x) { x.classList.remove("on"); });
            b.classList.add("on");
            var v = b.getAttribute("data-only");
            $("#gridWrap", l).innerHTML = gridHtml(items, v ? v.split(",") : null);
            wireCells(l);
          };
        });
        var c = $("#bdConfirm", l);
        if (c) c.onclick = function () { Panel.close(); Shell.confirmItems(); };
        wireCells(l);
      },
    });
  }

  function wireCells(l) {
    $$(".cell[data-q]", l).forEach(function (b) {
      b.onclick = function () {
        Panel.close();
        Shell.jumpTo(b.getAttribute("data-q"));
      };
    });
  }

  return {show: show, stats: stats, rows: ROWS};
})();
