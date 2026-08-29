/* 플로팅 패널.
   주요 입력과 현황은 바닥(본문) 위에 떠서 처리한다. 본문을 떠나지 않고
   확정·저장 같은 결정을 내리게 하려는 것이다. */
"use strict";

var Panel = (function () {
  var layer = null;

  function el() {
    if (!layer) layer = $("#panelLayer");
    return layer;
  }

  function close() {
    var l = el();
    l.hidden = true;
    l.innerHTML = "";
    document.removeEventListener("keydown", onKey);
  }

  function onKey(e) { if (e.key === "Escape") close(); }

  /* opt = {title, sub, body, foot, wide} */
  function open(opt) {
    var l = el();
    l.hidden = false;
    l.innerHTML =
      '<div class="panel-scrim" data-x="1"></div>'
      + '<div class="panel' + (opt.wide ? " wide" : "") + '">'
      + '<div class="panel-head"><div><h3>' + esc(opt.title || "") + "</h3>"
      + (opt.sub ? '<div class="sub">' + opt.sub + "</div>" : "")
      + '</div><button class="panel-x" data-x="1">&times;</button></div>'
      + '<div class="panel-body">' + (opt.body || "") + "</div>"
      + (opt.foot ? '<div class="panel-foot">' + opt.foot + "</div>" : "")
      + "</div>";
    $$("[data-x]", l).forEach(function (b) { b.onclick = close; });
    document.addEventListener("keydown", onKey);
    if (opt.after) opt.after(l);
    return l;
  }

  /* 확인 한 번으로 끝나는 것 — 되돌리기 어려운 결정에만 쓴다. */
  function confirm(opt) {
    return new Promise(function (resolve) {
      open({
        title: opt.title,
        sub: opt.sub,
        body: opt.body || "",
        foot: '<button class="btn btn--ghost" data-no>취소</button>'
          + '<span class="spacer"></span>'
          + '<button class="btn ' + (opt.danger ? "btn--danger" : "btn--go")
          + '" data-yes>' + esc(opt.ok || "확인") + "</button>",
        after: function (l) {
          $("[data-no]", l).onclick = function () { close(); resolve(false); };
          $("[data-yes]", l).onclick = function () { close(); resolve(true); };
        },
      });
    });
  }

  /* 한 줄 입력 — 저장 폴더 바꾸기 같은 것. */
  function prompt(opt) {
    return new Promise(function (resolve) {
      open({
        title: opt.title,
        sub: opt.sub,
        body: '<input type="text" id="pIn" value="' + esc(opt.value || "")
          + '" placeholder="' + esc(opt.placeholder || "") + '">'
          + (opt.hint ? '<div class="lbl" style="margin-top:10px"><em>'
              + opt.hint + "</em></div>" : ""),
        foot: '<button class="btn btn--ghost" data-no>취소</button>'
          + '<span class="spacer"></span>'
          + '<button class="btn btn--primary" data-yes>'
          + esc(opt.ok || "바꾸기") + "</button>",
        after: function (l) {
          var inp = $("#pIn", l);
          inp.focus();
          inp.select();
          inp.onkeydown = function (e) { if (e.key === "Enter") $("[data-yes]", l).click(); };
          $("[data-no]", l).onclick = function () { close(); resolve(null); };
          $("[data-yes]", l).onclick = function () { close(); resolve(inp.value); };
        },
      });
    });
  }

  return {open: open, close: close, confirm: confirm, prompt: prompt};
})();
