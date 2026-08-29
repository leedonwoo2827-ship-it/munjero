# -*- coding: utf-8 -*-
"""구조화 노드 → 시험지 HTML.

브라우저로 열면 그대로 검수 화면이 되도록 CSS 를 인라인한다.
TODO 는 빨간 점선으로 항상 보이게 한다 — 안 보이는 TODO 는 버린 TODO 다.
"""
from __future__ import annotations

import html as _h

CSS = """
:root{
  --ink:#181d26; --body:#333840; --muted:#5b6376; --faint:#8e96a8;
  --line:#e6eaf2; --line2:#d4d9e4; --soft:#f6f8fc; --soft2:#eef2fb;
  --brand:#0d9488; --brand-ink:#0f3d3a; --brand-50:#eefbf8;
  --todo:#e23b4e; --todo-soft:#fff0f4; --warn:#cf7a0d;
  --r:10px; --r-lg:16px;
}
*{box-sizing:border-box}
body{margin:0;padding:0 0 80px;background:var(--soft);color:var(--body);
  font:15px/1.7 "Pretendard Variable",Pretendard,"맑은 고딕","Malgun Gothic",sans-serif;}
.wrap{max-width:940px;margin:0 auto;padding:0 20px}
header.paper{background:var(--brand-ink);color:#fff;padding:34px 0 30px;margin-bottom:26px}
header.paper h1{margin:0 0 8px;font-size:25px;letter-spacing:-.4px}
header.paper .meta{font-size:13.5px;color:#a7d5cf}
header.paper .meta b{color:#fff;font-weight:700}
.legend{background:#fff;border:1px solid var(--line);border-radius:var(--r);
  padding:12px 16px;margin-bottom:22px;font-size:13px;color:var(--muted)}
.legend b{color:var(--todo)}
.exam-section{margin:34px 0 18px}
.exam-section>h2{font-size:19px;color:var(--brand-ink);margin:0 0 4px;
  padding-bottom:9px;border-bottom:2px solid var(--brand)}
.exam-section>h2 small{font-weight:500;color:var(--muted);font-size:13px;margin-left:8px}
.stimulus-group{background:#fff;border:1px solid var(--line);border-left:4px solid var(--brand);
  border-radius:var(--r);padding:16px 20px;margin:18px 0}
.stimulus-group>.covers{font-size:12px;font-weight:700;color:var(--brand);
  letter-spacing:.4px;margin-bottom:6px}
.group-directive{margin:0 0 10px;font-weight:600;color:var(--ink)}
.passage{background:var(--soft2);border-radius:var(--r);padding:13px 16px;
  margin:11px 0 0;font-size:14.5px;white-space:pre-wrap}
.question{background:#fff;border:1px solid var(--line);border-radius:var(--r-lg);
  padding:18px 22px 20px;margin:14px 0;box-shadow:0 1px 2px rgba(16,24,40,.04)}
.question::before{content:"#" attr(data-qno) "  ·  p." attr(data-src-page)
  "  ·  conf " attr(data-confidence);
  display:block;font:700 11px/1 ui-monospace,Consolas,monospace;
  color:var(--faint);letter-spacing:.5px;margin-bottom:10px}
.question[data-needs-review="true"]{outline:2px dashed var(--warn);outline-offset:2px}
.question[data-stimulus]::after{content:"공유지문 " attr(data-stimulus) " 참조";
  display:inline-block;margin-top:10px;font-size:11.5px;font-weight:700;
  color:var(--brand);background:var(--brand-50);border-radius:99px;padding:3px 10px}
.stem{font-size:16px;font-weight:600;color:var(--ink);margin:0}
.choices{list-style:none;margin:13px 0 0;padding:0;display:flex;flex-direction:column;gap:7px}
.choice{display:flex;gap:10px;align-items:flex-start;padding:9px 13px;
  border:1px solid var(--line2);border-radius:var(--r);background:#fff;font-size:14.5px}
.choice::before{content:attr(data-marker);font-weight:800;color:var(--brand);flex:0 0 auto}
.data-table{border-collapse:collapse;margin:12px 0 0;font-size:13.5px;width:100%}
.data-table th,.data-table td{border:1px solid var(--line2);padding:6px 10px;text-align:center}
.data-table th{background:var(--soft2);font-weight:700;color:var(--ink)}
.figure{margin:12px 0 0}
.figure img{max-width:100%;border:1px solid var(--line);border-radius:var(--r);background:#fff;padding:6px}
.figure__cap{margin-top:6px;font-size:12px;color:var(--faint)}
.answer{margin-top:13px;padding:9px 13px;border:1px dashed var(--line2);border-radius:var(--r);
  font-size:12.5px;color:var(--faint)}
.answer::before{content:"정답 · 해설 — 아직 없음 (AI 생성 단계에서 채워짐)"}
.unresolved{margin:11px 0 0;padding:9px 13px;background:var(--todo-soft);
  border-left:4px solid var(--todo);border-radius:var(--r);
  font-size:12.5px;font-weight:600;color:var(--todo)}
.unresolved::before{content:"TODO · " attr(data-todo) " — " attr(data-reason)
  "  (" attr(data-src) ")"}
"""


