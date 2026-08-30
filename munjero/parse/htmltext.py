# -*- coding: utf-8 -*-
"""HTML 에서 글자만 뽑는다 — 문항 확정 화면의 왼쪽에 놓을 원문.

정규식으로 태그를 지우면 <script> 안의 코드와 표의 칸 경계가 뭉개진다.
표준 파서로 훑으면서 블록마다 줄을 바꾸고, 표의 칸은 | 로 갈라 둔다.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

# meta 와 link 는 닫는 태그가 없다. 여기 넣으면 skip 이 올라간 채 안 내려와
# 그 뒤의 본문을 통째로 잃는다(실제로 13000자가 883자로 줄었다).
SKIP = {"script", "style", "head", "title"}
BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
         "section", "article", "table", "blockquote", "pre", "hr"}
CELL = "\t"          # 칸 경계. 빈 칸은 뒤에서 지운다


class _T(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "img":
            a = dict(attrs)
            src = a.get("src") or ""
            if src.startswith("data:"):
                src = "(붙임 그림)"
            self.out.append("\n[그림 %s]\n" % (a.get("alt") or src)[:60])
        elif tag in ("td", "th"):
            self.out.append(CELL)
        elif tag in BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK:
            self.out.append("\n")

    def handle_data(self, d):
        if not self.skip and d.strip():
            self.out.append(re.sub(r"[ \t]+", " ", d.strip()))


def to_text(html: str) -> str:
    p = _T()
    try:
        p.feed(html)
    except Exception:
        pass

    lines = []
    for raw in "".join(p.out).split("\n"):
        # 칸을 | 로 잇되 빈 칸은 버린다. 서식 표는 빈 칸이 대부분이라
        # 그대로 두면 "| | | |" 만 남아 원문이 안 보인다.
        cells = [c.strip() for c in raw.split(CELL)]
        lines.append(" | ".join(c for c in cells if c).strip())

    t = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return t.strip()
