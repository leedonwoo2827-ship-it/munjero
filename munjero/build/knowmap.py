# -*- coding: utf-8 -*-
"""방사형 지식맵 — 나온 개념을 3단계로 잇는다.

시험의 공식 목차를 축으로 삼으려 했더니 실패했다. 모델에게 서른 장을
늘어놓고 고르라 하면 고르지 못하고 제 말로 답한다(75문항 중 59개가 그랬다).

그래서 방향을 뒤집는다. **위에서 내려오지 않고 아래에서 올라간다.**
이미 붙어 있는 개념을 묶어 올리므로 해설을 다시 만들 필요가 없다.

    3단계  갈래     방사형 한 장의 제목
    2단계  축       방사형의 축
    1단계  개념     이미 문항에 붙어 있는 것. 몇 문항이냐가 축의 길이

한 번 만들면 지식맵.json 에 남는다. 개념이 바뀌지 않는 한 다시 부르지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict

from ..answer import codex_client as C

ORPHAN = "그 밖"      # 어디에도 안 붙은 개념을 담는 자리. 축이 아니다.

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["branches"],
    "properties": {
        "branches": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "axes"],
                "properties": {
                    "name": {"type": "string"},
                    "axes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["name", "concepts"],
                            "properties": {
                                "name": {"type": "string"},
                                "concepts": {"type": "array",
                                             "items": {"type": "string"}},
                            },
                        },
                    },
                },
            },
        },
    },
}

PROMPT = """너는 이 시험의 개념을 위계로 정리한다.

아래는 %s 의 문항에서 실제로 뽑혀 나온 개념들이다. 괄호 안은 그 개념이
나온 문항 수다. 이것이 **1단계** 다.

%s

할 일은 두 가지다.

1. 이 개념들을 **2단계(축)** 으로 묶는다.
   - 축은 그 분야를 아는 사람이 쓰는 이름이어야 한다. 개념 이름을 그대로
     쓰지 말고 한 단계 위의 말로 올린다.
     좋은 예: "위험 이전", "FOB", "CIF" → 축은 "정형거래조건"
     나쁜 예: 축을 "Incoterms 2010" 이라 하면 1단계와 같아서 올린 게 없다.
   - 축 이름은 12자 이내로 짧게. 방사형 그림에 들어간다.

2. 축을 다시 **3단계(갈래)** 로 묶는다.
   - 갈래는 2개에서 4개. 갈래마다 방사형 한 장이 그려진다.
   - 갈래 하나에 축은 6개에서 10개. 5개보다 적으면 그림이 안 되고
     11개가 넘으면 글자가 겹친다.

규칙

- **위에 있는 개념을 하나도 빠짐없이, 그리고 정확히 한 번만 배치한다.**
  빠뜨리면 문항 수가 안 맞는다. 두 곳에 넣으면 두 번 세어진다.
