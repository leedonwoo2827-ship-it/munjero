# -*- coding: utf-8 -*-
"""HWP 레코드 스트림 → 블록(문단 · 표 · 그림).

표는 반드시 셀 좌표(LIST_HEADER)로 배치한다. 스트림 순서로 짝지으면
"1×2 표에 왼쪽 칸 마커 4개 · 오른쪽 칸 텍스트 4개" 같은 배치에서 조용히 틀린다.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import hwp_ole as H


@dataclass
class Para:
    text: str
    level: int = 0


@dataclass
class Table:
    rows: int
    cols: int
    cells: list = field(default_factory=list)   # {row,col,row_span,col_span,text}
    rec: int = 0

    def grid(self):
        """행 우선으로 셀을 늘어놓는다. 병합 셀은 앞 셀이 자리를 먹는다."""
        taken = set()
        out = []
        by_pos = {(c["row"], c["col"]): c for c in self.cells}
        for r in range(self.rows):
            row = []
            for c in range(self.cols):
                if (r, c) in taken:
                    continue
                cell = by_pos.get((r, c))
                if cell is None:
                    continue
                for dr in range(cell["row_span"]):
                    for dc in range(cell["col_span"]):
                        taken.add((r + dr, c + dc))
                row.append(cell)
            out.append(row)
        return [r for r in out if r]

    def flat(self):
        """읽기 순서대로 셀 텍스트만. 문항 분절에서 쓴다."""
        return [c["text"] for r in self.grid() for c in r]


def build_blocks(records):
    """레코드 순서를 유지한 채 문단/표/그림 블록 목록을 만든다."""
    blocks = []
    i, n = 0, len(records)
    while i < n:
        tag, level, payload = records[i]

        if tag == H.CTRL_HEADER and H.ctrl_id(payload) == "tbl ":
            tbl, i = _read_table(records, i, level)
            if tbl:
                blocks.append(tbl)
            continue

        if tag == H.PARA_TEXT:
            t = H.para_text(payload).strip()
            if t:
                blocks.append(Para(t, level))
        i += 1
    return blocks


def _read_table(records, i, tbl_level):
    """i = CTRL_HEADER('tbl ') 위치. 표 끝 다음 인덱스를 함께 돌려준다."""
    start = i
    n = len(records)
    rows = cols = 0

    j = i + 1
    # 표 정의 레코드 — 공표된 상수를 믿지 말고 CTRL_HEADER 바로 뒤를 본다
    while j < n and records[j][1] > tbl_level:
        t, lv, p = records[j]
        if t not in (H.LIST_HEADER, H.PARA_TEXT) and len(p) >= 8:
            prop, r, c = struct.unpack_from("<IHH", p, 0)
            if 0 < r <= 200 and 0 < c <= 100:
                rows, cols = r, c
                j += 1
                break
        j += 1

    if not rows:
        return None, i + 1

    cells = []
    cur = None
    while j < n and records[j][1] > tbl_level:
        t, lv, p = records[j]
        if t == H.LIST_HEADER:
            info = H.cell_header(p)
            if info:
                cur = {"row": info["row"], "col": info["col"],
                       "row_span": info["row_span"], "col_span": info["col_span"],
                       "paras": []}
                cells.append(cur)
        elif t == H.PARA_TEXT and cur is not None:
            txt = H.para_text(p).strip()
            if txt:
                cur["paras"].append(txt)
        j += 1

    for c in cells:
        c["text"] = "\n".join(c["paras"])
    return Table(rows=rows, cols=cols, cells=cells, rec=start), j
