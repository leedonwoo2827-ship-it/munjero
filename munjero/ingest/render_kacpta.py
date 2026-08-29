# -*- coding: utf-8 -*-
"""전산세무회계 문항 → 시험지 HTML.

이론은 4지선다로 채점되고, 실무는 서술형이라 채점하지 않는다(정답·해설만 붙는다).
표는 셀 좌표로 복원한 그대로 rowspan/colspan 을 살려 렌더한다.
"""
from __future__ import annotations

from . import hwp_blocks as B
from .render_exam import CSS, esc

EXTRA_CSS = """
.kind-note{background:#fff;border:1px solid var(--line);border-left:4px solid var(--warn);
  border-radius:var(--r);padding:12px 16px;margin:0 0 18px;font-size:13px;color:var(--muted)}
.kind-note b{color:var(--warn)}
.exam-note{margin:14px 0 4px}
.exam-note .data-table{width:100%}
.exam-note .data-table td{text-align:left}
.task-head{font-size:15px;font-weight:800;color:var(--brand-ink);margin:26px 0 2px;
  padding:9px 14px;background:var(--brand-50);border-radius:var(--r)}
.question[data-answer-type="free"]{border-left:4px solid var(--warn)}
.question[data-answer-type="free"] .answer::before{
  content:"정답 · 풀이 — 아직 없음 (채점 대상 아님 · 해설만 제공)"}
.free-input{margin-top:12px;padding:10px 13px;border:1px dashed var(--line2);
  border-radius:var(--r);font-size:12.5px;color:var(--faint)}
.free-input::before{content:"서술형 — 프로그램 입력 문항"}
.figs{background:#fff;border:1px solid var(--line);border-radius:var(--r-lg);
  padding:18px 22px;margin:26px 0}
.figs h3{margin:0 0 6px;font-size:15px;color:var(--brand-ink)}
.figs p{margin:0 0 14px;font-size:13px;color:var(--muted)}
.figs .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
.figs figure{margin:0}
.figs img{width:100%;border:1px solid var(--line);border-radius:var(--r);background:#fff}
.figs figcaption{font:600 11px/1.5 ui-monospace,Consolas,monospace;color:var(--faint);margin-top:5px}
"""


def _table_html(t):
    o = ['<table class="data-table" data-rows="%d" data-cols="%d" '
         'data-src="hwp:Section0#rec%d">' % (t.rows, t.cols, t.rec)]
    for row in t.grid():
        o.append("<tr>")
        for c in row:
            attrs = ""
            if c["row_span"] > 1:
                attrs += ' rowspan="%d"' % c["row_span"]
            if c["col_span"] > 1:
                attrs += ' colspan="%d"' % c["col_span"]
            body = esc(c["text"]).replace("\n", "<br>")
            o.append("<td%s>%s</td>" % (attrs, body))
        o.append("</tr>")
    o.append("</table>")
    return "".join(o)


def _blocks_html(blocks):
    o = []
    buf = []
    for b in blocks:
        if isinstance(b, B.Para):
            t = b.text.replace("gso", "").strip()
            if t:
                buf.append(t)
        else:
            if buf:
                o.append('<blockquote class="passage">%s</blockquote>'
                         % esc("\n".join(buf)))
                buf = []
            o.append(_table_html(b))
    if buf:
        o.append('<blockquote class="passage">%s</blockquote>' % esc("\n".join(buf)))
    return "".join(o)


def _score(q):
    s, w = 1.0, []
    if q.kind == "theory":
        if len(q.choices) != 4:
            s -= .30
            w.append("choices_count=%d" % len(q.choices))
    if not q.stem:
        s -= .40
        w.append("no_stem")
    if q.todos:
        s = min(s, .40)
        w.append("todo_marker")
    return max(0.0, round(s, 2)), w


