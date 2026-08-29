/* 공통 도구. */
"use strict";

var $ = function (s, r) { return (r || document).querySelector(s); };
var $$ = function (s, r) {
  return Array.prototype.slice.call((r || document).querySelectorAll(s));
};

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
    return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c];
  });
}

function toast(msg) {
  var t = $("#toast");
  t.textContent = msg;
  t.classList.add("on");
  clearTimeout(t._x);
  t._x = setTimeout(function () { t.classList.remove("on"); }, 2600);
}

async function api(path, opt) {
  var r = await fetch("/api" + path, opt);
  var body = null;
  try { body = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error((body && body.detail) || ("요청 실패 " + r.status));
  return body;
}

function jpost(path, data) {
  return api(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data),
  });
}

/* 문항 번호가 숫자면 숫자로, 아니면 문자열로 정렬한다. */
function numRange(items) {
  var ns = items.map(function (i) { return String(i.number); });
  if (!ns.length) return "";
  var all = ns.every(function (n) { return /^\d+$/.test(n); });
  if (all) {
    var v = ns.map(Number);
    return Math.min.apply(null, v) + " ~ " + Math.max.apply(null, v);
  }
  return ns[0] + " ~ " + ns[ns.length - 1];
}
