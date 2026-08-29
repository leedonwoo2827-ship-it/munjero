# -*- coding: utf-8 -*-
"""문항 id 가 바뀐 정답 파일을 다시 이어붙인다.

시험 id 를 바꾸면 문항 id 도 같이 바뀌어서, 애써 만든(그리고 사람이 검수한)
정답이 통째로 미아가 된다. item_hash 는 본문과 보기로만 만들기 때문에
시험 id 와 무관하다 — 그걸 열쇠로 다시 붙인다.
"""
from __future__ import annotations

import json
import os


def remap(items_path: str, answers_path: str) -> dict:
    items = json.load(open(items_path, encoding="utf-8"))
    doc = json.load(open(answers_path, encoding="utf-8"))
    old = doc.get("answers") or {}

    by_hash = {}
    for k, v in old.items():
        h = v.get("item_hash")
        if h:
            by_hash.setdefault(h, (k, v))

    new, moved, kept, lost = {}, 0, 0, []
    for it in items["items"]:
        a = old.get(it["id"])
        if a and a.get("item_hash") == it["item_hash"]:
            new[it["id"]] = a
            kept += 1
            continue
        hit = by_hash.get(it["item_hash"])
        if hit:
            new[it["id"]] = hit[1]
            moved += 1
        else:
            lost.append(it["number"])

    doc["exam_id"] = items["exam_id"]
    doc["answers"] = new
    doc["errors"] = {}
    tmp = answers_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, answers_path)
    return {"kept": kept, "moved": moved, "lost": lost, "dropped": len(old) - kept - moved}
