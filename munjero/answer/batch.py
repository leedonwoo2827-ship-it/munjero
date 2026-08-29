# -*- coding: utf-8 -*-
"""정답·해설 생성 — 배치 · 재개 · 실패 시 이진 분할."""
from __future__ import annotations

import json
import os
import time

from . import codex_client as C

BATCH = 5          # 배치당 codex 부팅비가 5~10초. 1이면 부팅이 절반, 20이면 출력이 잘린다.

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "answer_index", "explanation",
                             "confidence", "wrong_reasons"],
                "properties": {
                    "id": {"type": "string"},
                    "answer_index": {"type": "integer", "minimum": -1, "maximum": 9},
                    "explanation": {"type": "string"},
                    "confidence": {"type": "string",
                                   "enum": ["high", "medium", "low"]},
                    "wrong_reasons": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}

PREAMBLE = """당신은 한국 국가공인 자격시험 문제의 정답과 해설을 만드는 전문가다.

규칙
1. 아래 각 문항에 대해 정답과 한국어 해설을 낸다.
2. answer_index 는 0-base 다. choices 배열의 인덱스다. ①=0, ②=1, ③=2, ④=3.
   answer_type 이 "free"(서술형)인 문항은 answer_index 를 -1 로 두고
   explanation 에 정답과 풀이를 함께 적는다.
3. explanation 은 3~6문장. "정답은 N번이다"로 시작하지 말고 왜 그것이 맞는지부터 쓴다.
   근거가 되는 협약·조문·기준서·계정과목이 있으면 이름을 밝힌다.
4. wrong_reasons 는 오답 보기마다 한 줄씩, 보기 순서대로. 정답 자리는 빈 문자열.
   서술형이면 빈 배열로 둔다.
5. 확신이 없어도 반드시 하나를 고른다. 대신 confidence 를 "low" 로 적는다.
   답을 비우거나 거부하지 마라 — 뒤 공정이 멈춘다.
6. 웹 검색이나 파일 읽기를 하지 마라. 주어진 텍스트와 네 지식만 쓴다.
7. 출력은 지정된 JSON 스키마뿐이다. 다른 말을 덧붙이지 마라.
"""


def _payload(item):
    d = {"id": item["id"], "answer_type": item["answer_type"],
         "question": item["question"]}
    if item.get("passage"):
        d["passage"] = item["passage"][:2500]
    if item.get("choices"):
        d["choices"] = item["choices"]
    for t in (item.get("tables") or [])[:3]:
        d.setdefault("tables", []).append(_md_table(t))
    return d


def _md_table(t):
    cols, rows = t.get("columns") or [], t.get("rows") or []
    out = []
    if cols:
        out.append("| " + " | ".join(cols) + " |")
        out.append("|" + "---|" * len(cols))
    for r in rows[:20]:
        out.append("| " + " | ".join(x.replace("\n", " ") for x in r) + " |")
    return "\n".join(out)


def build_prompt(exam_title, items):
    body = json.dumps([_payload(i) for i in items], ensure_ascii=False)
    return "%s\n시험: %s\n\n문항:\n%s\n" % (PREAMBLE, exam_title, body)


def _validate(items, data):
    if not isinstance(data, dict) or "results" not in data:
        return None, "results 키가 없음"
    by_id = {i["id"]: i for i in items}
    out = {}
    for r in data["results"]:
        it = by_id.get(r.get("id"))
        if it is None:
            continue
        ai = r.get("answer_index", -1)
        if it["answer_type"] == "single":
            if not isinstance(ai, int) or not (0 <= ai < len(it["choices"])):
                return None, "#%s answer_index 범위 밖(%r)" % (it["number"], ai)
        else:
            ai = -1
        if len(r.get("explanation") or "") < 20:
            return None, "#%s 해설이 너무 짧음" % it["number"]
        out[it["id"]] = {
            "answer_index": ai,
            "explanation": r["explanation"].strip(),
            "confidence": r.get("confidence", "medium"),
            "wrong_reasons": r.get("wrong_reasons") or [],
            "item_hash": it["item_hash"],
            "source": "codex",
        }
    missing = [i["id"] for i in items if i["id"] not in out]
    if missing:
        return None, "응답 누락 %d건" % len(missing)
    return out, None


