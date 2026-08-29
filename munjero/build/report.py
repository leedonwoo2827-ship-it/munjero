# -*- coding: utf-8 -*-
"""개념 지도 — 저자에게 넘기는 리포트.

채점기는 학습자가 보는 것이고, 이건 **저자가 다음 개정판에서 무엇을 보강할지**
판단하는 자료다. 그래서 파일을 따로 낸다. 한 파일에 섞으면 둘 다 못 쓴다.

교육평가에서 test blueprint(이원목적분류표)라고 부르는 것과 같은 일을 한다 —
어느 영역이 두껍고 어느 영역이 얇은지를 드러내는 것.
"""
from __future__ import annotations

import csv
import html as _h
import io
import os
import re
from collections import Counter, defaultdict

LEVELS = ["기억", "이해", "적용", "분석", "평가", "창조"]
DIFFS = ["하", "중", "상"]


def esc(s):
    return _h.escape(str(s or ""), quote=True)


def _words(s: str) -> set:
    """논점 비교용 낱말. 조사·기호를 털어낸 두 글자 이상만 본다."""
    s = re.sub(r"[^\w가-힣 ]+", " ", s or "")
    return {w for w in s.split() if len(w) >= 2}


def collect(items: list, kmap: dict = None) -> dict:
    """문항에서 축·개념·수준·난이도를 모은다."""
    by_concept = defaultdict(list)
    for it in items:
        for c in it.get("concepts") or []:
            by_concept[c].append(it)

    rows = []
    for c, its in by_concept.items():
        lv = Counter(i.get("level") for i in its if i.get("level"))
        df = Counter(i.get("difficulty") for i in its if i.get("difficulty"))
        rows.append({
            "concept": c,
            "count": len(its),
            "numbers": [str(i["number"]) for i in its],
            "levels": lv,
            "diffs": df,
            "main_diff": df.most_common(1)[0][0] if df else "",
        })
    rows.sort(key=lambda r: (-r["count"], r["concept"]))

    from . import knowmap
    br = (kmap or {}).get("branches") or []
    axes = knowmap.axes_for(br, items) if br else []
    placed = {c for b in br for a in b["axes"] for c in a["concepts"]}
    # 개념이 어느 갈래·축에 올라갔는지. 표와 CSV 에 필드로 실린다 —
    # 축으로 정렬해 봐야 어디에 힘을 줄지가 보인다.
    at = {c: (b["name"], a["name"])
          for b in br for a in b["axes"] for c in a["concepts"]}
    for r in rows:
        r["branch"], r["axis"] = at.get(r["concept"], ("", ""))
    return {
        "rows": rows,
        "chapters": axes,
        "no_chapter": sum(1 for i in items
                          if not (placed & set(i.get("concepts") or []))),
        "levels": Counter(i.get("level") for i in items if i.get("level")),
        "diffs": Counter(i.get("difficulty") for i in items if i.get("difficulty")),
        "untagged": [str(i["number"]) for i in items if not (i.get("concepts") or [])],
        "overlaps": _overlaps(items),
    }


def _overlaps(items: list) -> list:
    """겹침 의심 — 개념이 둘 이상 같고 논점의 낱말도 절반 넘게 겹치면 올린다.

    판단은 사람이 한다. 여기서는 볼 만한 짝만 골라 준다.
    """
    out = []
    n = len(items)
    for a in range(n):
        ia = items[a]
        ca, pa = set(ia.get("concepts") or []), _words(ia.get("point"))
        if len(ca) < 2 or not pa:
            continue
        for b in range(a + 1, n):
            ib = items[b]
            cb = set(ib.get("concepts") or [])
            shared = ca & cb
            if len(shared) < 2:
                continue
            pb = _words(ib.get("point"))
            if not pb:
                continue
            sim = len(pa & pb) / max(1, min(len(pa), len(pb)))
            if sim >= 0.5:
                out.append({
                    "a": str(ia["number"]), "b": str(ib["number"]),
                    "shared": sorted(shared),
                    "point_a": ia.get("point") or "",
                    "point_b": ib.get("point") or "",
                })
    return out[:30]


def _poly(cx, cy, r, n, k=1.0):
    """정 n각형 꼭짓점. 12시 방향부터 시계 방향."""
    import math

    return [(cx + r * k * math.sin(2 * math.pi * i / n),
             cy - r * k * math.cos(2 * math.pi * i / n)) for i in range(n)]


def _pts(ps):
    return " ".join("%.1f,%.1f" % p for p in ps)


def _short(name: str, n: int = 13) -> str:
    """긴 장 이름을 줄인다. 잘린 자리는 … 로 남겨 둔다."""
    name = (name or "").strip()
    return name if len(name) <= n else name[:n - 1] + "…"


def grader_link(out_dir: str) -> str:
    """옆 폴더의 채점기. 숫자를 눌러 그 문항으로 가려면 이게 있어야 한다.

    아직 내보내지 않았으면 빈 문자열이고, 그러면 번호는 링크가 아니라 글자로 남는다.
    """
    d = os.path.join(os.path.dirname(os.path.abspath(out_dir)), "04_grader")
    try:
        fs = [f for f in os.listdir(d) if f.lower().endswith(".html")]
    except OSError:
        return ""
    if not fs:
        return ""
    fs.sort(key=lambda f: os.path.getmtime(os.path.join(d, f)), reverse=True)
    from urllib.parse import quote
    return "../04_grader/" + quote(fs[0])