- 개념 이름은 **글자 그대로** 옮긴다. 고치거나 줄이지 마라.
- 위에 없는 개념을 새로 만들지 마라.
- 한 문항짜리 개념도 버리지 마라. 그게 어디가 얇은지 보여 주는 것이다.
- 갈래와 축 이름은 한국어로. 널리 쓰이는 약어는 그대로 둔다.
- 웹 검색이나 파일 읽기를 하지 마라.
- 출력은 지정된 JSON 스키마뿐이다.
"""


def fingerprint(concepts) -> str:
    """개념 목록이 바뀌었는지 보는 지문. 안 바뀌었으면 다시 안 부른다."""
    h = hashlib.sha1()
    for c in sorted(set(concepts)):
        h.update(c.encode("utf-8") + b"\0")
    return h.hexdigest()[:16]


def _concepts(items: list):
    c = Counter()
    for it in items:
        for x in it.get("concepts") or []:
            if x and x.strip():
                c[x.strip()] += 1
    return c


def _lines(counts: Counter) -> str:
    return "\n".join("- %s (%d)" % (k, v) for k, v in counts.most_common())


def make(exam_title: str, items: list, model: str = "", timeout: int = 300) -> dict:
    """개념 → 3단계 위계. 모델이 빠뜨린 것은 코드가 주워 담는다."""
    counts = _concepts(items)
    if not counts:
        return {"branches": [], "fingerprint": "", "orphans": []}

    d = C.run(PROMPT % (exam_title, _lines(counts)), SCHEMA,
              model=model, timeout=timeout)

    # 모델은 개념을 빠뜨리거나 두 번 넣는다. 코드가 정리한다 —
    # 여기서 안 맞추면 축 길이의 합이 문항 수와 어긋난다.
    known = set(counts)
    used = set()
    branches = []
    for b in d.get("branches") or []:
        axes = []
        for a in b.get("axes") or []:
            cs = []
            for x in a.get("concepts") or []:
                x = (x or "").strip()
                if x in known and x not in used:
                    used.add(x)
                    cs.append(x)
            if cs:
                axes.append({"name": (a.get("name") or "?").strip()[:24],
                             "concepts": cs})
        if axes:
            branches.append({"name": (b.get("name") or "?").strip()[:24],
                             "axes": axes[:12]})

    orphans = sorted(known - used, key=lambda x: (-counts[x], x))
    if orphans and branches:
        # 버리지 않는다. 어디에도 안 붙은 개념이 있다는 사실 자체가 정보다.
        branches[-1]["axes"].append({"name": ORPHAN, "concepts": orphans})

    return {"branches": branches,
            "fingerprint": fingerprint(known),
            "orphans": orphans}


def axes_for(branches: list, items: list) -> list:
    """축마다 몇 문항인지. 문항이 그 축의 개념을 하나라도 가지면 센다."""
    at = {}
    for b in branches:
        for a in b["axes"]:
            for c in a["concepts"]:
                at[c] = (b["name"], a["name"])

    hit = defaultdict(set)
    for it in items:
        n = str(it.get("number"))
        for c in it.get("concepts") or []:
            k = at.get((c or "").strip())
            if k:
                hit[k].add(n)

    out = []
    for b in branches:
        axes = []
        for a in b["axes"]:
            ns = sorted(hit.get((b["name"], a["name"]), ()),
                        key=lambda x: int(x) if x.isdigit() else 0)
            axes.append({"name": a["name"], "value": len(ns), "numbers": ns,
                         "concepts": a["concepts"]})
        out.append({"subject": b["name"], "axes": axes,
                    "total": sum(a["value"] for a in axes)})
    return out


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save(path: str, d: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _canon(name: str) -> str:
    """띄어쓰기·대소문자·기호를 털어낸 비교용 열쇠."""
    import re
    import unicodedata

    return re.sub(r"[^0-9a-z가-힣]+", "",
                  unicodedata.normalize("NFKC", name or "").lower())


def unify(items: list) -> dict:
    """같은 말이 다르게 적힌 것을 하나로 모은다.

    "UCP 600" 과 "UCP600" 은 띄어쓰기만 다른 같은 개념인데 따로 세어졌다.
    3문항 · 3문항으로 갈려서 실제로는 6문항인 것이 안 보였다.

    뜻으로 같은 것(신용장 / L/C)까지는 여기서 손대지 않는다. 그건 판단이고,
    판단은 사람이나 모델이 할 일이다. 여기서는 **표기만** 맞춘다.

    돌려주는 것은 {적힌 이름: 대표 이름}. 자기 자신만 가리키면 넣지 않는다.
    """
    seen = Counter()
    for it in items:
        for c in it.get("concepts") or []:
            if c and c.strip():
                seen[c.strip()] += 1

    groups = defaultdict(list)
    for name in seen:
        groups[_canon(name)].append(name)

    alias = {}
    for names in groups.values():
        if len(names) < 2:
            continue
        # 많이 쓰인 표기를 대표로. 같으면 띄어 쓴 쪽이 읽기 좋다.
        best = sorted(names, key=lambda n: (-seen[n], " " not in n, n))[0]
        for n in names:
            if n != best:
                alias[n] = best
    return alias


def apply_unify(items: list, alias: dict) -> int:
    """문항의 개념 이름을 대표 이름으로 바꾼다. 바뀐 문항 수를 돌려준다."""
    if not alias:
        return 0
    n = 0
    for it in items:
        cs = it.get("concepts") or []
        if not cs:
            continue
        out, hit = [], False
        for c in cs:
            c2 = alias.get((c or "").strip(), (c or "").strip())
            if c2 != c:
                hit = True
            if c2 and c2 not in out:          # 합치다 보면 같은 게 둘 생긴다
                out.append(c2)
        if hit or len(out) != len(cs):
            it["concepts"] = out
            n += 1
    return n
