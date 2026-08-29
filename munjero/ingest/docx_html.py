# -*- coding: utf-8 -*-
"""워드(.docx) → 단순 HTML.

문항을 여기서 알아내지 않는다. 문단·표·그림을 **문서 순서 그대로** HTML 로
옮겨 놓기만 하고, 문항을 잡아내는 일은 parse/generic.py 한 곳에서 한다.
그래야 워드에서 오든 한글에서 오든 같은 규칙으로 읽힌다.

python-docx 는 문단과 표를 각각 따로 준다. 그대로 이어붙이면 표가 전부
문서 끝으로 밀려서 어느 문항의 자료인지 알 수 없게 되므로,
XML 본문의 자식 순서를 직접 훑는다.
"""
from __future__ import annotations

import base64
import html as _h
import os
import re


def _esc(s):
    return _h.escape(s or "", quote=True)


def _img_data_uri(part) -> str:
    mime = getattr(part, "content_type", "") or "image/png"
    return "data:%s;base64,%s" % (
        mime, base64.b64encode(part.blob).decode("ascii"))


def _para_html(p, doc) -> str:
    """문단 하나. 안에 그림이 있으면 함께 내보낸다."""
    from docx.oxml.ns import qn

    out = []
    text = (p.text or "").replace("\xa0", " ").strip()

    # 인라인 그림 — 저자가 복잡한 표나 수식을 캡처해 붙여넣는 경우가 많다
    for blip in p._element.iter(qn("a:blip")):
        rid = blip.get(qn("r:embed")) or blip.get(qn("r:link"))
        if not rid:
            continue
        try:
            part = doc.part.related_parts[rid]
        except KeyError:
            continue
        out.append('<p><img src="%s" alt=""></p>' % _img_data_uri(part))

    if text:
        style = (getattr(p.style, "name", "") or "").lower()
        tag = "h2" if style.startswith("heading") else "p"
        out.append("<%s>%s</%s>" % (tag, _esc(text), tag))
    return "".join(out)


def _table_html(t) -> str:
    """병합을 살린다. gridSpan / vMerge 를 잃으면 서식이 통째로 어긋난다."""
    from docx.oxml.ns import qn

    rows = []
    for tr in t.rows:
        cells = []
        seen = set()
        for tc in tr.cells:
            if id(tc._tc) in seen:      # 가로 병합은 같은 셀이 반복해 나온다
                continue
            seen.add(id(tc._tc))
            gs = tc._tc.find(qn("w:tcPr"))
            span = 1
            vmerge = None
            if gs is not None:
                g = gs.find(qn("w:gridSpan"))
                if g is not None:
                    try:
                        span = int(g.get(qn("w:val")) or 1)
                    except ValueError:
                        span = 1
                v = gs.find(qn("w:vMerge"))
                if v is not None:
                    vmerge = v.get(qn("w:val")) or "continue"
            if vmerge == "continue":    # 세로 병합의 아래쪽 — 위 칸이 자리를 먹는다
                continue
            txt = "\n".join(x.text for x in tc.paragraphs).replace("\xa0", " ").strip()
            attr = ' colspan="%d"' % span if span > 1 else ""
            cells.append("<td%s>%s</td>" % (attr, _esc(txt).replace("\n", "<br>")))
        if cells:
            rows.append("<tr>%s</tr>" % "".join(cells))
    return "<table>%s</table>" % "".join(rows) if rows else ""


def to_html(path: str) -> str:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(path)
    title = os.path.splitext(os.path.basename(path))[0]

    body = []
    # 본문 자식을 순서대로 — 문단과 표가 섞인 순서가 곧 문제의 순서다
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            body.append(_para_html(Paragraph(child, doc), doc))
        elif child.tag == qn("w:tbl"):
            body.append(_table_html(Table(child, doc)))

    html = "\n".join(x for x in body if x)
    return ("<!DOCTYPE html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">"
            "<title>%s</title>"
            "<meta name=\"munjero:title\" content=\"%s\">"
            "<meta name=\"munjero:source\" content=\"%s\">"
            "<meta name=\"munjero:extractor\" content=\"docx@1\">"
            "</head><body>\n%s\n</body></html>"
            % (_esc(title), _esc(title), _esc(os.path.basename(path)), html))
