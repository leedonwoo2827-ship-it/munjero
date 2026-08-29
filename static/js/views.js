/* 본문 화면들. */
"use strict";

var State = {
  exam: null, summary: {}, items: [], dirty: {},
  ansRows: [], ansDirty: {}, view: "start", jumpId: null,
};

var Views = (function () {

  /* ── 시작 ───────────────────────────────────────────────────── */
  function start() {
    return '<div class="view-in">'
      + '<div class="page-h"><h1>시작</h1>'
      + '<span class="why">시험지를 넣으면 문항을 뽑아내고 문항표를 만듭니다</span></div>'

      + '<div class="card"><h2>새 시험지 만들기</h2>'
      + '<div class="sub">시험지 하나가 작업 공간 하나입니다.</div>'

      + '<label class="drop" id="drop">'
      + '<div class="big">여기로 파일을 끌어다 놓으세요</div>'
      + '<div class="small">HTML &middot; 워드 &middot; 한글 &middot; PDF</div>'
      + '<input type="file" id="file" '
      + 'accept=".html,.htm,.docx,.hwp,.hwpx,.pdf,.zip"></label>'

      + '<div class="tips">'
      + "<div>워드·한글·구글 문서에서 웹 페이지로 저장한 것이면 됩니다. "
      + '<b>가급적 HTML 로 업로드해 주세요.</b></div>'
      + "<div>복잡한 표나 그림은 캡처해서 붙여넣어도 됩니다. "
      + "원본 모양 그대로 채점기까지 따라갑니다.</div>"
      + '<div><b>그림이 있으면 [웹 페이지 — 한 개 파일] 로 저장해 주세요.</b> '
      + "그림이 HTML 안에 함께 들어옵니다. "
      + "이미 폴더로 나뉘었다면 <b>폴더째 zip 으로 묶어</b> 넣어도 됩니다.</div></div>"

      + '<table class="fmt"><tbody>'
      + '<tr class="best"><td class="f">HTML</td>'
      + '<td class="w">권합니다</td>'
      + '<td class="d">문단·표·그림이 이미 구분되어 있어 거의 그대로 읽힙니다.</td></tr>'
      + '<tr><td class="f">워드 docx</td>'
      + '<td class="w">잘 됩니다</td>'
      + '<td class="d">문단과 표를 순서대로 읽습니다. 붙여넣은 그림도 함께 옵니다.</td></tr>'
      + '<tr><td class="f">한글 hwpx</td>'
      + '<td class="w">잘 됩니다</td>'
      + '<td class="d">표의 병합 칸과 그림이 파일 안에 함께 들어 있어 그대로 옵니다.<br>'
      + "한글에서 <b>[다른 이름으로 저장 &gt; 한글 표준 문서(*.hwpx)]</b> 로 저장하세요.</td></tr>"
      + '<tr><td class="f">한글 hwp</td>'
      + '<td class="w">됩니다</td>'
      + '<td class="d">예전 형식입니다. 읽히지만 hwpx 로 저장하는 편이 안전합니다.<br>'
      + "암호가 걸렸거나 배포용으로 잠긴 문서는 열리지 않습니다.</td></tr>"
      + '<tr class="worst"><td class="f">PDF</td>'
      + '<td class="w">조판을 탑니다</td>'
      + '<td class="d">글자에 좌표만 있고 구조가 없어, 2단 조판·글상자·띄어쓰기를 '
      + "모두 좌표에서 되짚어야 합니다. 어긋나면 HTML 로 저장해 다시 넣어 주세요.</td></tr>"
      + "</tbody></table>"

      + '<div id="upBusy" class="note note--info hide" style="margin-top:14px">'
      + "읽어내는 중입니다. 잠시만 기다려 주세요…</div>"
      + "</div></div>";
  }

  /* ── 목차 ───────────────────────────────────────────────────
     묶음 문제가 섞이면 구조가 안 보인다. 어디에 무엇이 묶여 있는지 한 줄씩. */
  function toc(groups, cursor) {
    var done = groups.filter(function (g) {
      return g.every(function (x) { return x.reviewed; }); }).length;
    var sec = null, h = [];

    groups.forEach(function (g, k) {
      var it = g[0];
      if (it.subject && it.subject !== sec) {
        sec = it.subject;
        h.push('<div class="toc-sec-row">' + esc(sec) + "</div>");
      }
      var allDone = g.every(function (x) { return x.reviewed; });
      var anyFlag = g.some(function (x) { return x.needs_review; });
      var cls = anyFlag ? "flag" : (allDone ? "done" : "");
      var no = g.length > 1
        ? esc(g[0].number) + " ~ " + esc(g[g.length - 1].number)
        : esc(it.number);
      var kind = it.answer_type === "free" ? "서술형" : "";
      h.push('<div class="toc-row ' + cls + '" data-k="' + k + '">'
        + '<span class="no">' + no + "</span>"
        + '<span class="tx">' + esc((it.question || "(발문 없음)").slice(0, 90)) + "</span>"
        + '<span class="rt">'
        + (g.length > 1 ? '<span class="toc-grp">지문 묶음 ' + g.length + "</span>" : "")
        + (kind ? '<span class="toc-kind">' + kind + "</span>" : "")
        + ((it.tables || []).length ? '<span class="toc-kind">표</span>' : "")
        + ((it.figures || []).length ? '<span class="toc-kind">그림</span>' : "")
        + (anyFlag ? '<span class="tag tag--warn">확인 필요</span>'
            : (allDone ? '<span class="tag tag--ok">확인함</span>' : ""))
        + "</span></div>");
    });

    return '<div class="view-in">'
      + '<div class="page-h"><h1>목차</h1>'
      + '<span class="why">묶음이 어디에 걸쳐 있는지 봅니다. 줄을 누르면 그 문항으로 갑니다</span>'
      + "</div>"
      + '<div class="page-sum">묶음 <b>' + groups.length + "</b>개 &middot; 확인함 <b>"
      + done + "</b> &middot; 남음 " + (groups.length - done) + "</div>"
      + '<div class="bar">'
      + '<button class="btn" id="tocBoard">현황판</button>'
      + '<button class="btn btn--primary" id="tocGo">문항 확인하러 가기 &rarr;</button>'
      + "</div>"
      + '<div class="toc-list">' + (h.length ? h.join("")
          : '<div class="empty">문항이 없습니다.</div>') + "</div></div>";
  }

  /* ── 문항 (한 문항씩 확인) ──────────────────────────────────
     긴 목록을 죽 훑으면 문제 사이에 박스가 섞였을 때 무엇을 봤는지 알 수 없다.
     한 번에 하나만 보여 주고, 확인하면 다음으로 넘긴다.
     여러 문항이 지문을 나눠 쓰면 그 묶음을 한 화면에 함께 보여 준다. */
  function map(d) {
    var items = d.items;
    var single = items.filter(function (i) { return i.answer_type === "single"; }).length;
    var need = items.filter(function (i) { return i.needs_review; }).length;

    return '<div class="view-in">'
      + '<div class="page-h"><h1>문항 확인</h1>'
      + '<span class="why">한 문항씩 보고 고칩니다. 확인한 내용 그대로 정답을 만듭니다</span>'
      + "</div>"
      + '<div class="page-sum">문항 <b>' + items.length + "</b>개 &middot; "
      + numRange(items) + " &middot; 채점 대상 " + single
      + " &middot; 해설만 " + (items.length - single)
      + (need ? ' &middot; <b style="color:var(--warn)">확인 필요 ' + need + "</b>" : "")
      + "</div>"
      + '<div class="bar">'
      + '<button class="btn" id="btnBoard">현황판</button>'
      + '<button class="btn" id="btnSave">고친 내용 저장</button>'
      + '<button class="btn" id="btnRemap">다시 읽기</button>'
      + '<span class="spacer"></span>'
      + '<button class="btn btn--go" id="btnConfirm">'
      + (d.confirmed ? "다시 확정" : "이 문항표로 확정") + " &rarr;</button></div>"
      + '<div id="rev"></div></div>';
  }

  /* 지금 보고 있는 묶음을 그린다. group = 함께 볼 문항 배열 */
  function review(group, pos, total, doneCount, strip) {
    var shared = group.length > 1 ? group[0].passage : null;
    var h = ['<div class="rev-top">'];
    h.push('<span class="rev-count"><b>' + pos + "</b> / " + total
      + (group.length > 1 ? " 묶음" : "") + "</span>");
    h.push('<span class="rev-bar"><i style="width:'
      + Math.round(doneCount / Math.max(total, 1) * 100) + '%"></i></span>');
    h.push('<span class="rev-nav">'
      + '<button class="btn btn--sm" id="revPrev">&larr; 이전</button>'
      + '<button class="btn btn--sm" id="revNext">다음 &rarr;</button></span></div>');

    h.push('<div class="rev-strip">' + strip + "</div>");

    if (shared) {
      h.push('<div class="rev-group"><div class="gh">'
        + group.map(function (g) { return esc(g.number); }).join(" · ")
        + "번이 함께 쓰는 지문</div>");
      h.push('<div class="qb-passage" data-edit contenteditable '
        + 'onblur="Edit.sharedPassage(this.innerText)">' + esc(shared) + "</div></div>");
    }

    h.push('<div class="qb">');
    group.forEach(function (it) {
      h.push(item(it, State.items.indexOf(it), !!shared));
    });
    h.push("</div>");

    h.push('<div class="rev-foot">'
      + '<button class="btn btn--go" id="revOk">확인함 · 다음 &rarr;</button>'
      + '<button class="btn" id="revSkip">건너뛰기</button>'
      + '<span class="spacer"></span>'
      + '<span class="rev-hint"><kbd>&larr;</kbd> <kbd>&rarr;</kbd> 이동 &middot; '
      + "<kbd>Enter</kbd> 확인함</span></div>");
    return h.join("");
  }

  function item(it, i, hideShared) {
    var flags = [];
    if (it.answer_type === "free") flags.push('<span class="tag tag--free">해설만</span>');
    if (it.needs_review) flags.push('<span class="tag tag--warn">확인 필요</span>');
    (it.warnings || []).forEach(function (w) {
      flags.push('<span class="tag tag--warn">' + esc(w) + "</span>");
    });
    if (State.dirty[it.id]) flags.push('<span class="tag tag--ok">고침</span>');

    var h = ['<div class="qb-item' + (it.needs_review ? " flag" : "")
      + (State.dirty[it.id] ? " edited" : "") + '" id="qi-' + esc(it.id) + '">'];

    h.push('<div class="qb-num"><input value="' + esc(it.number)
      + '" onchange="Edit.f(' + i + ",'number',this.value)\"></div>");

    h.push('<div class="qb-acts">'
      + '<button onclick="Edit.mergeUp(' + i + ')"' + (i === 0 ? " disabled" : "")
      + ' title="이 문항이 앞 문항에서 잘려 나온 것이면 도로 붙입니다">앞 문항에 붙이기</button>'
      + '<button onclick="Edit.toggleType(' + i + ')" '
      + 'title="채점하지 않고 해설만 보여 줄 문항으로 바꿉니다">'
      + (it.answer_type === "single" ? "채점 안 함" : "채점 대상으로") + "</button>"
      + '<button class="warn" onclick="Edit.drop(' + i + ')" '
      + 'title="문항이 아닌 것이 잡혔을 때 뺍니다">문항 아님</button></div>');

    if (flags.length) h.push('<div class="qb-flags">' + flags.join("") + "</div>");

    h.push('<div class="qb-stem" data-edit contenteditable data-ph="발문을 적어 주세요" '
      + 'onblur="Edit.f(' + i + ",'question',this.innerText)\">"
      + esc(it.question) + "</div>");

    if (!hideShared && (it.passage || it._showPassage)) {
      h.push('<div class="qb-passage" data-edit contenteditable data-ph="지문" '
        + 'onblur="Edit.f(' + i + ",'passage',this.innerText)\">"
        + esc(it.passage || "") + "</div>");
    }
    if (it.code) {
      h.push('<div class="qb-code" data-edit contenteditable '
        + 'onblur="Edit.f(' + i + ",'code',this.innerText)\">" + esc(it.code) + "</div>");
    }

    (it.tables || []).forEach(function (t, ti) { h.push(tableHtml(i, ti, t)); });

    (it.figures || []).forEach(function (src) {
      h.push('<div class="qb-fig"><img src="' + Edit.figUrl(src)
        + '" alt="" loading="lazy"></div>');
    });

    if (it.answer_type === "single") {
      h.push('<ul class="qb-choices">');
      (it.choices || []).forEach(function (c, ci) {
        h.push('<li><span class="mk">'
          + esc((it.markers && it.markers[ci]) || "①②③④⑤"[ci] || (ci + 1)) + "</span>"
          + '<span data-edit contenteditable style="flex:1" '
          + 'onblur="Edit.choice(' + i + "," + ci + ',this.innerText)">'
          + esc(c) + "</span></li>");
      });
      h.push("</ul>");
    }
    h.push("</div>");
    return h.join("");
  }

  /* 표는 셀 좌표를 유지한다. 병합을 잃으면 서식이 통째로 깨진다. */
  function tableHtml(i, ti, t) {
    var byRow = {};
    (t.cells || []).forEach(function (c) { (byRow[c.r] = byRow[c.r] || []).push(c); });
    var wide = (t.cols || 0) >= 8 ? " qb-table--wide" : "";
    var h = ['<div class="qb-tbl-wrap"><table class="qb-table' + wide + '">'];
    for (var r = 0; r < (t.rows || 0); r++) {
      var row = (byRow[r] || []).sort(function (a, b) { return a.c - b.c; });
      if (!row.length) continue;
      h.push("<tr>");
      row.forEach(function (c) {
        var tag = c.th ? "th" : "td", a = "";
        if (c.rs > 1) a += ' rowspan="' + c.rs + '"';
        if (c.cs > 1) a += ' colspan="' + c.cs + '"';
        h.push("<" + tag + a + '><input value="' + esc(c.t || "") + '" onchange="Edit.cell('
          + i + "," + ti + "," + c.r + "," + c.c + ',this.value)"></' + tag + ">");
      });
      h.push("</tr>");
    }
    h.push("</table></div>");
    h.push('<div class="qb-tbl-bar">'
      + '<button onclick="Edit.swap(' + i + "," + ti + ')">좌변 ↔ 우변 바꾸기</button>'
      + '<button onclick="Edit.dropTable(' + i + "," + ti + ')">이 표 삭제</button></div>');
    return h.join("");
  }

  /* ── 정답 · 해설 ────────────────────────────────────────────── */
  function answer(d, confirmedItems) {
    var rows = (d && d.rows) || [];
    var has = rows.length > 0;
    var low = rows.filter(function (r) { return r.confidence === "low"; }).length;
    var none = rows.filter(function (r) { return !r.explanation; }).length;
    var stale = rows.filter(function (r) { return r.stale; }).length;

    if (!confirmedItems) {
      return '<div class="view-in">'
        + '<div class="page-h"><h1>정답 · 해설</h1></div>'
        + '<div class="note note--warn"><b>먼저 문항표를 확정해 주세요.</b> '
        + "자리가 틀린 채로 만들면 그 시간이 그대로 버려집니다.</div>"
        + '<button class="btn btn--primary" onclick="Shell.goto(\'map\')">'
        + "문항 확인하러 가기</button></div>";
    }

    return '<div class="view-in">'
      + '<div class="page-h"><h1>정답 · 해설</h1>'
      + '<span class="why">AI 가 초안을 씁니다. 읽어보고 고친 뒤 확정하세요</span></div>'
      + '<div class="page-sum" id="ansSum">' + (has
          ? "문항 <b>" + rows.length + "</b>개"
            + (low ? ' &middot; <b style="color:var(--warn)">확신 낮음 ' + low + "</b>" : "")
            + (none ? ' &middot; <b style="color:var(--err)">해설 없음 ' + none + "</b>" : "")
            + (stale ? ' &middot; <b style="color:var(--warn)">문제가 바뀜 ' + stale + "</b>" : "")
          : "아직 만들지 않았습니다.") + "</div>"

      + '<div class="card" id="runCard">'
      + '<div class="prog"><i id="ansProg" style="width:' + (has ? 100 : 0) + '%"></i></div>'
      + '<div class="bar" style="margin:14px 0 0">'
      + '<button class="btn btn--primary" id="btnAnswer">'
      + (has ? "남은 것 마저 쓰기" : "정답 · 해설 요청") + "</button>"
      + '<button class="btn" id="btnAnswerForce">전부 다시 쓰기</button>'
      + '<span class="spacer"></span>'
      + '<button class="btn' + (has ? "" : " hide") + '" id="btnAnsSave">고친 해설 저장</button>'
      + '<button class="btn btn--go' + (has ? "" : " hide") + '" id="btnAnsConfirm">'
      + "해설 확정 &rarr;</button></div>"
      + '<div class="log-lines hide" id="runLog"></div></div>'

      + (has ? '<div class="note note--warn"><b>이건 초안입니다.</b> '
          + "정답과 해설을 읽어보고 틀린 곳은 고쳐 주세요. "
          + "고친 것은 다시 만들어도 덮어쓰지 않습니다.</div>"
          : '<div class="note note--info">100문항에 10~15분쯤 걸립니다. '
          + "만드는 동안 창을 닫아도 계속 돕니다.</div>")

      + '<div class="qb" id="ansList">'
      + (has ? rows.map(ansItem).join("") : "") + "</div></div>";
  }

  function ansItem(r, i) {
    var flags = [];
    if (r.answer_type === "free") flags.push('<span class="tag tag--free">해설만</span>');
    if (r.confidence === "low") flags.push('<span class="tag tag--warn">확신 낮음</span>');
    if (r.stale) flags.push('<span class="tag tag--warn">문제가 바뀜</span>');
    if (r.source === "manual") flags.push('<span class="tag tag--ok">사람이 고침</span>');

    var h = ['<div class="qb-item' + (r.confidence === "low" || r.stale ? " flag" : "")
      + '" id="ai-' + esc(r.id) + '">'];
    h.push('<div class="qb-num">' + esc(r.number) + "</div>");
    if (flags.length) h.push('<div class="qb-flags">' + flags.join("") + "</div>");
    h.push('<div class="qb-stem">' + esc(r.question) + "</div>");

    if (r.answer_type === "single") {
      h.push('<div class="lbl">정답 <em>— 누르면 바꿉니다</em></div><div class="pickrow">');
      (r.choices || []).forEach(function (c, ci) {
        h.push('<button class="' + (r.answer_index === ci ? "on" : "") + '" onclick="Ans.pick('
          + i + "," + ci + ')">'
          + esc((r.markers && r.markers[ci]) || "①②③④⑤"[ci]) + "</button>");
      });
      h.push("</div>");
      h.push('<ul class="qb-choices">' + (r.choices || []).map(function (c, ci) {
        return '<li><span class="mk">'
          + esc((r.markers && r.markers[ci]) || "①②③④⑤"[ci]) + "</span><span>"
          + esc(c) + "</span></li>";
      }).join("") + "</ul>");
    }

    h.push('<div class="lbl">해설</div>');
    h.push('<div class="qb-passage" data-edit contenteditable data-ph="해설을 적어 주세요" '
      + 'onblur="Ans.set(' + i + ",'explanation',this.innerText)\">"
      + esc(r.explanation) + "</div>");

    if (r.diagram_svg) {
      h.push('<div class="lbl">도표</div><div class="ans-svg">' + r.diagram_svg + "</div>");
      h.push('<div class="qb-tbl-bar" style="opacity:1">'
        + '<button onclick="Ans.dropSvg(' + i + ')">이 도표 빼기</button></div>');
    }
    h.push("</div>");
    return h.join("");
  }

  /* ── 내보내기 ───────────────────────────────────────────────── */
  function exportView(s, built) {
    if (!s.answers) {
      return '<div class="view-in"><div class="page-h"><h1>내보내기</h1></div>'
        + '<div class="note note--warn"><b>먼저 정답과 해설을 만들어 주세요.</b></div>'
        + '<button class="btn btn--primary" onclick="Shell.goto(\'answer\')">'
        + "정답 · 해설로 가기</button></div>";
    }
    var n = [];
    if (built && (built.missing || []).length)
      n.push('<div class="note note--bad">정답 없음 ' + built.missing.length + "문항: "
        + built.missing.slice(0, 12).join(", ") + "</div>");
    if (built && (built.stale || []).length)
      n.push('<div class="note note--warn">문제가 바뀌어 해설이 낡은 문항 '
        + built.stale.length + "개: " + built.stale.slice(0, 12).join(", ") + "</div>");

    return '<div class="view-in">'
      + '<div class="page-h"><h1>내보내기</h1>'
      + '<span class="why">파일 하나로 나옵니다. 그대로 보내면 됩니다</span></div>'
      + '<div class="page-sum">' + (built
          ? "문항 <b>" + built.items + "</b>개 &middot; " + Math.round(built.bytes / 1024) + " KB"
          : "아직 만들지 않았습니다.") + "</div>"
      + '<div class="card">' + n.join("")
      + '<div class="bar" style="margin:0">'
      + '<button class="btn btn--primary" id="btnBuild">'
      + (built ? "다시 만들기" : "채점기 만들기") + "</button>"
      + (built ? '<button class="btn" id="btnOpenGrader">열어 보기</button>'
          + '<button class="btn" id="btnDownload">파일로 받기</button>' : "")
      + '<span class="spacer"></span>'
      + '<button class="btn" id="btnFolder">폴더 열기</button></div></div>'
      + '<div class="card"><h2>꼭 확인해 주세요</h2><div class="sub" style="margin:0">'
      + "정답은 AI 가 만든 것입니다. 시험지에는 정답이 없기 때문입니다.<br>"
      + "공식 정답표와 대조해 주세요. 채점기 위쪽 버튼으로 확인이 필요한 문항만 "
      + "골라 볼 수 있습니다. 주소 끝에 <b>?review=1</b> 을 붙이면 전부 펼쳐집니다."
      + "</div></div></div>";
  }

  return {start: start, toc: toc, map: map, item: item, review: review, answer: answer, ansItem: ansItem,
          exportView: exportView};
})();