def qn(numbers: list, link: str, limit: int = 0) -> str:
    """문항 번호를 누르면 그 문항이 옆에 열린다.

    목록만 봐서는 무슨 문제인지 모른다. 리포트를 떠나지 않고 바로 보여 주고,
    더 볼 것이 있으면 채점기로 건너가게 한다.
    """
    ns = numbers[:limit] if limit else numbers
    more = " …" if limit and len(numbers) > limit else ""
    # 파일명이 URL 인코딩되어 %ED 같은 게 들어 있다. % 서식으로 다루면 터진다.
    out = []
    for n in ns:
        from urllib.parse import quote as _q
        href = esc(link + "?review=1#q" + _q(n)) if link else "#"
        out.append("<a class='qn' data-q='" + esc(n) + "' href='" + href
                   + "'>" + esc(n) + "</a>")
    return ", ".join(out) + more


def qdata(items: list) -> list:
    """옆에 띄울 최소한. 표와 그림까지 담으면 리포트가 무거워진다 —
    그건 채점기가 할 일이고, 여기서는 '어떤 문제였더라' 만 답하면 된다."""
    out = []
    for it in items:
        p = (it.get("passage") or "").strip()
        out.append({
            "n": str(it.get("number")),
            "s": it.get("subject") or "",
            "q": (it.get("question") or "").strip(),
            "p": (p[:700] + " …") if len(p) > 700 else p,
            "c": [str(x) for x in (it.get("choices") or [])],
            "a": it.get("answer_index"),
            "x": (it.get("explanation") or "").strip(),
            "pt": it.get("point") or "",
            "k": it.get("concepts") or [],
            "lv": it.get("level") or "",
            "df": it.get("difficulty") or "",
            "tb": len(it.get("tables") or []),
            "im": len(it.get("images") or it.get("figures") or []),
        })
    return out


#  받침 유무로 조사를 고른다. "중 가 19문항", "3개 은" 처럼 나오면
#  읽는 사람이 기계가 쓴 글로 본다.
_D_JONG = {"0": 1, "1": 1, "3": 1, "6": 1, "7": 1, "8": 1,
           "2": 0, "4": 0, "5": 0, "9": 0}          # 영 일 삼 육 칠 팔 / 이 사 오 구
_A_JONG = set("bcdgklmnprstxz")                     # 알파벳으로 끝나면 소리로 짐작


def _jong(word: str) -> bool:
    """마지막 글자에 받침이 있는가."""
    for ch in reversed(word or ""):
        if "가" <= ch <= "힣":
            return (ord(ch) - 0xAC00) % 28 != 0
        if ch.isdigit():
            return bool(_D_JONG.get(ch, 1))
        if ch.isalpha():
            return ch.lower() in _A_JONG
    return False


def _j(word: str, pair: str = "은는") -> str:
    """word 뒤에 붙일 조사. pair 는 '은는' '이가' '을를' 처럼 받침있음/없음 순."""
    return pair[0] if _jong(word) else pair[1]


def _ro(word: str) -> str:
    """으로 / 로. ㄹ 받침은 '로' 쪽이다 — "매매계약 6으로", "원가요소 4로"."""
    for ch in reversed(word or ""):
        if "가" <= ch <= "힣":
            j = (ord(ch) - 0xAC00) % 28
            return "로" if j in (0, 8) else "으로"     # 8 = ㄹ
        if ch.isdigit():
            # 영(ㅇ) 삼(ㅁ) 육(ㄱ) 만 "으로". 일 칠 팔 은 ㄹ 이라 "로" 쪽이다.
            return "으로" if ch in "036" else "로"
        if ch.isalpha():
            return "으로" if ch.lower() in _A_JONG else "로"
    return "로"


def _names(xs, n=3, sep=" · "):
    return sep.join(esc(x) for x in xs[:n]) + (
        " 외 %d개" % (len(xs) - n) if len(xs) > n else "")


def trend_lede(chaps: list, data: dict) -> str:
    """출제 경향을 문장으로. 읽는 사람이 알고 싶은 건 사용법이 아니라 결과다.

    갈래를 두꺼운 순으로 훑으며 "이번 시험은 이렇게 나왔다" 를 적는다.
    그림은 모양만 보여 주고, 이름과 숫자는 글이 말해야 한다.
    """
    axes = [a for c in chaps for a in c["axes"]]
    if not axes:
        return ""
    br = sorted(chaps, key=lambda c: -c["total"])

    def tops(c, k=2):
        xs = [a for a in sorted(c["axes"], key=lambda a: -a["value"])[:k]
              if a["value"]]
        txt = " · ".join("%s %d" % (a["name"], a["value"]) for a in xs)
        html = " · ".join("<b>%s %d</b>" % (esc(a["name"]), a["value"])
                          for a in xs)
        return html, txt

    s = []
    head = br[0]
    h, t = tops(head)
    s.append("이번 시험은 <b>%s</b>%s %d문항으로 가장 두껍고, 그중 %s%s 중심입니다."
             % (esc(head["subject"]), _j(head["subject"], "이가"),
                head["total"], h, _j(t, "이가")))
    rest = ["<b>%s</b> %d문항은 %s"
            % (esc(c["subject"]), c["total"], tops(c)[0]) for c in br[1:]]
    if rest:
        body = (", ".join(rest[:-1]) + (", " if len(rest) > 1 else "")
                + rest[-1])
        s.append("이어서 %s%s 나왔습니다." % (body, _ro(tops(br[-1])[1])))

    thin = [a["name"] for a in axes if a["value"] == 1]
    zero = [a["name"] for a in axes if a["value"] == 0]
    if thin:
        nm = _names(thin, 5)
        s.append("반면 <b>%s</b>%s 한 문항씩만 나왔습니다." % (nm, _j(nm)))
    if zero:
        nm = _names(zero, 5)
        s.append("<span class='zk'>%s</span>%s 한 문항도 나오지 않았습니다."
                 % (nm, _j(nm)))
    return " ".join(s)


