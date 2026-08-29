# -*- coding: utf-8 -*-
"""정답·해설 생성 — 배치 · 재개 · 실패 시 이진 분할."""
from __future__ import annotations

import json
import os
import time

from . import codex_client as C
from . import svg_sanitize

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
                             "confidence", "wrong_reasons", "diagram_svg"],
                "properties": {
                    "id": {"type": "string"},
                    "answer_index": {"type": "integer", "minimum": -1, "maximum": 9},
                    "explanation": {"type": "string"},
                    "confidence": {"type": "string",
                                   "enum": ["high", "medium", "low"]},
                    "wrong_reasons": {"type": "array", "items": {"type": "string"}},
                    "diagram_svg": {"type": ["string", "null"]},
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
6. 계산이나 대조가 필요한 해설에는 **마크다운 표**를 쓴다.
   분개는 차변/대변 표로, 원가는 단계별 계산 표로 보이면 글보다 훨씬 빨리 읽힌다.
   | 차변 | 금액 | 대변 | 금액 |
   |---|---|---|---|
   | 상품 | 5,000,000 | 외상매입금 | 5,000,000 |
7. **그림이 있어야 설명이 짧아지는 문항에만** diagram_svg 를 채운다.
   좋은 예 — 위험·비용의 이전 지점, 당사자 사이의 흐름, T계정, 원가 흐름, 배분 구조.
   나쁜 예 — 단순 암기·어법·용어 문항. 이런 문항은 반드시 null 로 둔다.
   억지로 그린 도형은 오히려 해설의 신뢰를 떨어뜨린다. 애매하면 null 이다.
   SVG 규칙:
     - 반드시 viewBox 를 넣고 width/height 는 넣지 않는다 (반응형이어야 한다)
     - viewBox 는 "0 0 640 260" 정도. 가로로 길고 낮게 그린다
     - 쓸 수 있는 요소: svg g path rect circle ellipse line polyline polygon text tspan marker defs
     - script·style·image·foreignObject·이벤트 속성은 금지다. 넣으면 통째로 버려진다
     - 색은 var(--brand-600) var(--brand-50) var(--correct) var(--wrong) var(--muted)
       currentColor none 만 쓴다. 임의의 색상값을 쓰지 마라
     - 글자는 font-size 13 안팎, text-anchor 로 정렬한다. 한글을 써도 된다
8. 웹 검색이나 파일 읽기를 하지 마라. 주어진 텍스트와 네 지식만 쓴다.
9. 출력은 지정된 JSON 스키마뿐이다. 다른 말을 덧붙이지 마라.
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
    """모델에게 넘길 표. 병합 셀은 마크다운으로 표현이 안 되므로 격자로 펼친다."""
    cells = t.get("cells")
    if not cells:                                  # 예전 형식 호환
        cols, rows = t.get("columns") or [], t.get("rows") or []
        out = []
        if cols:
            out.append("| " + " | ".join(cols) + " |")
            out.append("|" + "---|" * len(cols))
        for r in rows[:20]:
            out.append("| " + " | ".join(x.replace("\n", " ") for x in r) + " |")
        return "\n".join(out)

    n_r, n_c = min(t.get("rows", 0), 24), min(t.get("cols", 0), 14)
    grid = [["" for _ in range(n_c)] for _ in range(n_r)]
    for c in cells:
        r0, c0 = c["r"], c["c"]
        if r0 >= n_r or c0 >= n_c:
            continue
        # 병합된 칸은 같은 값을 채워 넣는다. 모델이 격자로 읽어야 계산이 맞는다.
        for dr in range(c.get("rs", 1)):
            for dc in range(c.get("cs", 1)):
                if r0 + dr < n_r and c0 + dc < n_c:
                    grid[r0 + dr][c0 + dc] = (c.get("t") or "").replace("\n", " ")
    out = ["| " + " | ".join(grid[0]) + " |", "|" + "---|" * n_c]
    for row in grid[1:]:
        out.append("| " + " | ".join(row) + " |")
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
        # SVG 는 유일하게 날것으로 화면에 들어가는 값이다. 여기서 반드시 거른다.
        svg = svg_sanitize.sanitize(r.get("diagram_svg") or "")
        out[it["id"]] = {
            "answer_index": ai,
            "explanation": r["explanation"].strip(),
            "confidence": r.get("confidence", "medium"),
            "wrong_reasons": r.get("wrong_reasons") or [],
            "diagram_svg": svg,
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
