# -*- coding: utf-8 -*-
"""원본 시험지(PDF/HWP) → 시험지 HTML.

시험마다 조판이 근본적으로 달라 어댑터를 나눈다. 공유하는 것은 렌더러뿐이다.
"""
from __future__ import annotations

import io
import os
import re


def slugify(name: str) -> str:
    s = os.path.splitext(os.path.basename(name))[0]
    s = re.sub(r"\s+", "-", s.strip())
    return re.sub(r'[\\/:*?"<>|]', "", s)


def extract(src: str, out_dir: str, exam_id: str = "", title: str = "") -> dict:
    """원본 한 개를 시험지 HTML 로 바꾼다. 확장자로 어댑터를 고른다."""
    ext = os.path.splitext(src)[1].lower()
    exam_id = exam_id or slugify(src)
    title = title or os.path.splitext(os.path.basename(src))[0]
    os.makedirs(out_dir, exist_ok=True)

    if ext == ".pdf":
        return _extract_pdf(src, out_dir, exam_id, title)
    if ext == ".hwpx":
        return _extract_hwpx(src, out_dir, exam_id, title)
    if ext == ".hwp":
        return _extract_hwp(src, out_dir, exam_id, title)
    if ext == ".docx":
        return _extract_docx(src, out_dir, exam_id, title)
    raise SystemExit(
        "지원하지 않는 형식입니다: %s\n"
        "  HTML · 워드(.docx) · 한글(.hwp) · PDF 를 넣어 주세요.\n"
        "  .doc 는 워드에서 .docx 로 저장한 뒤 다시 시도하세요." % ext)


def _extract_hwpx(src, out_dir, exam_id, title):
    """hwpx 는 zip+XML 이라 hwp(OLE)와 리더가 다르다. HTML 로만 옮기고 판별은 파서에 맡긴다."""
    from . import hwpx_html

    html = hwpx_html.to_html(src)
    path = os.path.join(out_dir, "01_extract.html")
    io.open(path, "w", encoding="utf-8").write(html)
    return {"path": path, "items": 0, "sections": 0, "review": 0,
            "figures": html.count("data:image"), "deferred": True}


def _extract_docx(src, out_dir, exam_id, title):
    """워드는 문항을 여기서 알아내지 않고 HTML 로만 옮긴다.

    문항을 잡아내는 규칙은 parse/generic.py 한 곳에만 둔다. 그래야 워드에서
    오든 한글에서 오든 구글 문서에서 오든 같은 방식으로 읽힌다.
    """
    from . import docx_html

    html = docx_html.to_html(src)
    path = os.path.join(out_dir, "01_extract.html")
    io.open(path, "w", encoding="utf-8").write(html)
    return {"path": path, "items": 0, "sections": 0, "review": 0,
            "figures": html.count("data:image"), "deferred": True}


def _extract_pdf(src, out_dir, exam_id, title):
    import fitz
    from . import pdf_2col, render_exam

    doc = fitz.open(src)
    sections, groups, items = pdf_2col.build_items(pdf_2col.document_lines(doc))
    n_fig = pdf_2col.capture_regions(doc, items, groups,
                                     os.path.join(out_dir, "figs"))
    meta = {"exam_id": exam_id, "title": title, "round": "",
            "source": os.path.basename(src), "extractor": "pdf_2col_kcci@1"}
    html = render_exam.render(meta, sections, groups, items)
    path = os.path.join(out_dir, "01_extract.html")
    io.open(path, "w", encoding="utf-8").write(html)
    return {"path": path, "items": len(items), "sections": len(sections),
            "figures": n_fig,
            "review": sum(1 for q in items if render_exam._score(q)[1])}


def _extract_hwp(src, out_dir, exam_id, title):
    from . import hwp_blocks, hwp_kacpta, hwp_ole, render_kacpta

    ole = hwp_ole.Ole(open(src, "rb").read())
    fh = hwp_ole.file_header(ole.read("FileHeader"))
    if fh["encrypted"] or fh["distributed"]:
        raise SystemExit(
            "암호화되었거나 배포용으로 잠긴 문서입니다.\n"
            "  한글에서 [파일 > 다른 이름으로 저장 > 한글 표준 문서(*.hwpx)] 로 저장한 뒤\n"
            "  다시 시도하세요. 표가 그대로 살아옵니다.")

    records = list(hwp_ole.iter_records(
        hwp_ole.decompress(ole.read("BodyText/Section0"), fh["compressed"])))
    items, notes = hwp_kacpta.build_items(hwp_blocks.build_blocks(records))

    figs, dropped = _dump_bindata(ole, os.path.join(out_dir, "figs"))
    meta = {"exam_id": exam_id, "title": title, "round": "",
            "source": os.path.basename(src), "extractor": "hwp_kacpta@1"}
    html = render_kacpta.render(meta, items, figs, notes)
    path = os.path.join(out_dir, "01_extract.html")
    io.open(path, "w", encoding="utf-8").write(html)
    return {"path": path, "items": len(items), "sections": 2,
            "figures": len(figs), "dropped_figures": dropped,
            "review": sum(1 for q in items if render_kacpta._score(q)[1])}


def _decoration(im):
    """시험지 안의 그림은 대부분 문제와 상관없는 페이지 장식이다.

    로고·버튼·머리띠·빈 서식 용지 같은 것들이고, 정작 문제 내용(사업자등록증
    기재사항, 세금계산서 금액)은 표에 들어 있다. 이런 걸 그대로 실으면
    화면이 지저분해지고 파일만 커진다(빈 국세청 용지 하나가 456KB 다).

    돌려주는 값은 버리는 이유. 남길 그림이면 None.
    """
    from PIL import Image, ImageStat

    g = im.convert("L")
    w, h = g.size
    ratio = w / max(h, 1)
    px = list(g.getdata())
    ink = sum(1 for p in px if p < 200) / max(len(px), 1) * 100

    if ink < 8:
        return "빈 서식 용지·워터마크 (잉크 %.1f%%)" % ink
    if ratio >= 5:
        return "가로 머리띠·워드마크 (비율 %.1f)" % ratio
    if ratio >= 2.5 and h <= 200:
        return "버튼·로고 (%dx%d)" % (w, h)
    return None


def _dump_bindata(ole, fig_dir, keep_all=False):
    """BinData 를 파일로 꺼낸다. 압축은 항목별이라 매직바이트로 형식을 정한다."""
    from . import hwp_ole

    os.makedirs(fig_dir, exist_ok=True)
    out, dropped = [], []
    seen = {}
    for name in ole.names():
        if not name.startswith("BIN"):
            continue
        data, ext = hwp_ole.bin_data(ole.read(name))

        if not keep_all:
            try:
                from PIL import Image
                why = _decoration(Image.open(io.BytesIO(data)))
            except Exception:
                why = None
            if why:
                dropped.append((name, why))     # 조용히 버리지 않는다. 세어서 알린다
                continue

        digest = hash(data)
        if digest in seen:
            dropped.append((name, "%s 와 같은 그림" % seen[digest]))
            continue
        seen[digest] = name

        stem = name.split(".")[0]
        if ext == "bmp":
            try:
                from PIL import Image
                target = os.path.join(fig_dir, stem + ".png")
                Image.open(io.BytesIO(data)).save(target)
            except Exception:
                target = os.path.join(fig_dir, stem + ".bmp")
                open(target, "wb").write(data)
        else:
            target = os.path.join(fig_dir, "%s.%s" % (stem, ext))
            open(target, "wb").write(data)
        out.append((name, "figs/" + os.path.basename(target)))
    return out, dropped