def level_lede(data: dict, n_items: int) -> str:
    """사고 수준과 난이도. 아래 칩에 다 있으니 쏠린 곳만 한 줄로 짚는다."""
    lv = data.get("levels") or Counter()
    df = data.get("diffs") or Counter()
    if not lv and not df:
        return ""
    s = []
    if lv:
        k, v = lv.most_common(1)[0]
        s.append("사고 수준은 <b>%s</b>에 %d문항이 몰려 있고," % (esc(k), v))
        miss = [x for x in LEVELS if not lv.get(x)]
        if miss:
            nm = _names(miss, 3)
            s.append("<b>%s</b>%s 묻는 문항은 없습니다." % (nm, _j(nm, "을를")))
        else:
            s[-1] = s[-1][:-1] + "."
    if df:
        k, v = df.most_common(1)[0]
        s.append("난이도는 <b>%s</b>%s %d문항으로 가장 많습니다."
                 % (esc(k), _j(k, "이가"), v))
    return " ".join(s)


def concept_lede(rows: list, n_items: int) -> str:
    """개념 쪽 문장. 몇 개가 한 번뿐인지가 개정판에서 가장 먼저 볼 숫자다."""
    if not rows:
        return ""
    thin = [r for r in rows if r["count"] == 1]
    top = ["<b>%s %d</b>" % (esc(r["concept"]), r["count"]) for r in rows[:3]]
    s = ["개념 <b>%d</b>개 가운데 가장 두꺼운 것은 %s입니다."
         % (len(rows), " · ".join(top))]
    if thin:
        s.append("<b>%d개</b>는 한 문항에만 나옵니다(%s)."
                 % (len(thin), _names([r["concept"] for r in thin], 4)))
    return " ".join(s)


def _slug(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "-", s).strip("-") or "x"


def radar(axes: list, title: str = "", size: int = 190, group: str = "") -> str:
    """레이더 차트 — 빈 곳이 움푹 팬 자국으로 보인다.

    막대는 위에서 아래로 읽어야 공백을 알아채지만, 레이더는 모양 하나로
    "여기가 들어갔다" 가 바로 보인다. 개정판에서 볼 곳을 찾는 게 목적이므로
    이쪽이 낫다.

    axes = [{"name": 개념, "value": 문항수}, ...]  — 3개 미만이면 그리지 않는다
    """
    n = len(axes)
    if n < 3:
        return ""
    mx = max(a["value"] for a in axes) or 1
    # 축 이름 길이에 맞춰 여백을 잡는다. 고정값으로 두면 긴 이름이 그림 밖으로 잘린다
    # (실제로 "보험 부보와 보험청구 문서" 가 "와 보험청구" 로 보였다).
    # 글자 13.5px 에 숫자가 뒤에 붙는다. 한글은 폭이 거의 글자 크기만큼이다.
    longest = max(len(_short(a["name"])) for a in axes)
    pad = min(200, max(96, longest * 14 + 32))
    top = 26 if title else 6      # 제목 자리
    box = size + pad * 2
    cx = box / 2
    cy = top + pad + size / 2
    r = size / 2

    o = ["<svg class='radar' viewBox='0 0 %d %d' role='img' aria-label='%s'>"
         % (box, box + top, esc(title or "커버리지"))]
    if title:
        o.append("<text class='ti' x='%.1f' y='16' text-anchor='middle'>%s</text>"
                 % (cx, esc(title)))

    # 눈금 — 안쪽부터 네 겹
    for k in (0.25, 0.5, 0.75, 1.0):
        o.append("<polygon class='g' points='%s'/>" % _pts(_poly(cx, cy, r, n, k)))
    # 살
    for x, y in _poly(cx, cy, r, n):
        o.append("<line class='sp' x1='%.1f' y1='%.1f' x2='%.1f' y2='%.1f'/>"
                 % (cx, cy, x, y))

    # 값
    vals = [_poly(cx, cy, r, n, max(0.04, a["value"] / mx))[i]
            for i, a in enumerate(axes)]
    o.append("<polygon class='v' points='%s'/>" % _pts(vals))
    for i, (x, y) in enumerate(vals):
        v = axes[i]["value"]
        cls = "d zero" if v == 0 else ("d thin" if v == 1 else "d")
        o.append("<circle class='%s' cx='%.1f' cy='%.1f' r='%.1f'/>"
                 % (cls, x, y, 3.6 if v == 0 else 2.8))

    # 이름 — 왼쪽 축은 오른쪽 정렬, 오른쪽 축은 왼쪽 정렬
    for i, (x, y) in enumerate(_poly(cx, cy, r + 15, n)):
        dx = x - cx
        anchor = "middle" if abs(dx) < 12 else ("start" if dx > 0 else "end")
        a = axes[i]
        cls = "lb zero" if a["value"] == 0 else ("lb thin" if a["value"] == 1 else "lb")
        tip = ""
        if a.get("concepts"):
            cs = a["concepts"]
            tip = "<title>%s — %s%s</title>" % (
                esc(a["name"]), esc(" · ".join(cs[:14])),
                " 외 %d개" % (len(cs) - 14) if len(cs) > 14 else "")
        t = ("<text class='%s' x='%.1f' y='%.1f' text-anchor='%s'>%s%s"
             "<tspan class='n' dx='4'>%d</tspan></text>"
             % (cls, x, y + 3, anchor, tip,
                esc(_short(a["name"])), a["value"]))
        # 축을 누르면 아래 목록으로 간다. 거기서 번호를 누르면 그 문항으로 간다.
        if group:
            t = "<a class='axl' data-ax='%s' tabindex='0' role='button'>%s</a>" % (
                esc("%s|%s" % (group, a["name"])), t)
        o.append(t)

    o.append("</svg>")
    return "".join(o)


