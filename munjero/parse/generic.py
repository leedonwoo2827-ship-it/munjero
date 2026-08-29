# -*- coding: utf-8 -*-
"""아무 데서나 내보낸 HTML 에서 문항을 잡아낸다.

워드·한글·구글독스·브라우저 저장본은 마크업이 제각각이다. 클래스도 없고,
문단 하나가 <p> 일 수도 <div> 일 수도 표 안의 칸일 수도 있다.
그래서 **글의 생김새**로만 판단한다 — 번호로 시작하면 문항, 원문자로
시작하면 보기, 그 사이는 지문.

munjero 규약 클래스(.question 등)가 있으면 그쪽이 먼저다. 이건 없을 때의 길이다.
"""
from __future__ import annotations

import re

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
# "1." "1)" "1 ." "문 1." — 뒤에 글이 붙어 있어야 문항으로 본다
RE_Q = re.compile(r"^\s*(?:문\s*)?(\d{1,3})\s*[.)]\s*(\S.*)$", re.S)
RE_Q_BARE = re.compile(r"^\s*(?:문\s*)?(\d{1,3})\s*[.)]\s*$")
RE_CH = re.compile(r"^\s*([%s])\s*(.*)$" % CIRCLED, re.S)
RE_CH_NUM = re.compile(r"^\s*\(?([1-9])\s*[.)]\s+(\S.*)$", re.S)
# 오피스가 뱉는 껍데기 — 내용이 아니다
DROP = {"script", "style", "head", "meta", "link", "title", "o:p"}


def _text(node) -> str:
    for br in node.find_all("br"):
        br.replace_with("\n")
    s = node.get_text("\n")
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def _blocks(soup):
    """문서 순서대로 '한 덩어리'씩 내놓는다. 표는 통째로, 나머지는 문단으로."""
    body = soup.body or soup
    out = []
    seen = set()

    for el in body.find_all(["p", "div", "li", "h1", "h2", "h3", "h4",
                             "table", "img", "pre"]):
        if el.name in DROP:
            continue
        if any(id(a) in seen for a in el.parents):
            continue

        if el.name == "table":
            seen.add(id(el))
            out.append(("table", el))
            continue
        if el.name == "img":
            out.append(("img", el))
            continue
        if el.name == "pre":
            seen.add(id(el))
            out.append(("code", el))
            continue
        # 표나 pre 를 품고 있으면 그 자식들이 따로 나오게 둔다
        if el.find(["table", "pre"]):
            continue
        t = _text(el)
        if t:
            out.append(("text", t))
    return out


def _split_choices(text: str):
    """한 줄에 보기가 여러 개 눌려 있는 경우를 가른다."""
    parts = re.split(r"(?=[%s])" % CIRCLED, text)
    got = []
    for p in parts:
        p = p.strip()
        if p and p[0] in CIRCLED:
            got.append((p[0], re.sub(r"\s+", " ", p[1:]).strip()))
    return got


def looks_generic(soup) -> bool:
    """munjero 규약 마크업이 없으면 True."""
    return not soup.select(".question, .exam .item, article.item")


def parse(soup, table_fn):
    """(items, warnings) 를 돌려준다. table_fn 은 <table> → 표 딕셔너리."""
    items = []
    cur = None
    mode = None
    warns = []

    def close():
        nonlocal cur
        if cur and (cur["question"] or cur["choices"]):
            items.append(cur)
        cur = None

    for kind, node in _blocks(soup):
        if kind == "table":
            t = table_fn(node)
            if cur is None:
                continue
            # 보기가 표 안에 들어 있는 경우가 흔하다(한글 문서)
            flat = " ".join(c.get("t", "") for c in (t or {}).get("cells", []))
            if not cur["choices"] and sum(1 for c in CIRCLED[:4] if c in flat) >= 3:
                for c in (t or {}).get("cells", []):
                    for mk, body in _split_choices(c.get("t", "")):
                        cur["markers"].append(mk)
                        cur["choices"].append(body)
                mode = "choice"
            elif t:
                cur["tables"].append(t)
            continue

        if kind == "img":
            if cur is not None:
                src = node.get("src", "")
                if src:
                    cur["figures"].append(src)
            continue

        if kind == "code":
            if cur is not None:
                cur["code"] = (cur["code"] or "") + _text(node)
            continue

        text = node

        # 보기 — 원문자가 가장 확실한 신호다
        if cur is not None and RE_CH.match(text):
            for mk, body in _split_choices(text):
                cur["markers"].append(mk)
                cur["choices"].append(body)
            mode = "choice"
            continue

        # 새 문항 — 번호가 직전 번호 +1 일 때만 받는다.
        # 그래야 "2010 rules" 같은 게 문항으로 안 잡힌다.
        m = RE_Q.match(text) or RE_Q_BARE.match(text)
        if m:
            no = int(m.group(1))
            # 기대값은 **지금 쓰고 있는 문항** 기준이다. 아직 닫히지 않았으므로
            # items 의 마지막을 보면 한 칸씩 밀려서 3번부터 통째로 놓친다.
            last = cur["_no"] if cur else (items[-1]["_no"] if items else None)
            expected = (last + 1) if last is not None else None
            ok = expected is None or no == expected or no == 1
            if ok:
                close()
                rest = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else ""
                cur = {"_no": no, "number": str(no), "question": rest, "passage": "",
                       "choices": [], "markers": [], "tables": [], "figures": [],
                       "code": None}
                mode = "stem"
                continue

        if cur is None:
            continue

        # 보기 다음에 오는 줄은 그 보기의 이어짐으로 본다
        if mode == "choice" and cur["choices"]:
            m2 = RE_CH_NUM.match(text)
            if m2:                                   # "1) …" 형태의 보기
                cur["markers"].append(CIRCLED[int(m2.group(1)) - 1])
                cur["choices"].append(m2.group(2).strip())
            else:
                cur["choices"][-1] += " " + text
            continue

        if mode == "stem" and not cur["question"]:
            cur["question"] = text
        elif mode == "stem" and len(cur["question"]) < 160 and not cur["passage"]:
            cur["question"] += " " + text
        else:
            cur["passage"] = (cur["passage"] + "\n" + text).strip()
            mode = "passage"

    close()

    for it in items:
        it.pop("_no", None)
        n = len(it["choices"])
        it["warnings"] = []
        if n == 0:
            it["answer_type"] = "free"
        else:
            it["answer_type"] = "single"
            if n != 4:
                it["warnings"].append("choices_count=%d" % n)
    if not items:
        warns.append("문항을 하나도 찾지 못했습니다")
    return items, warns
