# -*- coding: utf-8 -*-
"""정답·해설 생성 — 배치 · 재개 · 실패 시 이진 분할."""
from __future__ import annotations

import json
import os
import re
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
                             "confidence", "wrong_reasons", "diagram_svg",
                             "chapter", "concepts", "point", "level",
                             "difficulty", "misconception"],
                "properties": {
                    "id": {"type": "string"},
                    "answer_index": {"type": "integer", "minimum": -1, "maximum": 9},
                    "explanation": {"type": "string"},
                    "confidence": {"type": "string",
                                   "enum": ["high", "medium", "low"]},
                    "wrong_reasons": {"type": "array", "items": {"type": "string"}},
                    "diagram_svg": {"type": ["string", "null"]},
                    # 아래 다섯은 학습자에게 보여 주는 동시에,
                    # 모아 두면 저자가 다음 개정판에서 무엇을 보강할지 보는 근거가 된다.
                    # 장(章) — 저자가 개정판을 볼 때 쓰는 단위.
                    # concepts 는 너무 잘게 갈라져(25문항에 103개) 축이 못 된다.
                    "chapter": {"type": "string"},
                    "concepts": {"type": "array", "items": {"type": "string"}},
                    "point": {"type": "string"},
                    "level": {"type": "string",
                              "enum": ["기억", "이해", "적용",
                                       "분석", "평가", "창조"]},
                    "difficulty": {"type": "string", "enum": ["하", "중", "상"]},
                    "misconception": {"type": ["string", "null"]},
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
8. chapter 는 이 문항이 속하는 **교재의 장(章)** 이다. 아래 장 목록에서 고른다.
   목록에 없는 이름을 새로 만들지 마라. concepts 처럼 잘게 쪼개지도 마라.
   ("미지급급여" 는 chapter 가 아니라 concepts 다.)
9. concepts 는 이 문항이 다루는 개념 3~5개다.
   **그 과목에서 통용되는 이름을 쓴다.** 문항마다 새 말을 지어내지 마라.
   같은 개념은 반드시 같은 이름으로 적는다 — 이름이 흔들리면 집계가 무너진다.
   좋은 예: "Incoterms 2010", "CIP", "위험 이전", "신용장", "감가상각"
   나쁜 예: "인코텀즈2010규칙", "씨아이피조건", "위험이 넘어가는 시점"
   약어와 풀이름이 함께 쓰이는 개념은 **약어 쪽**으로 통일한다(신용장이 아니라 "신용장",
   Letter of Credit 이 아니라 "신용장" — 한국어 시험이므로 한국어 통용어가 우선).
10. point 는 이 문항이 진짜 묻는 것 한 줄이다. 정답 자체가 아니라 **판단의 갈림길**을 적는다.
   좋은 예: "비용 부담 지점과 위험 이전 지점이 같지 않다"
   나쁜 예: "정답은 운송 중 전매이다"
11. level 은 이 문항이 요구하는 사고다. 블룸 개정 분류의 여섯 단계를 쓴다.
   기억 — 외운 것을 떠올리는가
   이해 — 뜻을 알고 제 말로 바꿀 수 있는가
   적용 — 새로운 사례에 규칙을 쓰는가
   분석 — 요소로 갈라 관계를 따지는가
   평가 — 기준을 대고 판단하는가
   창조 — 새로 짜 맞추는가
   자격시험 객관식은 대개 기억~분석에 몰린다. 억지로 평가·창조를 붙이지 마라.
12. difficulty 는 그 시험을 준비하는 사람 기준으로 하 · 중 · 상.
13. misconception 은 **틀리는 사람이 흔히 갖는 잘못된 생각**을 한 문장으로.
   억지로 만들지 마라. 단순 암기 문항처럼 특별한 오해가 없으면 null 로 둔다.
14. 웹 검색이나 파일 읽기를 하지 마라. 주어진 텍스트와 네 지식만 쓴다.
15. 출력은 지정된 JSON 스키마뿐이다. 다른 말을 덧붙이지 마라.
"""


CURRICULUM_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["subjects"],
    "properties": {
        "subjects": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["subject", "chapters"],
                "properties": {
                    "subject": {"type": "string"},
                    "chapters": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}

CURRICULUM_PROMPT = """당신은 한국 국가공인 자격시험의 출제 기준을 잘 아는 사람이다.

아래 시험의 **표준 커리큘럼**을 과목별 장(章) 목록으로 내라.

규칙
1. 그 시험의 공식 출제 기준·표준 교재에서 통용되는 영역 이름을 쓴다.
   지어내지 말고, 그 분야 사람이 보면 바로 알아보는 이름으로.
2. 한 과목에 **8~12개**. 너무 잘게 쪼개지 말고 장 단위로 굵게 잡는다.
3. 순서는 교재가 다루는 순서대로.
4. 과목 구분이 없는 시험이면 subject 를 "전체" 하나로 두고 장만 낸다.
5. 웹 검색을 하지 마라. 네 지식만 쓴다.
6. 출력은 지정된 JSON 스키마뿐이다.

시험: %s
문항에 붙어 있는 과목 구분: %s
"""


def curriculum(exam_title: str, subjects: list, model: str = "") -> dict:
    """시험의 표준 커리큘럼을 한 번만 받아 둔다.

    이걸 안 하면 배치마다 장 이름이 흔들려서(25문항에 개념 103개가 그랬다)
    방사형 축을 만들 수 없다. 축은 닫힌 목록이어야 한다.
    """
    subs = ", ".join(s for s in subjects if s) or "(없음)"
    try:
        d = C.run(CURRICULUM_PROMPT % (exam_title, subs),
                  CURRICULUM_SCHEMA, model=model, timeout=180)
    except C.CodexError:
        return {"subjects": []}
    out = []
    for s in d.get("subjects") or []:
        ch = [c.strip() for c in (s.get("chapters") or []) if c.strip()]
        if ch:
            out.append({"subject": (s.get("subject") or "전체").strip(),
                        "chapters": ch[:14]})
    return {"subjects": out}


def _payload(item):
    d = {"id": item["id"], "answer_type": item["answer_type"],
         "question": item["question"]}
    if item.get("subject"):
        d["subject"] = item["subject"]      # 과목을 알아야 개념 이름이 흔들리지 않는다
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


CH_HEAD_ONE = """
장 목록 — chapter 는 아래 '-' 뒤의 이름을 **글자 그대로** 적는다.
목록에 없는 이름을 새로 만들지 마라. 없으면 가장 가까운 것을 고른다.
"""

CH_HEAD_MANY = """
장 목록 — chapter 는 아래 '-' 뒤의 이름을 **글자 그대로** 적는다.
'과목 …' 줄은 묶음의 이름일 뿐 장이 아니다. 그 줄을 chapter 로 적지 마라.
문항의 subject 와 같은 과목 안에서만 고른다.
목록에 없는 이름을 새로 만들지 마라. 없으면 가장 가까운 것을 고른다.
"""


def build_prompt(exam_title, items, curri=None):
    """장 목록을 닫힌 집합으로 함께 보낸다.

    문항마다 장 이름을 짓게 두면 배치마다 흔들려서 방사형 축이 안 만들어진다.
    (개념을 그렇게 뒀더니 25문항에 103개가 나왔다.)
    """
    body = json.dumps([_payload(i) for i in items], ensure_ascii=False)
    ch = ""
    if curri and curri.get("subjects"):
        # 대괄호로 [과목] 장·장·장 을 늘어놓았더니 모델이 대괄호 안의
        # 과목 이름을 장으로 베꼈다(무역영어 75문항 중 59개가 그랬다).
        # 과목 표시를 빼고, 이 배치에 실제로 있는 과목의 장만 줄로 세운다.
        want = {i.get("subject") for i in items if i.get("subject")}
        subs = [x for x in curri["subjects"]
                if not want or x["subject"] in want] or curri["subjects"]
        lines = []
        for x in subs:
            if len(subs) > 1:
                lines.append("과목 %s 의 장:" % x["subject"])
            lines += ["  - %s" % c for c in x["chapters"]]
        head = CH_HEAD_MANY if len(subs) > 1 else CH_HEAD_ONE
        ch = head + "\n".join(lines) + "\n"

    return "%s%s\n시험: %s\n\n문항:\n%s\n" % (PREAMBLE, ch, exam_title, body)


def norm_chapter(name: str, curri: dict = None, subject: str = "") -> str:
    """장 이름을 목록에 맞춰 되돌린다.

    모델이 "[이론시험] 재고자산" 처럼 과목을 앞에 붙여 오면 같은 장이 둘로
    갈라진다. 접두사를 벗기고, 목록에 있는 이름이면 그걸로 맞춘다.
    """
    c = (name or "").strip()
    if not c:
        return ""
    c = re.sub(r"^\s*[\[(<]\s*[^\]\)>]{1,20}\s*[\])>]\s*", "", c).strip()
    c = re.sub(r"^\s*\d+\s*[.)]\s*", "", c).strip()
    subs = (curri or {}).get("subjects") or []
    # 과목 이름을 장으로 베껴 오는 일이 있었다("영문해석", "영작문").
    # 과목은 장이 아니다. 잘못 온 것이니 비워서 내보낸다.
    if any(c == x.get("subject") for x in subs):
        return ""
    # 같은 이름의 장이 여러 과목에 있다(무역영어의 "해상보험"). 제 과목 것을 먼저 본다.
    mine = [x for x in subs if subject and x["subject"] == subject]
    allowed = [ch for x in (mine or subs) for ch in (x.get("chapters") or [])]
    if not allowed:
        return c
    if c in allowed:
        return c
    flat = c.replace(" ", "")
    for a in allowed:
        if a.replace(" ", "") == flat:
            return a
    for a in allowed:                       # 부분 일치까지만. 더 늘리면 엉뚱한 데 붙는다
        if flat and (flat in a.replace(" ", "") or a.replace(" ", "") in flat):
            return a
    return c


def _validate(items, data, curri=None):
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
            "chapter": norm_chapter(r.get("chapter"), curri, it.get("subject")),
            "concepts": [c.strip() for c in (r.get("concepts") or []) if c.strip()][:6],
            "point": (r.get("point") or "").strip(),
            "level": r.get("level") or "",
            "difficulty": r.get("difficulty") or "",
            "misconception": (r.get("misconception") or "").strip() or None,
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

    # 장 목록을 먼저 닫아 둔다. 배치마다 이름이 흔들리면 방사형 축이 안 만들어진다.
    curri = store.doc.get("curriculum")
    if not (curri and curri.get("subjects")):
        log("  장 목록을 정하는 중…")
        subs = []
        for i in items:
            if i.get("subject") and i["subject"] not in subs:
                subs.append(i["subject"])
        curri = curriculum(doc["exam_title"], subs, model)
        store.doc["curriculum"] = curri
        store.save()
        for s2 in curri.get("subjects") or []:
            log("    [%s] %s" % (s2["subject"], " · ".join(s2["chapters"])))
    doc["_curriculum"] = curri
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
        data = C.run(build_prompt(doc["exam_title"], group, doc.get("_curriculum")),
                     SCHEMA, model=model)
        res, err = _validate(group, data, doc.get("_curriculum"))
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