SIDE_JS = """
(function () {
  var Q = window.MJ_Q || {}, AX = window.MJ_AX || [], GL = window.MJ_GRADER || '';
  // 폴더에서 파일로 열면 ../04_grader/... 가 맞지만, 웹 화면에서 열면
  // /api/exam/<id>/report 아래라 그 상대경로가 /api/exam/04_grader/... 가 된다.
  // 어디로 열렸는지 보고 주소를 바꾼다.
  var api = location.pathname.match(/^(.*\\/exam\\/[^\\/]+)\\/report$/);
  if (api) GL = api[1] + '/grader';
  function href(n) {
    return GL ? GL + '?review=1#q' + encodeURIComponent(n) : '';
  }
  var box = document.getElementById('qbd');
  if (!box) return;
  var axById = {}, back = null;
  AX.forEach(function (a) { axById[a.id] = a; });

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c];
    });
  }
  function nums(ns) {
    return ns.map(function (n) {
      return "<a class='qn' data-q='" + esc(n) + "' href='"
        + (esc(href(n)) || '#') + "'>" + esc(n) + "</a>";
    }).join(', ');
  }
  function guide() {
    back = null;
    box.innerHTML = "<div class='sguide'><b>축을 눌러 보세요.</b><br>"
      + "그 축이 어느 문항인지 여기에 뜹니다. 번호를 누르면 그 문제가 뜹니다."
      + "<br><br>아래 개념 목록과 표의 번호도 같습니다.</div>";
  }
  function axis(id) {
    var a = axById[id];
    if (!a) return;
    back = id;
    box.innerHTML = "<div class='sh'><span class='sg'>" + esc(a.g)
      + "</span><b>" + esc(a.a) + "</b><span class='sc'>" + a.v + "문항</span></div>"
      + (a.v ? "<div class='sq'>" + nums(a.ns) + "</div>"
             : "<div class='sq none'>이 축은 이번 시험에 한 문항도 없습니다.</div>")
      + "<div class='sk'>" + a.cs.map(function (c) {
          return "<span>" + esc(c) + "</span>"; }).join('') + "</div>";
    reveal();
  }
  function question(n) {
    var d = Q[n];
    if (!d) return;
    var h = "<div class='sh'>";
    if (back && axById[back]) {
      h += "<a class='sb' data-ax='" + esc(back) + "'>&larr; "
        + esc(axById[back].a) + "</a>";
    }
    h += "<b>" + esc(d.n) + "번</b>"
      + (d.s ? "<span class='sg'>" + esc(d.s) + "</span>" : "")
      + (d.lv ? "<span class='sg'>" + esc(d.lv) + "</span>" : "")
      + (d.df ? "<span class='sg'>난이도 " + esc(d.df) + "</span>" : "")
      + "</div>";
    if (d.k && d.k.length) {
      h += "<div class='sk'>" + d.k.map(function (c) {
        return "<span>#" + esc(c) + "</span>"; }).join('') + "</div>";
    }
    if (d.pt) h += "<div class='spt'>" + esc(d.pt) + "</div>";
    if (d.p) h += "<div class='sps'>" + esc(d.p) + "</div>";
    h += "<div class='sqq'>" + esc(d.q) + "</div>";
    if (d.tb || d.im) {
      h += "<div class='snote'>이 문항에는 "
        + (d.tb ? '표 ' + d.tb + '개 ' : '') + (d.im ? '그림 ' + d.im + '개 ' : '')
        + "가 있습니다. 채점기에서 보세요.</div>";
    }
    (d.c || []).forEach(function (c, i) {
      h += "<div class='sc" + (i === d.a ? ' ok' : '') + "'><i>" + (i + 1)
        + "</i>" + esc(c) + "</div>";
    });
    if (d.x) h += "<div class='sx'><b>해설</b><br>" + esc(d.x) + "</div>";
    if (GL) {
      h += "<a class='sgo' target='_blank' href='" + esc(href(d.n))
        + "'>채점기에서 보기 &rarr;</a>";
    }
    box.innerHTML = h;
    reveal();
  }
  function reveal() {
    box.scrollTop = 0;
    var r = box.getBoundingClientRect();
    // 아래쪽 표에서 눌렀으면 오른쪽 칸이 화면 밖이다. 안 보이면 데려온다.
    if (r.bottom < 60 || r.top > window.innerHeight - 60) {
      box.scrollIntoView({block: 'center', behavior: 'smooth'});
    }
  }
  document.addEventListener('click', function (e) {
    var t = e.target, a;
    if ((a = t.closest('a.qn')) && Q[a.getAttribute('data-q')]) {
      e.preventDefault(); question(a.getAttribute('data-q')); return;
    }
    if ((a = t.closest('a.axl'))) {
      e.preventDefault(); axis(a.getAttribute('data-ax')); return;
    }
    if ((a = t.closest('a.sb'))) { axis(a.getAttribute('data-ax')); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') guide();
    if (e.key === 'Enter' && e.target.classList
        && e.target.classList.contains('axl')) {
      axis(e.target.getAttribute('data-ax'));
    }
  });
  if (api) {
    document.querySelectorAll('a.qn[data-q]').forEach(function (a) {
      a.setAttribute('href', href(a.getAttribute('data-q')) || '#');
    });
  }
  guide();
})();
"""


