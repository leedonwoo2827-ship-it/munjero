# -*- coding: utf-8 -*-
"""한글 hwpx → 단순 HTML.

hwpx 는 zip + XML 이라 hwp(바이너리 OLE)와는 완전히 다른 포맷이다.
같은 리더로 보내면 "OLE 가 아니다" 로 죽는다.

문항을 여기서 알아내지 않는다. 문단·표·그림을 **문서 순서 그대로** HTML 로
옮기고, 문항을 잡아내는 일은 parse/generic.py 한 곳에서 한다.

  Contents/section0.xml   본문. hp:p(문단) 과 hp:tbl(표) 가 순서대로
  hp:t                    글자
  hp:tc + hp:cellAddr     칸과 그 좌표(colAddr/rowAddr)
  hp:cellSpan             병합(colSpan/rowSpan)
  BinData/                그림 파일
"""
from __future__ import annotations

import base64
import html as _h
import mimetypes
import os
import re
import zipfile

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"


def _esc(s):
    return _h.escape(s or "", quote=True)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text_of(el) -> str:
    """문단 안의 글자를 모은다. hp:t 만 본다 — 다른 요소는 서식이다."""
    out = []
    for t in el.iter():
        if _local(t.tag) == "t":
            out.append(t.text or "")
            # 글자 사이에 들어간 서식 태그의 뒤 텍스트도 붙는다
            for child in t:
                out.append(child.tail or "")
    s = "".join(out).replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


def _images(zf) -> dict:
    """BinData 를 data URI 로. hwpx 는 그림을 zip 안에 그대로 담고 있다."""
    out = {}
    for n in zf.namelist():
        if not n.lower().startswith("bindata/"):
            continue
        blob = zf.read(n)
        mime = mimetypes.guess_type(n)[0] or "image/png"
        out[os.path.basename(n).lower()] = "data:%s;base64,%s" % (
            mime, base64.b64encode(blob).decode("ascii"))
    return out


def _table_html(tbl, imgs) -> str:
    """표. 병합을 살린다 — 잃으면 분개표·증빙 서식이 통째로 어긋난다."""
    rows = []
    for tr in tbl:
        if _local(tr.tag) != "tr":
            continue
        cells = []
        for tc in tr:
            if _local(tc.tag) != "tc":
                continue
            span_c = span_r = 1
            for ch in tc:
                if _local(ch.tag) == "cellSpan":
                    span_c = int(ch.get("colSpan") or 1)
                    span_r = int(ch.get("rowSpan") or 1)
            body = _cell_body(tc, imgs)
            a = ""
            if span_c > 1:
                a += ' colspan="%d"' % span_c
            if span_r > 1:
                a += ' rowspan="%d"' % span_r
            cells.append("<td%s>%s</td>" % (a, body))
        if cells:
            rows.append("<tr>%s</tr>" % "".join(cells))
    return "<table>%s</table>" % "".join(rows) if rows else ""


def _cell_body(tc, imgs) -> str:
    parts = []
    for sub in tc:
        if _local(sub.tag) != "subList":
            continue
        for p in sub:
            if _local(p.tag) != "p":
                continue
            t = _text_of(p)
            if t:
                parts.append(_esc(t))
    return "<br>".join(parts)


def _pic_html(el, imgs) -> str:
    """그림 참조를 data URI 로 바꾼다. 못 찾으면 자리만 남긴다."""
    out = []
    for img in el.iter():
        if _local(img.tag) != "img":
            continue
        ref = img.get("binaryItemIDRef") or img.get("BinItem") or ""
        uri = None
        for k, v in imgs.items():
            if ref and (k.startswith(ref.lower()) or ref.lower() in k):
                uri = v
                break
        if uri is None and imgs:
            continue
        if uri:
            out.append('<p><img src="%s" alt=""></p>' % uri)
    return "".join(out)


def to_html(path: str) -> str:
    from lxml import etree

    title = os.path.splitext(os.path.basename(path))[0]
    body = []

    with zipfile.ZipFile(path) as z:
        imgs = _images(z)
        secs = sorted(n for n in z.namelist()
                      if re.match(r"Contents/section\d+\.xml$", n, re.I))
        if not secs:
            raise SystemExit(
                "hwpx 안에서 본문을 찾지 못했습니다.\n"
                "  한글에서 [다른 이름으로 저장 > 한글 표준 문서(*.hwpx)] 로 "
                "다시 저장해 주세요.")
        for name in secs:
            root = etree.fromstring(z.read(name))
            # 본문 자식 순서가 곧 문제의 순서다. 문단과 표를 섞인 그대로 훑는다.
            for el in root.iter():
                tag = _local(el.tag)
                if tag == "tbl":
                    body.append(_table_html(el, imgs))
                elif tag == "p":
                    # 표 안의 문단은 표에서 이미 처리했다
                    if any(_local(a.tag) == "tc" for a in el.iterancestors()):
                        continue
                    pics = _pic_html(el, imgs)
                    if pics:
                        body.append(pics)
                    t = _text_of(el)
                    if t:
                        body.append("<p>%s</p>" % _esc(t))

    html = "\n".join(x for x in body if x)
    return ('<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8">'
            "<title>%s</title>"
            '<meta name="munjero:title" content="%s">'
            '<meta name="munjero:source" content="%s">'
            '<meta name="munjero:extractor" content="hwpx@1">'
            "</head><body>\n%s\n</body></html>"
            % (_esc(title), _esc(title), _esc(os.path.basename(path)), html))
