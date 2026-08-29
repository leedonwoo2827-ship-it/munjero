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
    if ext in (".hwp", ".hwpx"):
        return _extract_hwp(src, out_dir, exam_id, title)
    raise SystemExit(
        "지원하지 않는 형식입니다: %s\n"
        "  PDF 또는 HWP 를 넣어주세요. 다른 형식이면 PDF 로 내보낸 뒤 다시 시도하세요." % ext)


def _extract_pdf(src, out_dir, exam_id, title):
    import fitz
    from . import pdf_2col, render_exam

    doc = fitz.open(src)
    sections, groups, items = pdf_2col.build_items(pdf_2col.document_lines(doc))
    meta = {"exam_id": exam_id, "title": title, "round": "",
            "source": os.path.basename(src), "extractor": "pdf_2col_kcci@1"}
    html = render_exam.render(meta, sections, groups, items)
    path = os.path.join(out_dir, "01_extract.html")
    io.open(path, "w", encoding="utf-8").write(html)
    return {"path": path, "items": len(items), "sections": len(sections),
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

    figs = _dump_bindata(ole, os.path.join(out_dir, "figs"))
    meta = {"exam_id": exam_id, "title": title, "round": "",
            "source": os.path.basename(src), "extractor": "hwp_kacpta@1"}
    html = render_kacpta.render(meta, items, figs, notes)
    path = os.path.join(out_dir, "01_extract.html")
    io.open(path, "w", encoding="utf-8").write(html)
    return {"path": path, "items": len(items), "sections": 2,
            "review": sum(1 for q in items if render_kacpta._score(q)[1])}


def _dump_bindata(ole, fig_dir):
    """BinData 를 파일로 꺼낸다. 압축은 항목별이라 매직바이트로 형식을 정한다."""
    from . import hwp_ole

    os.makedirs(fig_dir, exist_ok=True)
    out = []
    for name in ole.names():
        if not name.startswith("BIN"):
            continue
        data, ext = hwp_ole.bin_data(ole.read(name))
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
    return out