def _side(qs: list, axes: list, glink: str) -> str:
    """오른쪽 칸을 채우는 데이터와 스크립트.

    file:// 로 여는 문서라 fetch 가 막힌다. 데이터를 그대로 심는다.
    "</" 를 escape 하지 않으면 </script> 로 읽혀 문서가 거기서 끊긴다.
    """
    import json

    if not qs and not axes:
        return ""
    def blob(x):
        return json.dumps(x, ensure_ascii=False).replace("</", "<\\/")

    return ("<script>window.MJ_Q=%s;window.MJ_AX=%s;window.MJ_GRADER=%s;</script>"
            "<script>%s</script>"
            % (blob({q["n"]: q for q in qs}), blob(axes),
               json.dumps(glink), SIDE_JS))


CSS = """
:root{--ink:#16211f;--text:#2a3432;--muted:#5f6b69;--faint:#8d9694;
 --paper:#f5f7f6;--bone:#fdfefe;--line:#e6eaf2;--line2:#d4d9e4;
 --brand:#0b7c72;--brand-deep:#0f3d3a;--brand-50:#eafaf7;--sky:#14b8a6;
 --warn:#cf7a0d;--warn-bg:#fff3e1;--warn-ink:#7a4708;--thin:#c2ccca}
*{box-sizing:border-box}
body{margin:0;padding:0 0 70px;background:var(--paper);color:var(--text);
 font:15px/1.65 "Pretendard Variable",Pretendard,"맑은 고딕","Malgun Gothic",sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:0 24px}
header{background:var(--brand-deep);color:#fff;padding:34px 0 30px;margin-bottom:26px}
header h1{margin:0 0 6px;font-size:26px;letter-spacing:-.4px}
header h1 .hj{font-size:19px;color:#7fc9c0;margin-left:6px;font-weight:400}
header .m{font-size:13.5px;color:#a7d5cf}
header .m b{color:#fff}
.card{background:var(--bone);border:1px solid var(--line);border-radius:16px;
 padding:22px 24px;margin-bottom:16px;box-shadow:0 1px 2px rgba(16,24,40,.05)}
.card h2{margin:0 0 4px;font-size:17px;color:var(--ink)}
.card .s{font-size:13px;color:var(--muted);margin-bottom:16px}
.row{display:flex;align-items:center;gap:12px;padding:7px 8px;border-radius:7px}
.row:hover{background:var(--brand-50)}
.row .nm{flex:0 0 168px;font-weight:700;color:var(--ink);font-size:13.5px;
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .ba{flex:0 0 160px;height:9px;border-radius:99px;background:#e8eeed}
.row .ba i{display:block;height:100%;border-radius:99px;background:var(--sky)}
.row.thin .ba i{background:var(--thin)}
.row .ct{flex:0 0 40px;text-align:right;font-weight:800;color:var(--brand);font-size:13.5px}
.row .ns{flex:1;min-width:0;font:11.5px/1.5 ui-monospace,Consolas,monospace;
 color:var(--faint);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .th{flex:0 0 auto;font-size:11px;font-weight:800;color:var(--warn);
 background:var(--warn-bg);padding:2px 8px;border-radius:99px}
.dist{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}
.dist span{font-size:13px;background:var(--paper);border:1px solid var(--line);
 border-radius:99px;padding:5px 13px}
.dist span b{color:var(--brand);font-weight:800}
.ov{border-left:3px solid var(--warn);background:var(--warn-bg);border-radius:7px;
 padding:11px 14px;margin-bottom:9px;font-size:13.5px;color:var(--warn-ink)}
.ov b{font-weight:800}
.ov .p{color:var(--muted);font-size:12.5px;margin-top:5px}
.note{font-size:13px;color:var(--muted);line-height:1.7}
table.raw{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
table.raw th,table.raw td{border-bottom:1px solid var(--line);padding:8px 10px;
 text-align:left;vertical-align:top}
table.raw th{color:var(--muted);font-size:11.5px;font-weight:800;
 text-transform:uppercase;letter-spacing:.05em}
table.raw td.n{text-align:right;font-weight:700;color:var(--brand)}
table.raw td.no{font:11.5px/1.6 ui-monospace,Consolas,monospace;color:var(--faint)}
.wrap{max-width:1400px}
/* 오른쪽 줄은 페이지 전체의 것이다. 맨 위 카드 안에만 두면 아래 표에서
   번호를 눌렀을 때 화면을 거슬러 올라가야 한다. */
.page{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:18px;
 align-items:start}
.main{min-width:0}
.side{position:sticky;top:16px;max-height:calc(100vh - 32px);overflow:auto;
 background:var(--bone);border:1px solid var(--line);border-radius:16px;
 padding:16px 18px;font-size:13.5px;word-break:keep-all;
 box-shadow:0 1px 2px rgba(16,24,40,.05)}
@media (max-width:1180px){.page{grid-template-columns:1fr}
 .side{position:static;max-height:none}}
@media print{.side{display:none}.page{display:block}}
/* 방사형 두 장이 제 크기(약 420px)로 나란히 서야 글자가 안 줄어든다. */
.sguide{color:var(--muted);line-height:1.8}
.sguide b{color:var(--ink)}
.sh{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:10px;
 padding-bottom:9px;border-bottom:1px solid var(--line)}
.sh b{font-size:15px;color:var(--ink)}
.sg{font-size:11.5px;color:var(--muted);background:var(--bone);
 border:1px solid var(--line);border-radius:99px;padding:2px 9px}
.sc-n,.sh .sc{margin-left:auto;font-weight:800;color:var(--brand)}
.sb{display:block;width:100%;font-size:12px;color:var(--brand);cursor:pointer;
 margin-bottom:6px}
.sb:hover{text-decoration:underline}
.sq{line-height:2.1}
.sq.none{color:var(--warn);font-size:12.5px;line-height:1.7}
.sk{display:flex;flex-wrap:wrap;gap:5px;margin:10px 0}
.sk span{font-size:11.5px;color:var(--brand);background:var(--brand-50);
 border-radius:99px;padding:2px 9px}
.spt{background:var(--bone);border-left:3px solid var(--brand);border-radius:6px;
 padding:9px 11px;font-size:12.5px;color:var(--ink);margin-bottom:10px}
.sps{background:var(--bone);border:1px solid var(--line);border-radius:8px;
 padding:10px 12px;font-size:12.5px;color:var(--muted);margin-bottom:10px;
 max-height:190px;overflow:auto;white-space:pre-wrap}
.sqq{font-weight:700;color:var(--ink);margin-bottom:10px;line-height:1.7}
.snote{font-size:12px;color:var(--warn-ink);background:var(--warn-bg);
 border-radius:6px;padding:7px 10px;margin-bottom:9px}
.side .sc{display:flex;gap:8px;padding:7px 10px;border-radius:7px;
 border:1px solid var(--line);margin-bottom:5px;font-size:12.5px;
 background:var(--bone);line-height:1.6}
.side .sc i{font-style:normal;font-weight:800;color:var(--faint);flex:0 0 14px}
.side .sc.ok{border-color:#86c25a;background:#f1f8e8}
.side .sc.ok i{color:#2f6b13}
.sx{margin-top:11px;padding:11px 13px;background:var(--brand-50);
 border-radius:8px;font-size:12.5px;line-height:1.75;color:var(--text)}
.sx b{color:var(--brand-deep)}
.sgo{display:inline-block;margin-top:11px;font-size:12.5px;color:var(--brand);
 font-weight:700}
.sgo:hover{text-decoration:underline}
/* 번호는 눌러서 문제를 보는 자리다. 링크처럼 보여야 누른다. */
a.qn{color:var(--brand);text-decoration:none;border-bottom:1px dotted var(--line2);
 cursor:pointer}
a.qn:hover{background:var(--brand-50);border-bottom-color:var(--brand)}
.radar a.axl{cursor:pointer}
.radar a.axl:hover .lb,.radar a.axl:focus .lb{fill:var(--brand);font-weight:700}
.radar a.axl .lb{transition:fill .12s}
.radars{display:flex;flex-wrap:wrap;gap:14px;justify-content:center}
.rc{flex:1 1 400px;max-width:520px;min-width:0}
.radar{width:100%;height:auto;display:block}
.radar .ti{font:700 15.5px/1 "Pretendard Variable",Pretendard,sans-serif;fill:var(--ink)}
.radar .g{fill:none;stroke:var(--line);stroke-width:1}
.radar .sp{stroke:var(--line);stroke-width:1}
.radar .v{fill:rgba(20,184,166,.20);stroke:var(--sky);stroke-width:2;
 stroke-linejoin:round}
.radar .d{fill:var(--sky)}
.radar .d.thin{fill:var(--warn)}
.radar .d.zero{fill:var(--warn);stroke:#fff;stroke-width:1.5}
.radar .lb{font:600 13.5px/1 "Pretendard Variable",Pretendard,sans-serif;fill:var(--text)}
.radar .lb.thin{fill:var(--warn);font-weight:700}
.radar .lb.zero{fill:var(--warn);font-weight:800}
.radar .lb.zero .n{fill:var(--warn)}
.radar .lb .n{font-weight:800;font-size:14.5px;fill:var(--brand)}
.radar .lb.thin .n{fill:var(--warn)}
.hint{margin-top:14px;padding-top:12px;border-top:1px solid var(--line);
 font-size:12px;color:var(--faint);line-height:1.7}
.rcap{text-align:center;font-size:12px;color:var(--faint);margin-top:-4px}
.zk{color:var(--warn);font-weight:800}
.zline{margin-top:14px;padding:11px 14px;background:var(--warn-bg);
 border-left:3px solid var(--warn);border-radius:7px;font-size:13px;color:var(--warn-ink)}
.zline b{font-weight:800}
.note-bad{background:#fdebed;border-left:3px solid #c22638;border-radius:7px;
 padding:13px 16px;font-size:13.5px;color:#8f1b28;line-height:1.7}
.note-warn{background:var(--warn-bg);border-left:3px solid var(--warn);
 border-radius:7px;padding:11px 14px;font-size:13.5px;color:var(--warn-ink);
 margin-bottom:16px}
@media print{body{background:#fff}header{background:#fff;color:var(--ink);
 border-bottom:2px solid var(--brand-deep)}header .m,header .m b{color:var(--muted)}
 .card{break-inside:avoid;box-shadow:none}}
"""


