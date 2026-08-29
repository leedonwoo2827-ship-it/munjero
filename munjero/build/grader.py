# -*- coding: utf-8 -*-
"""문항 JSON + 정답 JSON → 채점기 HTML 한 파일.

file:// 문서는 origin 이 null 이라 fetch 가 CORS 로 막힌다.
그래서 데이터를 <script> 안에 굽는다 — 클래식 스크립트는 CORS 대상이 아니다.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(HERE, "templates")

FONT_LINK = (
    '<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>\n'
    '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/'
    'pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">'
)


def inline_json(obj) -> str:
    """문항 본문에 </script> 가 있으면 스크립트가 거기서 끊긴다.
    HTML 파서는 그게 문자열 안인지 모른다. 반드시 막는다."""
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return s.replace("</", "<\\/").replace("<!--", "<\\!--")


def _to_data_uri(path, cache):
    if path in cache:
        return cache[path]
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        cache[path] = "data:%s;base64,%s" % (
            mime, base64.b64encode(f.read()).decode("ascii"))
    return cache[path]


def _embed_appendix(figs, dirs, cache, lost):
    out = []
    for f in figs or []:
        src = f.get("src", "")
        if src.startswith("data:"):
            out.append(f)
            continue
        path = _find(src, dirs)
        if path:
            out.append({"src": _to_data_uri(path, cache), "caption": f.get("caption", "")})
        else:
            lost.append(src)          # 조용히 버리지 않는다
    return out


def _find(src, dirs):
    rel = src.replace("/", os.sep)
    for d in dirs:
        p = os.path.join(d, rel)
        if os.path.isfile(p):
            return p
    return None


def _embed_images(items, dirs, cache=None, lost=None):
    """그림을 data URI 로 굽는다. 파일 하나로 떼어 주는 게 목표다."""
    cache = {} if cache is None else cache
    lost = [] if lost is None else lost
    n = 0
    for it in items:
        out = []
        for src in it.get("figures") or []:
            if src.startswith("data:"):
                out.append(src)
                continue
            path = _find(src, dirs)
            if not path:
                lost.append(src)
                continue
            before = len(cache)
            uri = _to_data_uri(path, cache)
            if len(cache) > before:
                n += 1
            out.append(uri)
        it["figures"] = out
    return n


def merge(items_doc, answers_doc):
    """정답을 문항에 얹는다. 본문이 바뀌었으면 낡은 정답으로 표시한다."""
    ans = (answers_doc or {}).get("answers", {})
    stale, missing = [], []
    for it in items_doc["items"]:
        a = ans.get(it["id"])
        if a is None:
            missing.append(it["number"])
            it["confidence"] = None
            continue
        if a.get("item_hash") != it["item_hash"]:
            stale.append(it["number"])
            it["needs_review"] = True
            it.setdefault("warnings", []).append("answer_stale")
        it["answer_index"] = a.get("answer_index")
        it["explanation"] = a.get("explanation")
        it["confidence"] = a.get("confidence")
        it["wrong_reasons"] = a.get("wrong_reasons") or []
        it["diagram_svg"] = a.get("diagram_svg")
    return stale, missing


def build(items_doc, answers_doc, out_path, *, base_dir=".", no_cdn=False):
    stale, missing = merge(items_doc, answers_doc)
    dirs = [d for d in (items_doc.get("base_dir"), base_dir) if d]
    cache, lost = {}, []
    n_img = _embed_images(items_doc["items"], dirs, cache, lost)
    appendix = _embed_appendix(items_doc.get("appendix_figures"), dirs, cache, lost)
    n_img += len(appendix)

    slim = []
    for it in items_doc["items"]:
        slim.append({k: it.get(k) for k in (
            "id", "number", "subject", "answer_type", "question", "passage",
            "tables", "figures", "choices", "markers", "answer_index",
            "explanation", "confidence", "wrong_reasons", "diagram_svg",
            "needs_review", "source")})
    data = {"exam_id": items_doc["exam_id"], "exam_title": items_doc["exam_title"],
            "source_file": items_doc.get("source_file", ""), "items": slim,
            "appendix_figures": appendix}

    html = open(os.path.join(TEMPLATES, "grader.html"), encoding="utf-8").read()
    app = open(os.path.join(TEMPLATES, "grader.js"), encoding="utf-8").read()

    html = html.replace("{{TITLE}}", items_doc["exam_title"])
    html = html.replace("{{SUBTITLE}}", "시험지에서 채점기까지")
    html = html.replace("{{FONT_LINK}}", "" if no_cdn else FONT_LINK)
    html = html.replace("{{DATA_JS}}", "window.MUNJERO=" + inline_json(data) + ";")
    html = html.replace("{{APP_JS}}", app)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, out_path)

    return {"path": out_path, "bytes": os.path.getsize(out_path),
            "stale": stale, "missing": missing, "images": n_img, "lost_images": lost}
