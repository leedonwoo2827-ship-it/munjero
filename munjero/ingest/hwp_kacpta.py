# -*- coding: utf-8 -*-
"""전산세무회계(한국세무사회) 계열 HWP → 구조화 노드.

이론 15문항(4지선다)과 실무 문제1~6(서술형)을 나눈다.
보기 표는 배치가 문항마다 다르다 — 마커만 든 칸이 따로 있기도 하고,
칸마다 마커+본문이 같이 있기도 하다. 두 경우를 모두 다룬다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import hwp_blocks as B

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
RE_THEORY = re.compile(r"^(\d{1,2})\.\s*(\S.*)$")
RE_TASK = re.compile(r"^\s*\[\s*(\d)\s*\]\s*(.*)$")
RE_TASKHEAD = re.compile(r"^\s*문제\s*(\d)\b\s*(.*)$")
GSO = "gso"


@dataclass
class Item:
    kind: str                       # 'theory' | 'practice'
    no: str
    stem: str = ""
    blocks: list = field(default_factory=list)   # Para/Table (지문·자료·표)
    choices: list = field(default_factory=list)
    markers: list = field(default_factory=list)
    task: str | None = None         # 실무: 소속 문제N
    todos: list = field(default_factory=list)


def _marker_only(text: str) -> bool:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return bool(lines) and all(len(l) == 1 and l in CIRCLED for l in lines)


def _lines(text):
    return [l.strip() for l in text.splitlines() if l.strip()]


def _markers_in(text):
    return [l for l in _lines(text) if len(l) == 1 and l in CIRCLED]


def extract_choices(table):
    """보기 표에서 (마커, 본문) 쌍을 뽑는다. 배치가 세 가지다.

    A — 마커 4개가 한 칸, 본문 4개가 다음 칸   (스트림 순서로 짝지으면 틀린다)
    B — 칸 하나에 "① 본문 ② 본문 …" 이 몰려 있음
    C — 마커 칸과 본문 칸이 번갈아 나옴 (1x8 표 등)
    """
    flat = [c for c in table.flat() if c.strip()]
    marks, bodies = [], []
    i, n = 0, len(flat)
    while i < n:
        cell = flat[i]
        mk = _markers_in(cell)
        # 칸 전체가 마커뿐이면 다음 칸이 본문이다 — A(여러 개) 와 C(한 개)를 같이 처리한다
        if mk and len(mk) == len(_lines(cell)) and i + 1 < n:
            lines = _lines(flat[i + 1])
            for j, m in enumerate(mk):
                marks.append(m)
                bodies.append(re.sub(r"\s+", " ", lines[j]).strip() if j < len(lines) else "")
            i += 2
            continue
        # 그 밖에는 칸 안에서 마커로 자른다
        for p in re.split(r"(?=[%s])" % CIRCLED, cell):
            p = p.strip()
            if p and p[0] in CIRCLED:
                marks.append(p[0])
                bodies.append(re.sub(r"\s+", " ", p[1:]).strip())
        i += 1
    return marks, bodies


def _is_choice_table(table) -> bool:
    txt = "\n".join(table.flat())
    return sum(1 for ch in CIRCLED[:4] if ch in txt) >= 3


NOTE_HINTS = ("기 본 전 제", "기본전제", "유의사항", "유 의 사 항")


def _is_note(table) -> bool:
    txt = "".join(table.flat())
    return any(h in txt for h in NOTE_HINTS)


def build_items(blocks):
    """블록 목록 → (문항, 안내표).

    안내표는 문항에 속하지 않지만 수험자에게 필요한 내용이다
    (실무 기본전제 · 입력 시 유의사항). 버리지 않고 따로 모아 돌려준다.
    """
    items = []
    notes = []
    cur = None
    cur_task = None
    mode = "front"                  # front → theory → practice

    def close():
        nonlocal cur
        if cur:
            items.append(cur)
            cur = None

    for b in blocks:
        if isinstance(b, B.Para):
            t = b.text.replace(GSO, "").strip()
            if not t:
                continue

            if "이론시험" in t or ("이 론" in t and "시험" in t):
                mode = "theory"
                continue
            if "실무시험" in t or ("실 무" in t and "시험" in t):
                close()
                mode = "practice"
                continue

            m = RE_TASKHEAD.match(t)
            if m and mode in ("theory", "practice"):
                close()
                mode = "practice"
                cur_task = "문제%s" % m.group(1)
                continue

            if mode == "practice":
                m = RE_TASK.match(t)
                if m:
                    close()
                    cur = Item(kind="practice", no="%s-%s" % (cur_task or "문제?", m.group(1)),
                               stem=m.group(2).strip(), task=cur_task)
                    continue

            m = RE_THEORY.match(t)
            if m and mode != "practice" and len(m.group(1)) <= 2:
                close()
                mode = "theory"
                cur = Item(kind="theory", no=m.group(1), stem=m.group(2).strip())
                continue

            if cur is not None:
                if cur.choices:
                    pass                     # 보기 뒤 꼬리말은 버리지 않고 지문으로
                cur.blocks.append(b) if cur.stem else None
                if not cur.blocks or cur.blocks[-1] is not b:
                    cur.blocks.append(b)
            continue

        # 표
        if cur is None:
            # 섹션 라벨이 표로 들어있어 mode 전환이 늦다. front 도 이론으로 본다.
            if _is_note(b):
                notes.append(("theory" if mode == "front" else mode, b))
            continue
        if cur.kind == "theory" and not cur.choices and _is_choice_table(b):
            marks, bodies = extract_choices(b)
            cur.markers, cur.choices = marks, bodies
            if len(bodies) != 4:
                cur.todos.append(("layout-ambiguous",
                                  "보기 %d개로 잡힘 — 표 배치 확인 필요" % len(bodies),
                                  "hwp:Section0#rec%d" % b.rec))
        else:
            cur.blocks.append(b)

    close()
    return items, notes