def render_html(meta: dict, data: dict, n_items: int, glink: str = "",
                qs: list = None) -> str:
    rows = data["rows"]
    mx = rows[0]["count"] if rows else 1
    thin = [r for r in rows if r["count"] == 1]

    o = ["<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>",
         "<title>출제의 맥(脈) — %s</title>" % esc(meta.get("exam_title")),
         "<link rel='preconnect' href='https://cdn.jsdelivr.net' crossorigin>",
         "<link rel='stylesheet' href='https://cdn.jsdelivr.net/gh/orioncactus/"
         "pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css'>",
         "<style>%s</style></head><body>" % CSS,
         "<header><div class='wrap'><h1>출제의 맥<span class='hj'>脈</span></h1>"
         "<div class='m'>",
         "%s &middot; 문항 <b>%d</b>개 &middot; 개념 <b>%d</b>개%s"
         % (esc(meta.get("exam_title")), n_items, len(rows),
            (" &middot; 한 문항뿐인 개념 <b>%d</b>개" % len(thin)) if thin else ""),
         "</div></div></header><div class='wrap'><div class='page'>"
         "<div class='main'>"]

    # 방사형 지식맵 — 축은 나온 개념을 한 단계 올린 것(2단계)이다.
    # "여기가 비었다" 가 보인다. 문항이 나온 곳만 그리면 공백이 사라진다.
    chaps = data.get("chapters") or []
    if data.get("no_chapter") and data["no_chapter"] >= n_items:
        # 전부 0 인 그림을 그려 놓으면 "안 나왔다" 로 읽힌다. 실제로는 아직 안 만든 것이다.
        o.append("<div class='card'><h2>출제 경향</h2>"
                 "<div class='note-bad'><b>아직 지식맵이 만들어지지 않았습니다.</b><br>"
                 "개념을 묶어 올리는 계산이 한 번 필요합니다. 다시 만들기를 눌러 주세요. "
                 "지금 그리면 모든 축이 0 이라 <b>'안 나온 곳'</b> 과 구별되지 않으므로 "
                 "그리지 않았습니다.</div></div>")
        chaps = []
    elif data.get("no_chapter"):
        o.append("<div class='note-warn'>어느 축에도 안 붙은 문항 <b>%d</b>개는 "
                 "아래 그림에서 빠져 있습니다.</div>" % data["no_chapter"])
    axjs = []
    if chaps:
        cards = []
        for gi, c in enumerate(chaps):
            g = "g%d" % gi
            zero = [a["name"] for a in c["axes"] if a["value"] == 0]
            for a in c["axes"]:
                axjs.append({"id": "%s|%s" % (g, a["name"]),
                             "g": c["subject"], "a": a["name"],
                             "v": a["value"], "ns": a["numbers"],
                             "cs": a.get("concepts") or []})
            cards.append(
                "<div class='rc'>%s%s</div>"
                % (radar(c["axes"], "%s · %d문항" % (c["subject"], c["total"]),
                         group=g),
                   ("<div class='rcap'>안 나온 축 %d</div>" % len(zero))
                   if zero else ""))
        allzero = [a["name"] for c in chaps if not c.get("extra")
                   for a in c["axes"] if a["value"] == 0]
        # 왼쪽에 그림, 오른쪽에 목록과 문항. 채점기로 건너뛰면 보던 자리를
        # 잃는다. 축을 훑다가 "이게 무슨 문제였더라" 를 그 자리에서 확인해야 한다.
        o.append("<div class='card'><h2>출제 경향</h2>"
                 "<div class='s'>%s</div>"
                 "<div class='radars'>%s</div>%s"
                 "<div class='hint'>축을 누르면 오른쪽에 그 축의 문항이, "
                 "번호를 누르면 그 문제가 뜹니다. "
                 "한 문항이 여러 축에 걸치므로 축의 합은 문항 수보다 큽니다.</div>"
                 "</div>"
                 % (trend_lede(chaps, data), "".join(cards),
                    ("<div class='zline'><b>한 문항도 안 나온 축 %d개</b> — %s</div>"
                     % (len(allzero), esc(", ".join(allzero)))) if allzero else ""))

    o.append("<div class='card'><h2>어느 개념이 두껍고 어디가 얇은가</h2>"
             "<div class='s'>%s</div>" % concept_lede(rows, n_items))
    for r in rows:
        w = max(4, round(r["count"] / mx * 100))
        nums = qn(r["numbers"], glink, limit=14)
        o.append("<div class='row%s'><span class='nm'>%s</span>"
                 "<span class='ba'><i style='width:%d%%'></i></span>"
                 "<span class='ct'>%d</span>"
                 "%s<span class='ns'>%s</span></div>"
                 % (" thin" if r["count"] == 1 else "", esc(r["concept"]), w,
                    r["count"],
                    "<span class='th'>얇음</span>" if r["count"] == 1 else "",
                    nums))
    o.append("</div>")

    o.append("<div class='card'><h2>사고 수준과 난이도</h2>"
             "<div class='s'>%s</div>" % level_lede(data, n_items) +
             "<div class='dist'>")
    for lv in LEVELS:
        o.append("<span>%s <b>%d</b></span>" % (lv, data["levels"].get(lv, 0)))
    o.append("</div><div class='dist' style='margin-top:10px'>")
    for df in DIFFS:
        o.append("<span>난이도 %s <b>%d</b></span>" % (df, data["diffs"].get(df, 0)))
    o.append("</div></div>")

    if data["overlaps"]:
        o.append("<div class='card'><h2>겹침 의심 %d쌍</h2>"
                 "<div class='s'>개념이 둘 이상 같고 논점도 비슷한 짝입니다. "
                 "정말 겹치는지는 읽어 보고 판단해 주세요.</div>"
                 % len(data["overlaps"]))
        for v in data["overlaps"]:
            o.append("<div class='ov'><b>#%s &harr; #%s</b> &nbsp; %s"
                     "<div class='p'>#%s %s<br>#%s %s</div></div>"
                     % (esc(v["a"]), esc(v["b"]), esc(" · ".join(v["shared"])),
                        esc(v["a"]), esc(v["point_a"]),
                        esc(v["b"]), esc(v["point_b"])))
        o.append("</div>")

    if data["untagged"]:
        o.append("<div class='card'><h2>개념이 안 붙은 문항 %d개</h2>"
                 "<div class='s note'>%s</div></div>"
                 % (len(data["untagged"]), esc(", ".join(data["untagged"]))))

    o.append("<div class='card'><h2>표로 보기</h2>"
             "<div class='s'>같은 내용을 concepts.csv 로도 냈습니다. "
             "엑셀에서 바로 열립니다.</div>"
             "<table class='raw'><thead><tr><th>갈래</th><th>축</th><th>개념</th>"
             "<th>문항수</th>"
             "<th>주 난이도</th><th>사고 수준</th><th>문항 번호</th></tr></thead><tbody>")
    for r in rows:
        lv = " · ".join("%s %d" % (k, v) for k, v in r["levels"].most_common())
        o.append("<tr><td class='g'>%s</td><td class='ax'>%s</td><td>%s</td>"
                 "<td class='n'>%d</td><td>%s</td><td>%s</td>"
                 "<td class='no'>%s</td></tr>"
                 % (esc(r.get("branch")), esc(r.get("axis")),
                    esc(r["concept"]), r["count"],
                    esc(r["main_diff"]), esc(lv),
                    qn(r["numbers"], glink)))
    o.append("</tbody></table></div>")

    o.append("</div><aside class='side' id='qbd'></aside></div></div>")
    o.append(_side(qs or [], axjs, glink))
    o.append("</body></html>")
    return "".join(o)