def esc(s):
    return _h.escape(s or "", quote=True)


def _score(q):
    s, w = 1.0, []
    n = len(q.choices)
    if n == 0:
        s -= .60
        w.append("no_choices")
    elif n != 4:
        s -= .25
        w.append("choices_count=%d" % n)
    if not q.stem:
        # 공유지문 그룹의 지시문이 발문 역할을 하는 문항은 발문이 비는 게 정상이다.
        if not q.group:
            s -= .50
            w.append("no_stem")
    elif len(q.stem) < 8:
        s -= .20
        w.append("stem_too_short")
    if q.todos:
        s = min(s, .40)
        w.append("todo_marker")
    return max(0.0, round(s, 2)), w


def render(meta, sections, groups, items):
    by_group = {}
    for g in groups:
        by_group["%d-%d" % g.covers] = g

    todo_n = sum(len(q.todos) for q in items)
    review_n = sum(1 for q in items if _score(q)[1])

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
    a("<style>%s</style></head><body>" % CSS)

    a('<header class="paper"><div class="wrap">')
    a("<h1>%s</h1>" % esc(meta["title"]))
    a('<div class="meta">문항 <b>%d</b>개 &middot; 과목 <b>%d</b>개 '
      '&middot; 검수 필요 <b>%d</b>건 &middot; TODO <b>%d</b>건'
      '&nbsp;&nbsp;|&nbsp;&nbsp; 원본 %s</div>'
      % (len(items), len(sections), review_n, todo_n, esc(meta["source"])))
    a("</div></header>")

    a('<div class="wrap">')
    a('<div class="legend">이 파일은 <b>시험지</b>입니다 &mdash; 정답은 아직 없습니다. '
      "문항머리의 conf 는 추출 신뢰도이고, <b>빨간 줄</b>은 사람이 확인해야 할 지점입니다. "
      "고칠 곳은 이 HTML 을 직접 수정하면 됩니다.</div>")

    a('<article class="exam" data-exam="%s" data-source="%s" data-extractor="%s">'
      % (esc(meta["exam_id"]), esc(meta["source"]), esc(meta["extractor"])))

    cur_sec = None
    emitted = set()
    for q in items:
        if q.section_no != cur_sec:
            if cur_sec is not None:
                a("</section>")
            cur_sec = q.section_no
            a('<section class="exam-section" data-section-no="%s" data-title="%s"'
              ' data-section-boundary-confidence="inferred">'
              % (q.section_no or "", esc(q.section or "")))
            a("<h2>제%s과목 &middot; %s<small>추출 기준 경계(추정)</small></h2>"
              % (q.section_no or "?", esc(q.section or "")))

        if q.group and q.group not in emitted:
            emitted.add(q.group)
            g = by_group[q.group]
            a('<section class="stimulus-group" data-covers="%s">' % esc(q.group))
            a('<div class="covers">[%s] 공유지문</div>'
              % esc(q.group.replace("-", "~")))
            if g.directive:
                a('<p class="group-directive">%s</p>' % esc(g.directive))
            if g.passage:
                a('<blockquote class="passage" data-boxed="true">%s</blockquote>'
                  % esc("\n".join(g.passage)))
            # 편지·서식은 줄바꿈과 배치 자체가 정보다. 원본 조각을 함께 남긴다.
            for src in getattr(g, "figures", []):
                a('<div class="figure"><img src="%s" alt="공유지문 원본" loading="lazy">'
                  '<div class="figure__cap">원본 지문 이미지 &mdash; '
                  "줄바꿈과 배치를 그대로 봅니다.</div></div>" % esc(src))
            a("</section>")

        conf, warns = _score(q)
        need = "true" if (warns or conf < 0.7) else "false"
        a('<div class="question" data-qno="%d" data-answer-type="single"'
          ' data-src-page="%d" data-confidence="%.2f" data-needs-review="%s"%s>'
          % (q.no, q.page, conf, need,
             (' data-stimulus="%s"' % esc(q.group)) if q.group else ""))
        a('<p class="stem">%s</p>' % esc(q.stem))
        if q.passage:
            a('<blockquote class="passage" data-boxed="true">%s</blockquote>'
              % esc("\n".join(q.passage)))
        for src in q.figures:
            a('<div class="figure"><img src="%s" alt="원본 조각" loading="lazy">'
              '<div class="figure__cap">원본에서 잘라낸 조각 — 글자가 이미지로 그려져 있어'
              ' 텍스트로 옮기지 못한 부분입니다.</div></div>' % esc(src))
        if q.choices:
            a('<ol class="choices">')
            for i, (mk, c) in enumerate(zip(q.markers, q.choices), 1):
                a('<li class="choice" data-value="%d" data-marker="%s">%s</li>'
                  % (i, esc(mk), esc(c)))
            a("</ol>")
        for kind, reason, src in q.todos:
            a('<div class="unresolved" data-todo="%s" data-reason="%s"'
              ' data-src="%s" data-confidence="low"></div>'
              % (esc(kind), esc(reason), esc(src)))
        a('<div class="answer" data-todo="answer-key"></div>')
        a("</div>")

    if cur_sec is not None:
        a("</section>")
    a("</article></div></body></html>")
    return "\n".join(o)
