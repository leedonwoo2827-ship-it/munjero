# -*- coding: utf-8 -*-
"""문항을 구조화 마크다운으로.

items.json 은 기계가 읽는 것이다. 저자가 몇 주 뒤에 문제를 고치려면 사람이
읽고 고칠 수 있는 형태가 있어야 한다. 발문 · 지문 · 보기 · 해설로 나뉘고,
표 · 텍스트 · 수식 · 그림은 토큰으로 본문의 제자리에 놓인다.

    ## 12

    발문을 여기 적는다.

    {{t-1}} 를 넣은 자리에 표가 펼쳐진다.

    ① 첫 번째
    ② 두 번째

    ### 해설
    ...

    ### 자산
    {{t-1}} table
    | 계정 | 금액 |
"""
from __future__ import annotations

import io
import os

KIND_NAME = {"table": "표", "code": "박스", "math": "수식",
             "text": "텍스트", "figure": "그림"}
MARKS = "①②③④⑤⑥⑦⑧⑨⑩"


def _fence(kind: str) -> str:
    """자산 본문을 감쌀 울타리. 표는 마크다운 그대로 두어야 눈에 보인다."""
    return "" if kind == "table" else {"code": "sql", "math": "math"}.get(kind, "")


def asset_md(a: dict) -> str:
    """자산 하나를 사람이 읽을 수 있게. 되읽을 수 있어야 하므로 형식을 지킨다."""
    tok, kind = a.get("token") or "?", a.get("kind") or "text"
    head = "**{{%s}}** %s" % (tok, KIND_NAME.get(kind, kind))
    if kind == "figure":
        src = a.get("src") or ""
        cap = (a.get("caption") or "").strip()
        # 붙여넣은 그림은 data: 라 한 줄이 수십만 자가 된다. 파일에 그대로
        # 두면 사람이 읽을 수 없으므로 자리만 적고, 그림은 채점기가 싣는다.
        if src.startswith("data:"):
            return "%s\n\n_붙여넣은 그림_%s" % (head, ("  \n> " + cap) if cap else "")
        return "%s\n\n![%s](%s)%s" % (head, cap, src,
                                      ("  \n> " + cap) if cap else "")
    body = (a.get("md") or a.get("text") or "").rstrip()
    f = _fence(kind)
    if kind == "table":
        return "%s\n\n%s\n" % (head, body)
    return "%s\n\n```%s\n%s\n```\n" % (head, f, body)


def item_md(it: dict) -> str:
    """문항 하나."""
    o = ["## %s" % (it.get("number") or "?")]

    meta = []
    if it.get("subject"):
        meta.append(it["subject"])
    if it.get("answer_type") == "free":
        meta.append("채점 안 함")
    if it.get("answer_index") is not None:
        meta.append("정답 %s" % (MARKS[it["answer_index"]]
                                if it["answer_index"] < len(MARKS)
                                else it["answer_index"] + 1))
    if it.get("difficulty"):
        meta.append("난이도 %s" % it["difficulty"])
    if meta:
        o.append("`" + " · ".join(meta) + "`")

    # 발문 · 지문 · 보기 · 해설 순. 사람이 읽는 순서이자 해설을 쓸 때
    # 무엇을 묻는지부터 보게 되는 순서다.
    o.append("### 발문\n\n" + (it.get("question") or "").rstrip())
    if it.get("passage"):
        o.append("### 지문\n\n" + it["passage"].rstrip())

    if it.get("code"):
        o.append("```\n%s\n```" % it["code"].rstrip())

    if it.get("choices"):
        # 선지 수는 넷으로 정해져 있지 않다. 다섯일 수도, 참·거짓 둘일 수도 있다.
        lines = []
        for i, c in enumerate(it["choices"]):
            mk = (it.get("markers") or [None] * len(it["choices"]))[i] \
                or (MARKS[i] if i < len(MARKS) else str(i + 1))
            lines.append("%s %s" % (mk, c))
        o.append("### 보기\n\n" + "\n".join(lines))

    if it.get("explanation"):
        o.append("### 해설\n\n" + it["explanation"].rstrip())

    if it.get("assets"):
        o.append("### 자산\n\n"
                 + "\n\n".join(asset_md(a) for a in it["assets"]))

    # 원본에서 읽어 온 표·그림은 자산과 따로 온다. 빠뜨리면 안 되니 적어 둔다.
    extra = []
    if it.get("tables"):
        extra.append("표 %d개" % len(it["tables"]))
    if it.get("figures"):
        extra.append("그림 %d개" % len(it["figures"]))
    if extra:
        o.append("> 시험지에서 읽어 온 %s는 채점기에 그대로 실립니다."
                 % " · ".join(extra))

    return "\n\n".join(o)


def render(items_doc: dict) -> str:
    """시험 한 벌."""
    title = items_doc.get("exam_title") or items_doc.get("exam_id") or "시험"
    items = items_doc.get("items") or []
    # 이 파일은 내보내는 것이지 되읽는 것이 아니다. 고치면 반영된다고
    # 적어 두면 거짓말이 된다. 고치는 곳은 화면이다.
    o = ["# %s" % title,
         "문항 %d개. 화면에서 확정할 때마다 다시 만들어집니다 — "
         "고칠 곳은 화면이고, 이 파일은 읽고 넘기기 위한 것입니다." % len(items)]
    for it in items:
        o.append("---")
        o.append(item_md(it))
    return "\n\n".join(o) + "\n"


def write(items_doc: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "문항.md")
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(render(items_doc))
    os.replace(tmp, path)
    return path