def render(meta, items, figures, notes=()):
    theory = [q for q in items if q.kind == "theory"]
    practice = [q for q in items if q.kind == "practice"]
    review_n = sum(1 for q in items if _score(q)[1])
    todo_n = sum(len(q.todos) for q in items) + len(figures)

    o = []
    a = o.append
    a("<!DOCTYPE html>")
    a('<html lang="ko"><head><meta charset="utf-8">')
    a("<title>%s</title>" % esc(meta["title"]))
    a('<meta name="munjero:exam-id" content="%s">' % esc(meta["exam_id"]))
    a('<meta name="munjero:title" content="%s">' % esc(meta["title"]))
    a('<meta name="munjero:round" content="%s">' % esc(meta.get("round", "")))
    a('<meta name="munjero:source" content="%s">' % esc(meta["source"]))
    a('<meta name="munjero:extractor" content="%s">' % esc(meta["extractor"]))
    a('<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>')
    a('<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/'
      'pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">')
    a("<style>%s%s</style></head><body>" % (CSS, EXTRA_CSS))

    a('<header class="paper"><div class="wrap">')
    a("<h1>%s</h1>" % esc(meta["title"]))
    a('<div class="meta">이론 <b>%d</b>문항 &middot; 실무 <b>%d</b>문항 '
      '&middot; 표 <b>%d</b>개 &middot; 검수 필요 <b>%d</b>건 &middot; TODO <b>%d</b>건'
      '&nbsp;&nbsp;|&nbsp;&nbsp; 원본 %s</div>'
      % (len(theory), len(practice),
         sum(1 for q in items for b in q.blocks if isinstance(b, B.Table)),
         review_n, todo_n, esc(meta["source"])))
    a("</div></header>")

    a('<div class="wrap">')
    a('<div class="legend">이 파일은 <b>시험지</b>입니다 &mdash; 정답은 아직 없습니다. '
      "문항머리의 conf 는 추출 신뢰도이고, <b>빨간 줄</b>은 사람이 확인해야 할 지점입니다.</div>")
    a('<div class="kind-note"><b>실무 %d문항은 채점하지 않습니다.</b> '
      "분개는 계정과목&middot;금액 조합이라 표기 차이(외상매입금/외상매입, 5000000/5,000,000)로 "
      "오판정이 쏟아집니다. 정답과 풀이는 전부 제공하되 점수화만 하지 않습니다. "
      "점수는 이론 %d문항 기준입니다.</div>" % (len(practice), len(theory)))

    a('<article class="exam" data-exam="%s" data-source="%s" data-extractor="%s">'
      % (esc(meta["exam_id"]), esc(meta["source"]), esc(meta["extractor"])))

    # ── 이론 ──
    a('<section class="exam-section" data-section-no="1" data-title="이론시험">')
    a("<h2>이론시험<small>4지선다 &middot; 채점 대상</small></h2>")
    _notes(a, notes, "theory")
    for q in theory:
        _question(a, q, "single")
    a("</section>")

    # ── 실무 ──
    a('<section class="exam-section" data-section-no="2" data-title="실무시험">')
    a("<h2>실무시험<small>서술형 &middot; 해설만 제공</small></h2>")
    _notes(a, notes, "practice")
    cur_task = None
    for q in practice:
        if q.task != cur_task:
            cur_task = q.task
            a('<div class="task-head">%s</div>' % esc(cur_task or ""))
        _question(a, q, "free")
    a("</section>")

    if figures:
        a('<section class="figs">')
        a("<h3>원본에 포함된 이미지 %d개</h3>" % len(figures))
        a("<p>HWP BinData 에서 추출했습니다. 문서 안 어느 문항에 붙는지는 앵커 정보만으로 "
          "확정할 수 없어 여기에 모아 둡니다 &mdash; 도입 담당자가 배치를 정하면 됩니다.</p>")
        a('<div class="grid">')
        for name, rel in figures:
            a('<figure data-todo="figure" data-src="hwp:BinData/%s">'
              '<img src="%s" alt="%s" loading="lazy">'
              "<figcaption>%s</figcaption></figure>" % (esc(name), esc(rel), esc(name), esc(name)))
        a("</div></section>")

    a("</article></div></body></html>")
    return "\n".join(o)


def _notes(a, notes, mode):
    """기본전제 · 입력 시 유의사항 — 문항에 안 붙지만 수험자에게 필요하다."""
    seen = set()
    for m, t in notes:
        if m != mode:
            continue
        key = "".join(t.flat())
        if key in seen:
            continue
        seen.add(key)
        a('<div class="exam-note">%s</div>' % _table_html(t))


def _question(a, q, atype):
    conf, warns = _score(q)
    need = "true" if (warns or conf < 0.7) else "false"
    a('<div class="question" data-qno="%s" data-answer-type="%s"'
      ' data-src-page="0" data-confidence="%.2f" data-needs-review="%s">'
      % (esc(q.no), atype, conf, need))
    a('<p class="stem">%s</p>' % esc(q.stem))
    if q.blocks:
        a(_blocks_html(q.blocks))
    if q.choices:
        a('<ol class="choices">')
        for i, (mk, c) in enumerate(zip(q.markers, q.choices), 1):
            a('<li class="choice" data-value="%d" data-marker="%s">%s</li>'
              % (i, esc(mk), esc(c)))
        a("</ol>")
    elif atype == "free":
        a('<div class="free-input"></div>')
    for kind, reason, src in q.todos:
        a('<div class="unresolved" data-todo="%s" data-reason="%s"'
          ' data-src="%s" data-confidence="low"></div>'
          % (esc(kind), esc(reason), esc(src)))
    a('<div class="answer" data-todo="answer-key"></div>')
    a("</div>")
