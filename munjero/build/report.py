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


def radar(axes: list, title: str = "", size: int = 190) -> str:
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
    longest = max(len(_short(a["name"])) for a in axes)
    pad = min(150, max(70, longest * 8))
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
        o.append("<text class='%s' x='%.1f' y='%.1f' text-anchor='%s'>%s%s"
                 "<tspan class='n' dx='4'>%d</tspan></text>"
                 % (cls, x, y + 3, anchor, tip,
                    esc(_short(a["name"])), a["value"]))

    o.append("</svg>")
    return "".join(o)


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
.radars{display:flex;flex-wrap:wrap;gap:14px;justify-content:center}
.rc{flex:0 0 auto}
.radar{width:min(300px,100%);height:auto}
.radar .ti{font:700 13px/1 "Pretendard Variable",Pretendard,sans-serif;fill:var(--ink)}
.radar .g{fill:none;stroke:var(--line);stroke-width:1}
.radar .sp{stroke:var(--line);stroke-width:1}
.radar .v{fill:rgba(20,184,166,.20);stroke:var(--sky);stroke-width:2;
 stroke-linejoin:round}
.radar .d{fill:var(--sky)}
.radar .d.thin{fill:var(--warn)}
.radar .d.zero{fill:var(--warn);stroke:#fff;stroke-width:1.5}
.radar .lb{font:11.5px/1 "Pretendard Variable",Pretendard,sans-serif;fill:var(--muted)}
.radar .lb.thin{fill:var(--warn);font-weight:700}
.radar .lb.zero{fill:var(--warn);font-weight:800}
.radar .lb.zero .n{fill:var(--warn)}
.radar .lb .n{font-weight:800;fill:var(--brand)}
.radar .lb.thin .n{fill:var(--warn)}
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


def render_html(meta: dict, data: dict, n_items: int) -> str:
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
         "%s &middot; 문항 <b>%d</b>개 &middot; 개념 <b>%d</b>개"
         % (esc(meta.get("exam_title")), n_items, len(rows)),
         "</div></div></header><div class='wrap'>"]

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
    if chaps:
        cards = []
        for c in chaps:
            zero = [a["name"] for a in c["axes"] if a["value"] == 0]
            cards.append(
                "<div class='rc'>%s<div class='rcap'>%d문항%s</div></div>"
                % (radar(c["axes"],
                         c["subject"]),
                   c["total"],
                   " · 안 나온 축 %d" % len(zero) if zero else ""))
        allzero = [a["name"] for c in chaps if not c.get("extra")
                   for a in c["axes"] if a["value"] == 0]
        o.append("<div class='card'><h2>출제 경향</h2>"
                 "<div class='s'>어디가 많이 나왔는지 봅니다. 축은 이 시험에서 실제로 나온 "
                 "<b>개념을 한 단계 묶어 올린 것</b>이고, 축에 마우스를 올리면 그 아래 개념이 보입니다. "
                 "움푹 팬 곳이 적게 나온 자리, "
                 "<span class='zk'>주황</span>은 한 문항도 없는 자리입니다. "
                 "한 문항이 여러 축에 걸치므로 축의 합은 문항 수보다 큽니다.</div>"
                 "<div class='radars'>%s</div>%s</div>"
                 % ("".join(cards),
                    ("<div class='zline'><b>한 문항도 안 나온 축 %d개</b> — %s</div>"
                     % (len(allzero), esc(", ".join(allzero)))) if allzero else ""))

    o.append("<div class='card'><h2>어느 개념이 두껍고 어디가 얇은가</h2>"
             "<div class='s'>많이 나온 순입니다. 한 문항뿐인 개념은 "
             "다음 판에서 늘릴지, 아예 뺄지 정할 자리입니다.</div>")
    for r in rows:
        w = max(4, round(r["count"] / mx * 100))
        nums = ", ".join(r["numbers"][:14]) + (" …" if len(r["numbers"]) > 14 else "")
        o.append("<div class='row%s'><span class='nm'>%s</span>"
                 "<span class='ba'><i style='width:%d%%'></i></span>"
                 "<span class='ct'>%d</span>"
                 "%s<span class='ns'>%s</span></div>"
                 % (" thin" if r["count"] == 1 else "", esc(r["concept"]), w,
                    r["count"],
                    "<span class='th'>얇음</span>" if r["count"] == 1 else "",
                    esc(nums)))
    o.append("</div>")

    o.append("<div class='card'><h2>사고 수준과 난이도</h2>"
             "<div class='s'>한쪽으로 몰려 있으면 개정판에서 균형을 볼 자리입니다.</div>"
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
             "<table class='raw'><thead><tr><th>개념</th><th>문항수</th>"
             "<th>주 난이도</th><th>사고 수준</th><th>문항 번호</th></tr></thead><tbody>")
    for r in rows:
        lv = " · ".join("%s %d" % (k, v) for k, v in r["levels"].most_common())
        o.append("<tr><td>%s</td><td class='n'>%d</td><td>%s</td><td>%s</td>"
                 "<td class='no'>%s</td></tr>"
                 % (esc(r["concept"]), r["count"], esc(r["main_diff"]), esc(lv),
                    esc(", ".join(r["numbers"]))))
    o.append("</tbody></table></div>")

    if thin:
        o.append("<div class='card'><h2>다음 판에서 볼 것</h2><div class='note'>"
                 "한 문항뿐인 개념이 <b>%d개</b>입니다 — %s<br><br>"
                 "이 개념들이 시험에 꼭 필요하다면 문항을 늘리고, "
                 "그렇지 않다면 빼서 다른 개념에 자리를 주는 편이 낫습니다."
                 "</div></div>"
                 % (len(thin), esc(", ".join(r["concept"] for r in thin[:20]))))

    o.append("</div></body></html>")
    return "".join(o)


def write_csv(path: str, rows: list) -> None:
    """엑셀에서 바로 열리도록 BOM 을 넣는다. 없으면 한글이 깨진다."""
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["개념", "문항수", "주 난이도", "사고 수준", "문항 번호"])
        for r in rows:
            lv = " · ".join("%s %d" % (k, v) for k, v in r["levels"].most_common())
            w.writerow([r["concept"], r["count"], r["main_diff"], lv,
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
    with io.open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(meta, data, len(items)))
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