class Store:
    """배치마다 원자적으로 저장한다. Ctrl+C 나 정전에도 파일이 반쪽이 되지 않는다."""

    def __init__(self, path, exam_id):
        self.path = path
        if os.path.exists(path):
            self.doc = json.load(open(path, encoding="utf-8"))
        else:
            self.doc = {"schema": "munjero/answers@1", "exam_id": exam_id,
                        "engine": {}, "answers": {}, "errors": {}}
        self.doc.setdefault("answers", {})
        self.doc.setdefault("errors", {})

    def pending(self, items, force=False):
        out = []
        for it in items:
            a = self.doc["answers"].get(it["id"])
            if a and a.get("source") == "manual":
                continue                      # 사람이 고친 답은 절대 덮지 않는다
            if force or a is None or a.get("item_hash") != it["item_hash"]:
                out.append(it)
        return out

    def commit(self, results):
        self.doc["answers"].update(results)
        for k in results:
            self.doc["errors"].pop(k, None)
        self.save()

    def fail(self, item, reason):
        self.doc["errors"][item["id"]] = {"reason": reason, "number": item["number"]}
        self.save()

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.doc, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)


def answer_all(doc, out_path, *, batch=BATCH, limit=0, force=False,
               model="", log=print):
    items = doc["items"]
    if limit:
        items = items[:limit]
    store = Store(out_path, doc["exam_id"])
    todo = store.pending(items, force=force)
    if not todo:
        log("  이미 모두 생성되어 있습니다. 다시 만들려면 --force 를 쓰세요.")
        return store

    store.doc["engine"] = {"cli": "codex", "auth": "chatgpt", "model": model or "default"}
    groups = [todo[i:i + batch] for i in range(0, len(todo), batch)]
    log("  %d문항 · %d배치 (배치당 %d문항)" % (len(todo), len(groups), batch))

    t0 = time.time()
    done = 0
    for n, g in enumerate(groups, 1):
        ok = _run_group(doc, g, store, model, log, "[%2d/%d]" % (n, len(groups)))
        done += ok
        el = time.time() - t0
        rate = el / max(done, 1)
        log("        누적 %d/%d · 경과 %.0f초 · 남은 예상 %.0f초"
            % (done, len(todo), el, rate * (len(todo) - done)))
    return store


def _run_group(doc, group, store, model, log, tag):
    """실패하면 절반으로 쪼개 다시 시도한다. 1개까지 내려가고, 그래도 안 되면 기록하고 넘어간다."""
    label = "#%s~#%s" % (group[0]["number"], group[-1]["number"]) \
        if len(group) > 1 else "#%s" % group[0]["number"]
    t0 = time.time()
    try:
        data = C.run(build_prompt(doc["exam_title"], group), SCHEMA, model=model)
        res, err = _validate(group, data)
        if res:
            store.commit(res)
            log("%s %-14s ok  (%.1f초)" % (tag, label, time.time() - t0))
            return len(res)
        raise C.CodexError(err)
    except C.NotAuthenticated:
        raise
    except C.CodexError as e:
        if len(group) == 1:
            store.fail(group[0], str(e)[:300])
            log("%s %-14s 실패 — 건너뜁니다: %s" % (tag, label, str(e)[:90]))
            return 0
        log("%s %-14s 실패 → 분할 재시도 (%s)" % (tag, label, str(e)[:70]))
        mid = len(group) // 2
        return (_run_group(doc, group[:mid], store, model, log, tag)
                + _run_group(doc, group[mid:], store, model, log, tag))
