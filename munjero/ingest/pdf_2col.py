# -*- coding: utf-8 -*-
"""무역영어 계열(상공회의소 2단 조판) PDF → 구조화 노드.

역할 판별이 폰트+x0 로 결정적이라 휴리스틱이 필요 없다.
  발문        Batang 10.7  x0 19.8 / 308.7
  그룹헤더    Gulim  10.7  x0 19.8 / 308.7   ← 발문과 x0 가 같고 폰트로만 갈린다
  보기        Gulim  10.8  x0 36.8 / 325.7   ← 줄바꿈된 보기 본문은 Batang 으로 바뀐다
  지문        Batang 10.8  글상자(벡터 사각형) 안
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

import fitz

SPLIT_X = 270.0          # 2단 경계. 페이지 폭 595pt, 세로 괘선이 x=297.4 에 있다
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
RE_STEM = re.compile(r"^(\d{1,3})\.")
RE_GROUP = re.compile(r"^\[\s*(\d{1,3})\s*[~\-–]\s*(\d{1,3})\s*\]")
RE_SECTION = re.compile(r"[<〈]\s*제\s*(\d)\s*과목\s*[>〉]\s*(.*)")


# ── 데이터 ────────────────────────────────────────────────────────────────
@dataclass
class Line:
    page: int
    col: int
    y: float
    x0: float
    text: str
    font: str
    size: float
    boxed: bool = False
    image: str | None = None
    box: tuple | None = None        # 이 줄을 감싼 글상자 (잘라내기용)


@dataclass
class Question:
    no: int
    page: int
    stem: str = ""
    passage: list = field(default_factory=list)
    choices: list = field(default_factory=list)
    markers: list = field(default_factory=list)
    group: str | None = None
    section_no: int | None = None
    section: str | None = None
    todos: list = field(default_factory=list)
    capture: tuple | None = None    # (page, x0, y0, x1, y1) — 원본 조각 이미지
    figures: list = field(default_factory=list)


@dataclass
class Group:
    covers: tuple
    directive: str = ""
    passage: list = field(default_factory=list)
    capture: tuple | None = None    # (page, x0, y0, x1, y1) — 공유지문 글상자
    figures: list = field(default_factory=list)


# ── 공백 복원 ─────────────────────────────────────────────────────────────
def _is_subset(font: str) -> bool:
    """T3/T5/T7/T9 같은 서브셋 폰트는 공백 글리프를 안 내보낸다."""
    return len(font) > 1 and font[0] == "T" and font[1:].isdigit()


def span_text(span) -> str:
    """rawdict 는 span 에 chars 만 준다. 문자에서 텍스트를 만들되,
    서브셋 폰트(T3/T5/…)일 때만 좌표 간격으로 공백을 복원한다."""
    chars = span.get("chars")
    if not chars:
        return span.get("text", "")
    subset = _is_subset(span["font"])
    thr = 0.25 * span["size"]
    out, prev = [], None
    for c in chars:
        if subset and prev is not None and c["bbox"][0] - prev > thr            and not c["c"].isspace() and (not out or not out[-1].isspace()):
            out.append(" ")
        out.append(c["c"])
        prev = c["bbox"][2]
    return "".join(out)


# ── 글상자 검출 ───────────────────────────────────────────────────────────
def passage_boxes(page) -> list:
    """지문 글상자는 진짜 벡터 사각형이다. 수평선을 x-범위로 짝지어 복원한다."""
    horiz = []
    for d in page.get_drawings():
        for item in d["items"]:
            if item[0] != "l":
                continue
            p1, p2 = item[1], item[2]
            if abs(p1.y - p2.y) < 0.6 and abs(p2.x - p1.x) > 60:
                horiz.append((round(min(p1.x, p2.x), 1), round(max(p1.x, p2.x), 1),
                              round(p1.y, 1)))
    byspan = defaultdict(list)
    for x0, x1, y in horiz:
        byspan[(x0, x1)].append(y)
    boxes = []
    for (x0, x1), ys in byspan.items():
        ys = sorted(set(ys))
        for i in range(0, len(ys) - 1):
            top, bot = ys[i], ys[i + 1]
            if 12 < bot - top < 460:
                boxes.append((x0, top, x1, bot))
                break
    return boxes


def in_box(x, y, boxes):
    """줄이 들어 있는 글상자를 돌려준다. 없으면 None."""
    for b in boxes:
        bx0, by0, bx1, by1 = b
        if bx0 - 3 <= x <= bx1 + 3 and by0 + 1 < y < by1 - 1:
            return b
    return None


# ── 페이지 → 줄 ───────────────────────────────────────────────────────────
def page_lines(doc, pno: int) -> list:
    page = doc[pno]
    boxes = passage_boxes(page)
    buckets = defaultdict(list)

    raw = page.get_text("rawdict")
    for b in raw["blocks"]:
        if b.get("type") == 1:               # 이미지 블록
            x0, y0, x1, y1 = b["bbox"]
            key = (0 if x0 < SPLIT_X else 1, round(y0, 0))
            buckets[key].append((x0, "\uE000IMG\uE001", "IMAGE", 0.0, b["bbox"]))
            continue
        for l in b.get("lines", []):
            for s in l["spans"]:
                t = span_text(s)
                if not t.strip():
                    continue
                x0 = s["bbox"][0]
                key = (0 if x0 < SPLIT_X else 1, round(s["bbox"][1], 0))
                buckets[key].append((x0, t, s["font"], s["size"], s["bbox"]))

    lines = []
    for (col, y), parts in sorted(buckets.items(), key=lambda k: (k[0][0], k[0][1])):
        parts.sort(key=lambda p: p[0])
        text = " ".join(p[1].strip() for p in parts).strip()
        text = re.sub(r"\s{2,}", " ", text)
        if re.fullmatch(r"-\s*\d+\s*-", text):        # 페이지 푸터
            continue
        img = "\uE000IMG\uE001" in text
        text = text.replace("\uE000IMG\uE001", "").strip()
        lead = parts[0]
        b = in_box(lead[0], y, boxes)
        lines.append(Line(pno, col, y, lead[0], text, lead[2], lead[3],
                          boxed=b is not None, box=b,
                          image="inline" if img else None))
    return lines


def document_lines(doc, first=1) -> list:
    """모든 페이지를 읽기 순서로 이어붙인다. 페이지를 넘는 공유지문이 이걸로 산다."""
    out = []
    for pno in range(first, doc.page_count):
        out.extend(page_lines(doc, pno))
    return out


# ── 줄 → 문항 ─────────────────────────────────────────────────────────────
def _split_inline_choices(text: str):
    """한 줄에 보기가 여러 개 눌려 있는 경우(2단 보기, Q39 처럼 4개 몰림)를 가른다."""
    parts = re.split(r"(?=[①-⑩])", text)
    out = []
    for p in parts:
        p = p.strip()
        if p and p[0] in CIRCLED:
            out.append((p[0], p[1:].strip()))
    return out


def build_items(lines: list):
    """섹션·그룹·문항 노드를 만든다. 판별 우선순위가 곧 규칙이다."""
    sections, groups, items = [], [], []
    cur_sec = None
    cur_grp = None
    cur = None
    mode = None                      # 'stem' | 'choice' | 'passage'

    def close():
        nonlocal cur
        if cur:
            items.append(cur)
            cur = None

    for ln in lines:
        t, f, x = ln.text, ln.font, ln.x0
        is_num_col = x < 25 or 305 < x < 316
        is_gulim = "Gulim" in f

        # 1) 과목 헤더 — 크기로 갈린다
        m = RE_SECTION.search(t)
        if m and ln.size > 13:
            close(); cur_grp = None
            cur_sec = (int(m.group(1)), m.group(2).strip() or f"제{m.group(1)}과목")
            sections.append(cur_sec)
            continue

        # 2) 그룹 헤더 — 발문과 x0 가 같고 폰트로만 갈린다
        m = RE_GROUP.match(t)
        if m and is_gulim and is_num_col:
            close()
            cur_grp = Group(covers=(int(m.group(1)), int(m.group(2))),
                            directive=t[m.end():].strip())
            groups.append(cur_grp)
            mode = "group"
            continue

        # 3) 새 보기 — Gulim 이면서 원문자로 시작할 때만
        if cur and is_gulim and t and t[0] in CIRCLED:
            for mk, body in _split_inline_choices(t):
                cur.markers.append(mk)
                cur.choices.append(body)
            mode = "choice"
            continue

        # 4) 발문 — Batang + 번호단 + "N."
        m = RE_STEM.match(t)
        if m and "Batang" in f and is_num_col and not ln.boxed:
            close()
            no = int(m.group(1))
            cur = Question(no=no, page=ln.page)
            if cur_sec:
                cur.section_no, cur.section = cur_sec
            if cur_grp and cur_grp.covers[0] <= no <= cur_grp.covers[1]:
                cur.group = "%d-%d" % cur_grp.covers
            rest = t[m.end():].strip()
            if rest:
                cur.stem = rest
            mode = "stem"
            if ln.image:
                cur.todos.append(("inline-image", "글리프가 비트맵으로 렌더됨",
                                  f"pdf:p{ln.page}"))
            continue

        # 5) 이어지는 줄
        if ln.image and cur:
            cur.todos.append(("inline-image", "글리프가 비트맵으로 렌더됨",
                              f"pdf:p{ln.page}"))
            # 글자 하나를 잘라봐야 쓸모없다. 지문 글상자를 통째로 남긴다.
            if ln.box and not cur.capture:
                cur.capture = (ln.page,) + tuple(ln.box)
        if mode == "group" and cur_grp is not None:
            # 지시문이 줄바꿈되면 글상자 밖에 남는다. 글상자에 들어가야 지문이다.
            if ln.boxed or cur_grp.passage:
                cur_grp.passage.append(t)
                # 공유지문 글상자도 원본 모양 그대로 남긴다 — 편지·서식은 배치가 정보다
                if ln.box and not cur_grp.capture:
                    cur_grp.capture = (ln.page,) + tuple(ln.box)
            else:
                cur_grp.directive = (cur_grp.directive + " " + t).strip()
        elif cur is None:
            continue
        elif mode == "choice":
            if cur.choices:
                cur.choices[-1] += " " + t
        elif ln.boxed:
            cur.passage.append(t)
            mode = "passage"
        elif mode == "passage":
            cur.passage.append(t)
        else:
            cur.stem = (cur.stem + " " + t).strip()

    close()
    return sections, groups, items


def capture_regions(doc, items, groups, out_dir, zoom: float = 2.5) -> int:
    """원본 글상자를 그림으로 남긴다.

    두 경우에 쓴다.
      · 글리프가 비트맵으로 그려져 텍스트로 복원할 방법이 없는 문항
      · 여러 문항이 공유하는 지문 — 편지·서식은 줄바꿈과 배치 자체가 정보다
    버리는 대신 원본 모양 그대로 보여준다. 사람이 보면 바로 안다.
    """
    import os

    os.makedirs(out_dir, exist_ok=True)
    n = 0

    def shot(cap, name):
        pno, x0, y0, x1, y1 = cap
        rect = fitz.Rect(x0 - 4, y0 - 4, x1 + 4, y1 + 4)
        doc[pno].get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect)                 .save(os.path.join(out_dir, name))
        return "figs/" + name

    for g in groups or []:
        if g.capture:
            g.figures.append(shot(g.capture, "group%d-%d.png" % g.covers))
            n += 1
    for q in items:
        if q.capture:
            q.figures.append(shot(q.capture, "q%s-p%d.png" % (q.no, q.capture[0])))
            n += 1
    return n