def write_csv(path: str, rows: list) -> None:
    """엑셀에서 바로 열리도록 BOM 을 넣는다. 없으면 한글이 깨진다."""
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["갈래", "축", "개념", "문항수", "주 난이도", "사고 수준",
                    "문항 번호"])
        for r in rows:
            lv = " · ".join("%s %d" % (k, v) for k, v in r["levels"].most_common())
            w.writerow([r.get("branch", ""), r.get("axis", ""),
                        r["concept"], r["count"], r["main_diff"], lv,
                        ", ".join(r["numbers"])])


def build(items_doc: dict, answers_doc: dict, out_dir: str) -> dict:
    """개념 지도 HTML 과 CSV 를 낸다."""
    from .grader import merge

    merge(items_doc, answers_doc)          # 문항에 정답·메타를 얹는다
    items = items_doc["items"]
    os.makedirs(out_dir, exist_ok=True)
    kmap = knowledge_map(items, out_dir,
                         items_doc.get("exam_title") or items_doc.get("exam_id"))
    data = collect(items, kmap)

    html_path = os.path.join(out_dir, "리포트.html")
    csv_path = os.path.join(out_dir, "concepts.csv")

    meta = {"exam_title": items_doc.get("exam_title") or items_doc.get("exam_id")}
    glink = grader_link(out_dir)       # 채점기가 있으면 번호에서 건너갈 수 있다
    with io.open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(meta, data, len(items), glink, qdata(items)))
    write_csv(csv_path, data["rows"])

    return {"html": html_path, "csv": csv_path,
            "concepts": len(data["rows"]), "items": len(items),
            "thin": sum(1 for r in data["rows"] if r["count"] == 1),
            "overlaps": len(data["overlaps"]),
            "untagged": len(data["untagged"]),
            "axes": sum(len(b["axes"]) for b in data["chapters"]),
            "branches": len(data["chapters"])}


def knowledge_map(items: list, out_dir: str, exam_title: str,
                  force: bool = False) -> dict:
    """개념 위계. 개념이 그대로면 다시 부르지 않는다 — 한 번이 20~40초다."""
    from . import knowmap

    path = os.path.join(out_dir, "지식맵.json")
    fp = knowmap.fingerprint(c for i in items for c in (i.get("concepts") or []))
    old = knowmap.load(path)
    if not force and old.get("fingerprint") == fp and old.get("branches"):
        return old
    try:
        d = knowmap.make(exam_title or "이 시험", items)
    except Exception:
        return old          # 못 만들면 있던 것으로 그린다. 리포트까지 죽이진 않는다
    if d.get("branches"):
        knowmap.save(path, d)
        return d
    return old
