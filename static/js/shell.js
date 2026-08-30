/* 껍데기 — 레일 · 화면 전환 · 편집 동작. */
"use strict";

/* ── 문항 편집 ───────────────────────────────────────────────────── */
var Edit = (function () {
  function mark(i) { State.dirty[State.items[i].id] = true; }
  function draw() { Shell.paintItems(); }

  return {
    figUrl: function (src) {
      if (/^(data:|https?:)/.test(src)) return src;
      return "/api/exam/" + encodeURIComponent(State.exam) + "/paper/"
        + src.replace(/^\.?\//, "");
    },
    f: function (i, k, v) {
      var it = State.items[i];
      if ((it[k] || "") === v) return;
      it[k] = v; mark(i); Shell.syncRail();
    },
    choice: function (i, ci, v) {
      if (State.items[i].choices[ci] === v) return;
      State.items[i].choices[ci] = v; mark(i);
    },
    cell: function (i, ti, r, c, v) {
      var cells = State.items[i].tables[ti].cells;
      for (var k = 0; k < cells.length; k++) {
        if (cells[k].r === r && cells[k].c === c) { cells[k].t = v; break; }
      }
      mark(i);
    },
    /* 차변/대변이 통째로 뒤집혀 들어온 표를 한 번에 고친다 */
    swap: function (i, ti) {
      var t = State.items[i].tables[ti];
      var half = Math.floor((t.cols || 0) / 2);
      if (!half) { toast("열이 홀수라 좌우로 나눌 수 없습니다"); return; }
      t.cells.forEach(function (c) { c.c = c.c < half ? c.c + half : c.c - half; });
      mark(i); draw(); toast("좌변과 우변을 바꿨습니다");
    },
    dropTable: async function (i, ti) {
      if (!await Panel.confirm({title: "이 표를 지울까요?", ok: "지우기", danger: true,
        sub: "되돌리려면 시험지에서 다시 읽어야 합니다."})) return;
      State.items[i].tables.splice(ti, 1); mark(i); draw();
    },
    /* 보기 칸 수를 맞춘다. 적힌 것은 그대로 두고 칸만 늘고 준다 —
       O/X 도 있고 다섯 개짜리도 있어서 시험마다 다르다. */
    nch: function (i, k) {
      var it = State.items[i];
      var cs = it.choices || [];
      if (k === "OX") {
        it.markers = ["O", "X"];
        it.choices = [cs[0] || "O", cs[1] || "X"];
      } else {
        var n = +k;
        if (!(n > 0)) return;
        it.markers = null;
        var out = [];
        for (var c = 0; c < n; c++) out.push(cs[c] == null ? "" : cs[c]);
        it.choices = out;
      }
      it.answer_type = "single";
      mark(i); draw();
    },
    /* ── 자산 : 표 · 코드 · 텍스트 · 수식 · 그림 ───────────────── */
    addAsset: function (i, kind) {
      var it = State.items[i];
      var as = it.assets = it.assets || [];
      var pre = {table: "t", code: "b", math: "x", text: "s", figure: "g"}[kind];
      var n = 0;
      as.forEach(function (a) {
        var m = /^([a-z])-(\d+)$/.exec(a.token || "");
        if (m && m[1] === pre) n = Math.max(n, +m[2]);
      });
      var a = {token: pre + "-" + (n + 1), kind: kind};
      if (kind === "figure") {
        Edit.pickImage(function (src) {
          a.src = src; as.push(a); Edit.putTokenTo(it, a.token);
          mark(i); draw();
        });
        return;
      }
      a[kind === "table" ? "md" : "text"] =
        kind === "table" ? "| 항목 | 값 |\n| --- | --- |\n|  |  |" : "";
      as.push(a);
      Edit.putTokenTo(it, a.token);
      mark(i); draw();
    },
    asset: function (i, ai, k, v) {
      var a = (State.items[i].assets || [])[ai];
      if (!a || a[k] === v) return;
      a[k] = v; mark(i);
    },
    dropAsset: async function (i, ai) {
      var it = State.items[i], a = (it.assets || [])[ai];
      if (!a) return;
      if (!await Panel.confirm({title: "{{" + a.token + "}} 를 지울까요?",
        ok: "지우기", danger: true,
        sub: "본문에 적어 둔 토큰도 함께 지웁니다."})) return;
      var re = new RegExp("\\{\\{\\s*" + a.token + "\\s*\\}\\}", "g");
      ["question", "passage", "explanation"].forEach(function (f) {
        if (it[f]) it[f] = it[f].replace(re, "").replace(/\n{3,}/g, "\n\n").trim();
      });
      it.assets.splice(ai, 1);
      mark(i); draw();
    },
    putToken: function (i, ai) {
      var it = State.items[i], a = (it.assets || [])[ai];
      if (!a) return;
      Edit.putTokenTo(it, a.token, true);
      mark(i); draw(); toast("{{" + a.token + "}} 를 지문 끝에 넣었습니다");
    },
    /* 토큰이 본문 어디에도 없으면 지문 끝에 붙인다. 안 붙이면 자산을
       만들어 놓고도 어디에도 안 나와서 사라진 것처럼 보인다. */
    putTokenTo: function (it, tok, force) {
      var t = "{{" + tok + "}}";
      var has = [it.question, it.passage, it.explanation].some(function (s) {
        return (s || "").indexOf(t) >= 0;
      });
      if (has && !force) return;
      it.passage = ((it.passage || "") + "\n" + t).trim();
    },
    pickImage: function (cb) {
      var inp = document.createElement("input");
      inp.type = "file";
      inp.accept = "image/*";
      inp.onchange = function () {
        var f = inp.files && inp.files[0];
        if (!f) return;
        if (f.size > 3 * 1024 * 1024) { toast("3MB 보다 작은 그림을 써 주세요"); return; }
        var r = new FileReader();
        r.onload = function () { cb(String(r.result)); };
        r.readAsDataURL(f);
      };
      inp.click();
    },
    toggleType: function (i) {
      var it = State.items[i];
      it.answer_type = it.answer_type === "single" ? "free" : "single";
      mark(i); draw();
    },
    resolve: function (i) {
      var it = State.items[i];
      it.needs_review = false; it.warnings = []; it._resolved = true;
      mark(i); draw(); Shell.syncRail();
    },
    drop: async function (i) {
      if (!await Panel.confirm({title: "#" + State.items[i].number + " 문항을 지울까요?",
        ok: "지우기", danger: true})) return;
      State.items.splice(i, 1); draw(); Shell.syncRail();
    },
    /* 한 문항이 둘로 쪼개져 들어온 경우 — 아래 것을 위에 붙인다 */
    sharedPassage: function (v) {
      var g = Shell.currentGroup();
      g.forEach(function (it) {
        if ((it.passage || "") !== v) {
          it.passage = v;
          State.dirty[it.id] = true;
        }
      });
      Shell.syncRail();
    },
    mergeUp: function (i) {
      if (i === 0) return;
      var a = State.items[i - 1], b = State.items[i];
      a.passage = [a.passage, b.question, b.passage].filter(Boolean).join("\n");
      if ((b.choices || []).length && !(a.choices || []).length) {
        a.choices = b.choices; a.markers = b.markers; a.answer_type = b.answer_type;
      }
      (b.tables || []).forEach(function (t) { (a.tables = a.tables || []).push(t); });
      (b.figures || []).forEach(function (f) { (a.figures = a.figures || []).push(f); });
      mark(i - 1);
      State.items.splice(i, 1);
      draw(); Shell.syncRail(); toast("위 문항에 이어붙였습니다");
    },
  };
})();

/* ── 해설 편집 ───────────────────────────────────────────────────── */
var Ans = (function () {
  function mark(i) { State.ansDirty[State.ansRows[i].id] = true; }
  function one(i) {
    var el = document.getElementById("ai-" + State.ansRows[i].id);
    if (el) el.outerHTML = Views.ansItem(State.ansRows[i], i);
  }
  return {
    pick: function (i, ci) { State.ansRows[i].answer_index = ci; mark(i); one(i); },
    set: function (i, k, v) {
      if ((State.ansRows[i][k] || "") === v) return;
      State.ansRows[i][k] = v; mark(i);
    },
    dropSvg: function (i) {
      State.ansRows[i].diagram_svg = null;
      State.ansRows[i]._dropSvg = true;
      mark(i); one(i);
    },
  };
})();

/* ── 껍데기 ──────────────────────────────────────────────────────── */
var Shell = (function () {
  var timer = null, clock = null, startedAt = 0, built = null;

  function paint(html) {
    $("#view").innerHTML = html;
    window.scrollTo({top: 0});
  }

  /* ── 레일 ── */
  function navActive(v) {
    $$(".nav a").forEach(function (a) {
      a.classList.toggle("active", a.getAttribute("data-go") === v);
      var locked = !State.exam && a.getAttribute("data-go") !== "start";
      a.classList.toggle("locked", locked);
    });
  }

  function syncRail() {
    var it = State.items || [], s = State.summary || {};
    var need = it.filter(function (i) { return i.needs_review; }).length;
    var cnt = function (f) { return it.filter(f).length; };
    $("#subnav").innerHTML = it.length ? [
      ["발문", cnt(function (i) { return i.question; }), it.length, ""],
      ["지문", cnt(function (i) { return i.passage; }), 0, ""],
      ["표", cnt(function (i) { return (i.tables || []).length; }), 0, ""],
      ["그림", cnt(function (i) { return (i.figures || []).length; }), 0, ""],
      ["보기 4개", cnt(function (i) {
        return i.answer_type === "single" && (i.choices || []).length === 4;
      }), cnt(function (i) { return i.answer_type === "single"; }), ""],
      ["확인 필요", need, 0, need ? "warn" : "ok"],
    ].map(function (r) {
      return '<li class="' + r[3] + '"><b>' + r[0] + "</b>"
        + '<span class="c">' + r[1] + (r[2] ? " / " + r[2] : "") + "</span></li>";
    }).join("") : '<li><b>아직 없습니다</b></li>';

    if (typeof refreshSide === "function") { /* 우측 서랍도 함께 갱신된다 */ }
    $("#curBadge").textContent = it.length ? String(it.length) : "—";
    $("#curName").textContent = s.title || "고르지 않음";
    $("#curMeta").textContent = it.length
      ? (numRange(it) + " · " + (s.confirmed ? "확정됨" : "확정 전"))
      : "시험지를 넣어 주세요";
  }

  async function loadRecent() {
    var d = await api("/exams?limit=8");
    $("#recent").innerHTML = d.exams.length ? d.exams.map(function (e) {
      return '<div class="r' + (e.exam_id === State.exam ? " active" : "")
        + '" data-go="' + esc(e.exam_id) + '">'
        + '<span class="t"><b>' + esc(e.title) + "</b><em>" + e.items + "개 문항"
        + (e.has_grader ? " · 완료" : (e.answers ? " · 해설 있음"
            : (e.confirmed ? " · 확정됨" : ""))) + "</em></span>"
        + '<button class="x" data-del="' + esc(e.exam_id) + '" title="지우기">&times;</button>'
        + "</div>";
    }).join("") : '<div class="side-empty">아직 없습니다.</div>';

    $$("#recent .r").forEach(function (r) {
      r.onclick = function (e) {
        if (e.target.hasAttribute("data-del")) return;
        open(r.getAttribute("data-go"));
      };
    });
    $$("#recent [data-del]").forEach(function (b) {
      b.onclick = async function (e) {
        e.stopPropagation();
        var id = b.getAttribute("data-del");
        if (!await Panel.confirm({title: "이 시험지를 지울까요?", ok: "지우기", danger: true,
          sub: id, body: '<div class="note note--bad">폴더째 사라집니다. '
            + "만들어 둔 채점기와 해설도 함께 지워집니다.</div>"})) return;
        await api("/exam/" + encodeURIComponent(id), {method: "DELETE"});
        if (State.exam === id) { State.exam = null; State.items = []; State.summary = {}; }
        toast("지웠습니다");
        loadRecent(); tabs();
        if (!State.exam) goto("start");
      };
    });
  }

  async function tabs() {
    var d = await api("/exams?limit=20");
    $("#tabs").innerHTML = d.exams.map(function (e) {
      return '<button data-go="' + esc(e.exam_id) + '"'
        + (e.exam_id === State.exam ? ' class="on"' : "") + ">"
        + esc(e.title) + "</button>";
    }).join("");
    $$("#tabs button").forEach(function (b) {
      b.onclick = function () { open(b.getAttribute("data-go")); };
    });
  }

  /* ── 화면 ── */
  async function goto(v) {
    State.view = v;
    navActive(v);
    if (v === "start") { paint(Views.start()); wireDrop(); return; }
    if (!State.exam) { toast("먼저 시험지를 넣어 주세요"); return goto("start"); }
    if (v === "board") { Board.show(); return; }
    if (v === "toc") return showToc();
    if (v === "map") return showMap();
    if (v === "answer") return showAnswer();
    if (v === "export") return showExport();
    if (v === "report") return showReport();
  }

  function wireDrop() {
    var drop = $("#drop"), input = $("#file");
    if (!drop) return;
    ["dragenter", "dragover"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); });
    });
    drop.addEventListener("drop", function (e) {
      if (e.dataTransfer.files.length) upload(e.dataTransfer.files[0]);
    });
    input.addEventListener("change", function () {
      if (input.files.length) upload(input.files[0]);
    });
  }

  async function upload(f) {
    $("#upBusy").classList.remove("hide");
    try {
      var fd = new FormData();
      fd.append("file", f);
      var e = await api("/upload", {method: "POST", body: fd});
      toast("문항 " + e.items + "개를 읽어냈습니다");
      await open(e.exam_id);
      Board.show();                     // 읽어내면 바로 문항표를 보여 준다
    } catch (err) {
      Panel.open({title: "읽어내지 못했습니다", narrow: true,
        body: '<div class="note note--bad">' + esc(err.message) + "</div>"
          + '<div class="sub">시험지 HTML 로 저장해서 다시 넣어 보세요.</div>',
        foot: '<span class="spacer"></span><button class="btn" data-x>닫기</button>',
        after: function (l) { $$("[data-x]", l).forEach(function (b) { b.onclick = Panel.close; }); }});
    } finally {
      var b = $("#upBusy"); if (b) b.classList.add("hide");
    }
  }

  async function open(id) {
    State.exam = id; State.dirty = {}; reportInfo = null;
    State.paperText = null;               // 시험이 바뀌면 원문도 바뀐다
    var d = await api("/exam/" + encodeURIComponent(id) + "/items");
    State.items = d.items;
    State.summary = await api("/exam/" + encodeURIComponent(id));
    State.summary.confirmed = d.confirmed;
    syncRail(); loadRecent(); tabs();
    await goto("map");
  }

  /* ── 문항: 한 문항씩 확인 ── */
  var cursor = 0;

  /* 지문을 나눠 쓰는 문항들은 한 화면에 함께 본다.
     그러지 않으면 지문 없이 발문만 보게 되어 판단할 수가 없다. */
  function groups() {
    var out = [], seen = {};
    State.items.forEach(function (it) {
      var k = it.stimulus;
      if (k) {
        if (seen[k] != null) { out[seen[k]].push(it); return; }
        seen[k] = out.length;
      }
      out.push([it]);
    });
    return out;
  }

  function showToc() {
    var gs = groups();
    paint(Views.toc(gs, cursor));
    $$(".toc-row[data-k]").forEach(function (r) {
      r.onclick = function () { cursor = +r.getAttribute("data-k"); goto("map"); };
    });
    $("#tocBoard").onclick = function () { Board.show(); };
    $("#tocGo").onclick = function () { goto("map"); };
  }

  function showMap() {
    paint(Views.map({items: State.items, confirmed: State.summary.confirmed}));
    $("#btnBoard").onclick = function () { Board.show(); };
    $("#btnSave").onclick = function () { saveItems(); };
    $("#btnConfirm").onclick = confirmItems;
    $("#btnRemap").onclick = async function () {
      if (!await Panel.confirm({title: "시험지에서 다시 읽을까요?", ok: "다시 읽기",
        narrow: true, sub: "화면에서 고친 내용은 사라집니다."})) return;
      await api("/exam/" + encodeURIComponent(State.exam) + "/remap", {method: "POST"});
      await open(State.exam);
      toast("다시 읽었습니다");
    };

    if (State.jumpId) {
      var gs = groups();
      for (var k = 0; k < gs.length; k++) {
        if (gs[k].some(function (x) { return x.id === State.jumpId; })) { cursor = k; break; }
      }
      State.jumpId = null;
    }
    paintItems();
  }

  function paintItems() {
    var el = $("#rev");
    if (!el) return;
    var gs = groups();
    if (!gs.length) { el.innerHTML = '<div class="empty">문항이 없습니다.</div>'; return; }
    cursor = Math.max(0, Math.min(cursor, gs.length - 1));
    var done = gs.filter(function (g) {
      return g.every(function (x) { return x.reviewed; });
    }).length;

    var strip = gs.map(function (g, k) {
      var cls = k === cursor ? "on"
        : (g.some(function (x) { return x.needs_review; }) ? "flag"
          : (g.every(function (x) { return x.reviewed; }) ? "done" : ""));
      return '<button class="' + cls + '" data-k="' + k + '">'
        + esc(g[0].number) + (g.length > 1 ? "+" : "") + "</button>";
    }).join("");

    el.innerHTML = Views.review(gs[cursor], cursor + 1, gs.length, done, strip);

    $$("#rev .rev-strip button").forEach(function (b) {
      b.onclick = function () { cursor = +b.getAttribute("data-k"); paintItems(); };
    });
    var st = $("#srcToggle");
    if (st) st.onclick = function () { State.srcOpen = !openSrc(); paintItems(); };
    var sx = $("#srcClose");
    if (sx) sx.onclick = function () { State.srcOpen = false; paintItems(); };
    $$("#rev .src-tab button").forEach(function (b) {
      b.onclick = function () {
        State.srcMode = b.getAttribute("data-src");
        paintItems();
      };
    });
    if (openSrc() && (State.srcMode || "text") === "text") loadPaperText();

    $("#revPrev").onclick = function () { move(-1); };
    $("#revNext").onclick = function () { move(1); };
    $("#revSkip").onclick = function () { move(1); };
    $("#revOk").onclick = function () {
      gs[cursor].forEach(function (x) {
        x.reviewed = true;
        x.needs_review = false;
        x.warnings = [];
        State.dirty[x.id] = true;
        x._resolved = true;
      });
      syncRail();
      move(1);
    };
  }

  function openSrc() { return State.srcOpen !== false; }

  /* 원문은 한 번만 읽어 온다. 문항을 넘길 때마다 다시 받으면 느리다. */
  var paperPending = false;
  async function loadPaperText() {
    if (State.paperText != null || paperPending) return;
    paperPending = true;
    try {
      var r = await api("/exam/" + encodeURIComponent(State.exam) + "/paper/text");
      State.paperText = r.text || "(원문이 비어 있습니다)";
    } catch (e) {
      State.paperText = "원문을 읽지 못했습니다 — " + e.message;
    }
    paperPending = false;
    if (State.view === "map") paintItems();
  }

  function move(d) {
    var n = groups().length;
    var next = cursor + d;
    if (next < 0) { toast("첫 문항입니다"); return; }
    if (next >= n) {
      cursor = n - 1;
      paintItems();
      toast("마지막 문항입니다. 이제 확정할 수 있습니다");
      return;
    }
    cursor = next;
    paintItems();
    window.scrollTo({top: 0, behavior: "smooth"});
  }

  function currentGroup() {
    var gs = groups();
    return gs[Math.max(0, Math.min(cursor, gs.length - 1))] || [];
  }

  /* 키보드로 넘긴다 — 수십 문항을 마우스로만 도는 건 고문이다 */
  document.addEventListener("keydown", function (e) {
    if (State.view !== "map") return;
    if (/^(INPUT|TEXTAREA)$/.test(e.target.tagName) || e.target.isContentEditable) return;
    if (!$("#rev")) return;
    if (e.key === "ArrowLeft") { move(-1); e.preventDefault(); }
    else if (e.key === "ArrowRight") { move(1); e.preventDefault(); }
    else if (e.key === "Enter") { var b = $("#revOk"); if (b) b.click(); e.preventDefault(); }
  });

  async function saveItems() {
    var patches = State.items.filter(function (it) { return State.dirty[it.id]; })
      .map(function (it) {
        return {id: it.id, number: String(it.number), question: it.question,
                passage: it.passage || "", choices: it.choices || [],
                answer_type: it.answer_type, resolved: !!it._resolved,
                explanation: it.explanation || "", assets: it.assets || []};
      });
    if (!patches.length) { toast("고친 내용이 없습니다"); return null; }
    var r = await jpost("/exam/" + encodeURIComponent(State.exam) + "/items", patches);
    State.dirty = {};
    State.summary = await api("/exam/" + encodeURIComponent(State.exam));
    toast(r.changed + "문항을 저장했습니다");
    paintItems(); syncRail();
    return r;
  }

  async function confirmItems() {
    if (Object.keys(State.dirty).length) await saveItems();
    var need = State.items.filter(function (i) { return i.needs_review; }).length;
    var st = Board.stats(State.items);
    var ok = await Panel.confirm({
      title: "이 문항표로 확정할까요?", narrow: true,
      sub: "확정한 내용 그대로 정답과 해설을 만듭니다.",
      ok: "확정하고 정답 요청으로",
      body: '<div class="kv">'
        + '<div class="r"><span class="k">문항</span><span class="v">'
        + numRange(State.items) + " · 모두 " + State.items.length + "개</span></div>"
        + '<div class="r"><span class="k">빈 칸</span><span class="v">'
        + st.blank + "개</span></div>"
        + '<div class="r"><span class="k">확인 필요</span><span class="v">'
        + (need ? need + "문항" : "없음") + "</span></div></div>"
        + (need ? '<div class="note note--warn">아직 확인 필요가 ' + need
            + "문항 남아 있습니다. 그대로 진행해도 되지만, 자리가 틀렸다면 "
            + "만든 해설이 버려집니다.</div>"
            : '<div class="note note--info">정답과 해설은 100문항에 '
            + "10~15분쯤 걸립니다.</div>"),
    });
    if (!ok) return;
    await api("/exam/" + encodeURIComponent(State.exam) + "/confirm", {method: "POST"});
    State.summary.confirmed = true;
    syncRail();
    toast("확정했습니다");
    goto("answer");
  }

  /* ── 정답 · 해설 ── */
  async function showAnswer() {
    var d = null;
    try { d = await api("/exam/" + encodeURIComponent(State.exam) + "/answers"); }
    catch (e) { d = null; }
    State.ansRows = (d && d.rows) || [];
    State.ansDirty = {};
    paint(Views.answer(d, State.summary.confirmed));
    if (!State.summary.confirmed) return;

    $("#btnAnswer").onclick = function () { runAnswer(false); };
    $("#btnAnswerForce").onclick = async function () {
      if (await Panel.confirm({title: "전부 다시 쓸까요?", ok: "다시 쓰기", narrow: true,
        sub: "사람이 고친 해설은 그대로 둡니다."})) runAnswer(true);
    };
    var s = $("#btnAnsSave"); if (s) s.onclick = saveAnswers;
    var c = $("#btnAnsConfirm"); if (c) c.onclick = confirmAnswers;
    poll();                                   // 이미 돌고 있으면 이어서 보여 준다
  }

  async function runAnswer(force) {
    $("#btnAnswer").disabled = $("#btnAnswerForce").disabled = true;
    $("#runLog").classList.remove("hide");
    try {
      await api("/exam/" + encodeURIComponent(State.exam) + "/answer"
        + (force ? "?force=true" : ""), {method: "POST"});
      startedAt = Date.now();
      poll();
    } catch (e) {
      $("#btnAnswer").disabled = $("#btnAnswerForce").disabled = false;
      Panel.open({title: "시작하지 못했습니다", narrow: true,
        body: '<div class="note note--bad">' + esc(e.message) + "</div>",
        foot: '<span class="spacer"></span><button class="btn" data-x>닫기</button>',
        after: function (l) { $$("[data-x]", l).forEach(function (b) { b.onclick = Panel.close; }); }});
    }
  }

  function mmss(ms) {
    var s = Math.max(0, Math.floor(ms / 1000));
    return Math.floor(s / 60) + "분 " + ("0" + (s % 60)).slice(-2) + "초";
  }

  /* 시계는 화면에서 매초 돈다. 서버 응답을 기다리는 동안 멈춰 보이면
     사람은 프로그램이 죽은 줄 안다. */
  function startClock(job) {
    stopClock();
    var c = $("#clock");
    if (c) c.classList.add("on");
    tick(job);
    clock = setInterval(function () { tick(job); }, 1000);
  }

  function tick(job) {
    var t = $("#clockT");
    if (!t) return stopClock();
    var el = Math.max(0, Date.now() - startedAt);
    t.textContent = mmss(el);
    var n = $("#clockN");
    if (n) n.innerHTML = "<b>" + job.done + "</b> / " + job.total + " 문항";
    var per = job.done > 0 ? el / job.done : 0;
    var left = per && job.total > job.done ? per * (job.total - job.done) : 0;
    var l = $("#clockL");
    if (l) l.textContent = left ? "남은 예상 " + mmss(left) : "시작하는 중…";
    var s = $("#ansSum");
    if (s) s.textContent = "쓰는 중";
  }

  function stopClock() {
    if (clock) clearInterval(clock);
    clock = null;
    var c = $("#clock");
    if (c) c.classList.remove("on");
  }

  async function poll() {
    if (timer) clearTimeout(timer);
    var j;
    try { j = await api("/exam/" + encodeURIComponent(State.exam) + "/answer/progress"); }
    catch (e) { return; }

    if (j.running) {
      if (!startedAt) startedAt = Date.now() - (j.started ? 0 : 0);
      $("#btnAnswer").disabled = $("#btnAnswerForce").disabled = true;
      var p = $("#ansProg");
      if (p && j.total) p.style.width = Math.round(j.done / j.total * 100) + "%";
      var lg = $("#runLog");
      if (lg) {
        lg.classList.remove("hide");
        lg.textContent = (j.log || []).join("\n");
        lg.scrollTop = lg.scrollHeight;
      }
      startClock(j);
      timer = setTimeout(poll, 2000);
      return;
    }

    stopClock();
    if ($("#btnAnswer")) $("#btnAnswer").disabled = $("#btnAnswerForce").disabled = false;
    if (j.error) {
      Panel.open({title: "쓰지 못했습니다", narrow: true,
        body: '<div class="note note--bad">' + esc(j.error).replace(/\n/g, "<br>") + "</div>",
        foot: '<span class="spacer"></span><button class="btn" data-x>닫기</button>',
        after: function (l) { $$("[data-x]", l).forEach(function (b) { b.onclick = Panel.close; }); }});
      return;
    }
    if (startedAt) {                       // 방금 끝났으면 다시 그린다
      startedAt = 0;
      await showAnswer();
      toast("해설 초안이 나왔습니다. 읽어보고 확정해 주세요");
    }
  }

  async function saveAnswers() {
    var patches = State.ansRows.filter(function (r) { return State.ansDirty[r.id]; })
      .map(function (r) {
        return {id: r.id, answer_index: r.answer_index, explanation: r.explanation,
                wrong_reasons: r.wrong_reasons, drop_diagram: !!r._dropSvg};
      });
    if (!patches.length) { toast("고친 해설이 없습니다"); return; }
    var r = await jpost("/exam/" + encodeURIComponent(State.exam) + "/answers", patches);
    State.ansDirty = {};
    toast(r.changed + "개를 저장했습니다");
  }

  async function confirmAnswers() {
    if (Object.keys(State.ansDirty).length) await saveAnswers();
    var low = State.ansRows.filter(function (r) { return r.confidence === "low"; }).length;
    var ok = await Panel.confirm({
      title: "해설을 확정할까요?", narrow: true, ok: "확정하고 내보내기",
      sub: "확정한 해설로 채점기를 만듭니다.",
      body: '<div class="kv">'
        + '<div class="r"><span class="k">문항</span><span class="v">'
        + State.ansRows.length + "개</span></div>"
        + '<div class="r"><span class="k">확신 낮음</span><span class="v">'
        + (low ? low + "문항" : "없음") + "</span></div></div>"
        + '<div class="note note--warn">정답은 AI 가 만든 것입니다. '
        + "<b>공식 정답표와 대조</b>해 주세요.</div>",
    });
    if (!ok) return;
    await api("/exam/" + encodeURIComponent(State.exam) + "/answers/confirm", {method: "POST"});
    await doBuild();
    goto("export");
  }

  /* ── 내보내기 ── */
  async function doBuild() {
    built = await api("/exam/" + encodeURIComponent(State.exam) + "/build", {method: "POST"});
    State.summary = built;
    toast("채점기를 만들었습니다");
    return built;
  }

  async function showExport() {
    var s = State.summary || {};
    paint(Views.exportView(s, s.has_grader ? (built || s) : null));
    var b = $("#btnBuild");
    if (b) b.onclick = async function () { await doBuild(); showExport(); };
    var o = $("#btnOpenGrader");
    if (o) o.onclick = function () {
      window.open("/api/exam/" + encodeURIComponent(State.exam) + "/grader", "_blank");
    };
    var d = $("#btnDownload");
    if (d) d.onclick = function () {
      window.location = "/api/exam/" + encodeURIComponent(State.exam) + "/grader?download=true";
    };
    var f = $("#btnFolder");
    if (f) f.onclick = function () {
      api("/exam/" + encodeURIComponent(State.exam) + "/open-folder", {method: "POST"});
    };
    var tr = $("#btnToReport");
    if (tr) tr.onclick = function () { goto("report"); };
  }

  /* ── 출제의 맥 ── */
  var reportInfo = null;

  async function showReport() {
    var s = State.summary || {};
    paint(Views.report(s, reportInfo));
    var b = $("#btnReport");
    if (b) b.onclick = async function () {
      b.disabled = true;
      b.textContent = "만드는 중…";
      try {
        reportInfo = await api("/exam/" + encodeURIComponent(State.exam) + "/report",
                               {method: "POST"});
        showReport();
        toast("개념 " + reportInfo.concepts + "개를 모았습니다");
      } catch (e) {
        b.disabled = false;
        toast(e.message);
      }
    };
    var o = $("#btnReportOpen");
    if (o) o.onclick = function () {
      window.open("/api/exam/" + encodeURIComponent(State.exam) + "/report", "_blank");
    };
    var c = $("#btnReportCsv");
    if (c) c.onclick = function () {
      window.location = "/api/exam/" + encodeURIComponent(State.exam)
        + "/report?kind=csv";
    };
    var f = $("#btnReportFolder");
    if (f) f.onclick = function () {
      api("/exam/" + encodeURIComponent(State.exam) + "/open-folder", {method: "POST"});
    };
  }

  /* ── 워크스페이스 ── */
  async function workspace() {
    var st = await api("/settings");
    var h = await api("/health");
    var d = await api("/exams");
    Panel.open({
      title: "워크스페이스", sub: "저장 폴더 · 연결 · 시험지",
      body: '<div class="sec-h">저장 폴더</div>'
        + '<div class="kv">'
        + '<div class="r"><span class="k">앱</span><span class="v mono">'
        + esc(st.repo) + "</span></div>"
        + '<div class="r"><span class="k">산출물</span><span class="v mono">'
        + esc(st.out_root) + "</span></div>"
        + '<div class="r"><span class="k">지정 방식</span><span class="v">'
        + (st.env_locked ? "환경변수 MUNJERO_OUT"
            : (st.out_root === st["default"] ? "기본값" : "화면에서 지정")) + "</span></div>"
        + '<div class="r"><span class="k">시험지</span><span class="v">'
        + d.total + "개</span></div></div>"
        + '<div class="sec-h">연결</div>'
        + '<div class="kv">'
        + '<div class="r"><span class="k">상태</span><span class="v" id="wsState">'
        + (h.ok ? '<span class="badge-ok">Codex 연결됨</span>'
                : '<span class="badge-bad">로그인 필요</span>') + "</span></div>"
        + '<div class="r"><span class="k">CLI</span><span class="v mono">'
        + esc(h.codex || "찾지 못함") + "</span></div>"
        + '<div class="r"><span class="k"></span><span class="v">'
        + "API 키를 쓰지 않습니다. 이 PC 의 ChatGPT 로그인으로 나갑니다."
        + "</span></div>"
        + '<div class="r"><span class="k"></span><span class="v">'
        + '<div class="row">'
        + '<button class="btn btn--sm btn--primary" id="wsLogin">ChatGPT 로그인</button>'
        + '<button class="btn btn--sm" id="wsCheck">연결 확인</button>'
        + '<button class="btn btn--sm" id="wsLogout">로그아웃</button>'
        + "</div>"
        + '<div class="sub" style="margin:8px 0 0">'
        + "로그인을 누르면 검은 창이 하나 뜨고 브라우저가 열립니다. "
        + "ChatGPT 계정으로 승인한 뒤 <b>연결 확인</b>을 눌러 주세요."
        + "</div></span></div></div>"
        + '<div class="sec-h">시험지</div>'
        + (d.exams.length ? d.exams.map(function (e) {
            return '<div class="list-row" data-go="' + esc(e.exam_id) + '">'
              + '<span class="nm">' + esc(e.title) + "</span>"
              + '<span class="ct">' + e.items + "개 문항</span>"
              + '<span class="ar">&rsaquo;</span></div>';
          }).join("") : '<div class="empty">아직 없습니다.</div>'),
      foot: '<button class="btn" id="wsChange">저장 폴더 바꾸기</button>'
        + (d.exams.length
            ? '<button class="btn btn--danger" id="wsWipe">전부 지우기 ('
              + d.exams.length + ")</button>" : "")
        + '<span class="spacer"></span><button class="btn" data-x>닫기</button>',
      after: function (l) {
        $$("[data-x]", l).forEach(function (b) { b.onclick = Panel.close; });
        $$("[data-go]", l).forEach(function (r) {
          r.onclick = function () { Panel.close(); open(r.getAttribute("data-go")); };
        });
        $("#wsChange", l).onclick = changeOut;
        var lg = $("#wsLogin", l);
        if (lg) lg.onclick = function () {
          jpost("/codex", {action: "login"})
            .then(function () { toast("새 창에서 로그인해 주세요"); })
            .catch(function (e) { toast(e.message); });
        };
        var lo = $("#wsLogout", l);
        if (lo) lo.onclick = async function () {
          if (!await Panel.confirm({title: "로그아웃할까요?", ok: "로그아웃", narrow: true,
            sub: "다시 쓰려면 로그인해야 합니다."})) return;
          jpost("/codex", {action: "logout"}).then(function () { toast("로그아웃 창을 띄웠습니다"); });
        };
        var ck = $("#wsCheck", l);
        if (ck) ck.onclick = async function () {
          ck.disabled = true;
          ck.textContent = "확인 중…";
          try {
            /* 파일 검사는 만료를 못 잡는다. 실제로 한 번 부딪혀 봐야 안다. */
            var r = await api("/codex/check");
            var st = $("#wsState", l);
            if (r.ok) {
              if (st) st.innerHTML = '<span class="badge-ok">Codex 연결됨</span>';
              toast("연결됐습니다");
            } else {
              if (st) st.innerHTML = '<span class="badge-bad">로그인 필요</span>';
              toast(r.need_login ? "로그인이 필요합니다" : "확인 실패");
            }
          } finally {
            ck.disabled = false;
            ck.textContent = "연결 확인";
          }
        };
        var w = $("#wsWipe", l);
        if (w) w.onclick = function () { wipeAll(d.exams.length); };
      },
    });
  }

  /* 되돌릴 수 없으므로 두 번 묻는다 — 두 번째는 개수를 직접 치게 한다 */
  async function wipeAll(n) {
    var ok = await Panel.confirm({
      title: "시험지를 전부 지울까요?", narrow: true, danger: true, ok: "계속",
      sub: n + "개가 폴더째 사라집니다.",
      body: '<div class="note note--bad">만들어 둔 문항·해설·채점기가 모두 없어집니다. '
        + "되돌릴 수 없습니다.</div>",
    });
    if (!ok) return;
    var v = await Panel.prompt({
      title: "정말 지울까요?", ok: "지우기",
      sub: "확인을 위해 지울 개수를 적어 주세요.",
      value: "", placeholder: String(n),
      hint: "지금 " + n + "개가 있습니다. <b>" + n + "</b> 을 적으면 지웁니다.",
    });
    if (String(v || "").trim() !== String(n)) {
      if (v != null) toast("숫자가 달라서 그만뒀습니다");
      return;
    }
    var r = await api("/exams", {method: "DELETE"});
    Panel.close();
    State.exam = null; State.items = []; State.summary = {}; built = null;
    toast(r.deleted + "개를 지웠습니다");
    syncRail(); loadRecent(); tabs(); goto("start");
  }

  async function changeOut() {
    var cur = await api("/settings");
    if (cur.env_locked) { toast("MUNJERO_OUT 환경변수가 걸려 있습니다"); return; }
    var v = await Panel.prompt({
      title: "저장 폴더 바꾸기", sub: "시험지마다 이 안에 폴더가 하나씩 생깁니다.",
      value: cur.out_root, placeholder: "예: D:\\munjero-output",
      hint: "기본값은 " + esc(cur["default"]) + " 입니다. 없으면 만듭니다.",
    });
    if (v == null || !v.trim()) return;
    try {
      var r = await jpost("/settings/out-root", {path: v});
      $("#outRoot").textContent = r.out_root;
      State.exam = null; State.items = []; State.summary = {};
      toast("바꿨습니다");
      syncRail(); loadRecent(); tabs(); goto("start");
    } catch (e) { toast(e.message); }
  }

  /* ── 배선 ── */
  $("#sideRTab").onclick = function () {
    var r = $("#sideR");
    r.setAttribute("data-open", r.getAttribute("data-open") === "1" ? "0" : "1");
  };

  /* 우측 서랍의 실행현황 — 오래 걸리는 일이 도는 동안 여기가 살아 있어야 한다 */
  async function refreshSide() {
    var q = State.exam ? "?exam_id=" + encodeURIComponent(State.exam) : "";
    var d;
    try { d = await api("/activity" + q); } catch (e) { return; }

    var running = d.running || [];
    $("#runNow").innerHTML = running.length
      ? running.map(function (r) {
          var pct = r.total ? Math.round(r.done / r.total * 100) : 0;
          return '<div class="run-now"><div class="t">' + esc(r.exam_id) + "</div>"
            + '<div class="prog"><i style="width:' + pct + '%"></i></div>'
            + '<div style="margin-top:7px;font-size:12px">' + r.done + " / " + r.total
            + " 문항</div></div>";
        }).join("")
      : '<div class="idle">도는 작업 없음</div>';

    $("#fileList").innerHTML = (d.stages || []).length
      ? d.stages.map(function (x) {
          var gate = x.gate ? '<span class="gate ' + (x.gate === "확정됨" ? "pass" : "wait")
            + '">' + esc(x.gate) + "</span>" : "";
          return '<li class="' + (x.ok ? "ok" : "") + '">'
            + '<span class="k">' + esc(x.key.slice(0, 2)) + "</span>"
            + '<span class="n">' + esc(x.name) + "</span>" + gate
            + '<span class="v">' + esc(x.note || (x.ok ? "" : "—")) + "</span></li>";
        }).join("")
      : '<li class="idle">시험지를 고르면 나옵니다</li>';

    $("#verList").innerHTML = (d.versions || []).length
      ? d.versions.map(function (v) { return "<li>" + esc(v) + "</li>"; }).join("")
      : '<li class="idle">없음</li>';

    if (running.length) $("#sideR").setAttribute("data-open", "1");
  }
  setInterval(refreshSide, 2500);
  refreshSide();

  $("#railToggle").onclick = function () {
    var b = document.body;
    b.dataset.rail = b.dataset.rail === "collapsed" ? "open" : "collapsed";
  };
  $("#btnNew").onclick = function () { goto("start"); };
  $("#lnkAll").onclick = workspace;
  $("#btnWorkspace").onclick = workspace;
  $("#outRoot").onclick = changeOut;
  $$(".nav a").forEach(function (a) {
    a.onclick = function () { goto(a.getAttribute("data-go")); };
  });

  api("/settings").then(function (s) {
    $("#outRoot").textContent = s.out_root;
    $("#outRoot").title = "눌러서 저장 폴더 바꾸기 — " + s.out_root;
  });

  loadRecent();
  tabs();
  goto("start");

  return {goto: goto, open: open, paintItems: paintItems, syncRail: syncRail,
          currentGroup: currentGroup,
          confirmItems: confirmItems,
          jumpTo: function (id) { State.jumpId = id; goto("map"); }};
})();
