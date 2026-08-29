# -*- coding: utf-8 -*-
"""시험지 HTML → 문항 JSON.

파서는 **클래스명만** 본다. 태그·인라인 스타일·<b>·<br>·공백은 전부 자유다.
그래야 사람이 브라우저에서 보면서 마음대로 고쳐도 파서가 안 깨진다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

from bs4 import BeautifulSoup

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def _txt(node) -> str:
    if node is None:
        return ""
    for br in node.find_all("br"):
        br.replace_with("\n")
    s = node.get_text("\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def strip_leading_marker(s: str) -> str:
    """보기 앞의 ①·1)·가. 는 있어도 되고 없어도 된다. 파서가 벗긴다."""
    s = s.strip()
    if s and s[0] in CIRCLED:
        return s[1:].strip()
    return re.sub(r"^(?:\(?\d{1,2}[.)]|[가-힣][.)])\s+", "", s)


def item_hash(question: str, choices) -> str:
    raw = question + "\x00" + "\x00".join(choices)
    return "sha1:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _table(node):
    rows = []
    for tr in node.find_all("tr"):
        rows.append([_txt(td) for td in tr.find_all(["td", "th"])])
    if not rows:
        return None
    return {"columns": rows[0], "rows": rows[1:]} if len(rows) > 1 else \
           {"columns": [], "rows": rows}


def parse_html(path: str) -> dict:
    soup = BeautifulSoup(open(path, encoding="utf-8").read(), "lxml")
    base_dir = os.path.dirname(os.path.abspath(path))

    def meta(name, default=""):
        tag = soup.find("meta", attrs={"name": "munjero:" + name})
        return (tag.get("content") if tag else "") or default

    exam_id = meta("exam-id", "exam")
    doc = {
        "schema": "munjero/items@1",
        "exam_id": exam_id,
        "exam_title": meta("title") or (soup.title.string if soup.title else exam_id),
        "round": meta("round"),
        "source_file": meta("source"),
        # 그림 상대경로는 시험지 HTML 옆을 기준으로 한다. 빌드가 폴더를 옮겨도 찾아간다.
        "base_dir": base_dir,
        "extractor": meta("extractor"),
        "sections": [],
        "items": [],
        # 어느 문항에 붙는지 알 수 없어 부록으로 남은 그림. 버리지 않고 끝까지 들고 간다.
        "appendix_figures": [
            {"src": img.get("src", ""), "caption": _txt(img.find_parent("figure"))}
            for img in soup.select(".figs figure img")
        ],
    }

    # 공유지문을 먼저 모아 둔다 — 문항이 covers 로 참조한다
    stimulus = {}
    for sg in soup.select("section.stimulus-group"):
        key = sg.get("data-covers", "")
        parts = []
        d = sg.select_one(".group-directive")
        if d:
            parts.append(_txt(d))
        for bq in sg.select(".passage"):
            parts.append(_txt(bq))
        stimulus[key] = "\n\n".join(p for p in parts if p)

    for sec in soup.select("section.exam-section"):
        doc["sections"].append({
            "no": _int(sec.get("data-section-no")),
            "name": sec.get("data-title", ""),
            "boundary_confidence": sec.get("data-section-boundary-confidence", "exact"),
        })

    auto = 0
    for q in soup.select(".question"):
        sec = q.find_parent("section", class_="exam-section")
        warnings = []

        no = q.get("data-qno")
        if not no:
            auto += 1
            no = str(auto)
            warnings.append("number_autofilled")

        stem = _txt(q.select_one(".stem"))
        if not stem:
            first = q.find(string=True, recursive=False)
            stem = (first or "").strip()
            if stem:
                warnings.append("stem_from_text_node")

        passages = [_txt(p) for p in q.select(".passage")]
        tables = [t for t in (_table(t) for t in q.select(".data-table")) if t]
        figures = [img.get("src", "") for img in q.select(".figure img, img.fig")]

        choices, markers = [], []
        for li in q.select(".choices > .choice"):
            markers.append(li.get("data-marker", ""))
            choices.append(strip_leading_marker(_txt(li)))

        todos = [{"kind": u.get("data-todo", ""), "reason": u.get("data-reason", ""),
                  "src": u.get("data-src", "")}
                 for u in q.select(".unresolved")]
        if todos:
            warnings.append("todo_marker")

        atype = q.get("data-answer-type", "single")
        if atype == "single" and len(choices) != 4:
            warnings.append("choices_count=%d" % len(choices))

        gid = q.get("data-stimulus")
        # 공유지문이 있으면 문항 지문 앞에 붙인다 — 해설 생성기가 한 덩어리로 읽어야 한다
        pass_parts = ([stimulus[gid]] if gid in stimulus else []) + passages
        item = {
            "id": "%s#%s" % (exam_id, no),
            "number": no,
            "subject": (sec.get("data-title") if sec else None),
            "subject_no": _int(sec.get("data-section-no")) if sec else None,
            "answer_type": atype,
            "question": stem,
            "passage": "\n\n".join(p for p in pass_parts if p) or None,
            "stimulus": gid,
            "code": None,
            "tables": tables or None,
            "figures": figures or [],
            "choices": choices,
            "markers": markers,
            "answer_index": None,
            "explanation": None,
            "source": {"page": _int(q.get("data-src-page")),
                       "confidence": _float(q.get("data-confidence"))},
            "item_hash": item_hash(stem, choices),
            "warnings": warnings,
            "needs_review": bool(warnings) or q.get("data-needs-review") == "true",
        }
        doc["items"].append(item)

    return doc


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def report(doc) -> str:
    items = doc["items"]
    single = [i for i in items if i["answer_type"] == "single"]
    need = [i for i in items if i["needs_review"]]
    lines = [
        "── 매핑 결과: %s ──" % doc["exam_id"],
        "  문항        %4d 개  (채점 대상 %d · 해설만 %d)"
        % (len(items), len(single), len(items) - len(single)),
        "  보기 4개    %4d / %d" % (sum(1 for i in single if len(i["choices"]) == 4),
                                    len(single)),
        "  검수 필요   %4d 문항" % len(need),
    ]
    for i in need[:12]:
        lines.append("     #%-6s %s" % (i["number"], ", ".join(i["warnings"]) or "-"))
    if len(need) > 12:
        lines.append("     … 외 %d건" % (len(need) - 12))
    return "\n".join(lines)


def save(doc, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
