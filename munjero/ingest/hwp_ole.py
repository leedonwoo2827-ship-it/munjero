# -*- coding: utf-8 -*-
"""HWP 5.x 리더 — 표준 라이브러리만 쓴다.

olefile · pyhwp · 한글 · LibreOffice 어느 것도 필요 없다.
OLE 복합문서(CFB)를 직접 열고, BodyText 섹션을 zlib 로 풀고, 레코드를 훑는다.

레코드 헤더는 u32 하나에 눌려 있다:  tag = v & 0x3FF,  level = (v>>10) & 0x3FF,
size = (v>>20) & 0xFFF.  size 가 0xFFF 면 뒤따르는 u32 가 진짜 크기다.
"""
from __future__ import annotations

import struct
import zlib

# 레코드 태그
PARA_HEADER = 66
PARA_TEXT = 67
CTRL_HEADER = 71
LIST_HEADER = 72

FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE


# ── OLE 복합문서 ──────────────────────────────────────────────────────────
class Ole:
    def __init__(self, data: bytes):
        if data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            raise ValueError("OLE 복합문서가 아닙니다 (HWP 5.x 가 아님)")
        self.d = data
        self.ssz = 1 << struct.unpack_from("<H", data, 30)[0]
        self.mssz = 1 << struct.unpack_from("<H", data, 32)[0]
        self.n_fat = struct.unpack_from("<I", data, 44)[0]
        self.dir_start = struct.unpack_from("<I", data, 48)[0]
        self.cutoff = struct.unpack_from("<I", data, 56)[0]
        self.mini_start = struct.unpack_from("<I", data, 60)[0]
        self.difat_start = struct.unpack_from("<I", data, 68)[0]
        self.n_difat = struct.unpack_from("<I", data, 72)[0]
        self._fat = self._build_fat()
        self._dir = self._read_dir()
        self._minifat = self._build_minifat()
        self._ministream = self._read_ministream()

    def _sector(self, sid: int) -> bytes:
        off = 512 + sid * self.ssz
        return self.d[off:off + self.ssz]

    def _chain(self, sid: int, fat) -> list:
        out = []
        seen = set()
        while sid not in (ENDOFCHAIN, FREESECT) and sid < len(fat):
            if sid in seen:
                break
            seen.add(sid)
            out.append(sid)
            sid = fat[sid]
        return out

    def _build_fat(self) -> list:
        # DIFAT: 헤더에 109개가 인라인, 나머지는 섹터로 이어진다
        difat = list(struct.unpack_from("<109I", self.d, 76))
        sid = self.difat_start
        for _ in range(self.n_difat):
            if sid in (ENDOFCHAIN, FREESECT):
                break
            sec = self._sector(sid)
            vals = struct.unpack("<%dI" % (self.ssz // 4), sec)
            difat.extend(vals[:-1])
            sid = vals[-1]
        fat = []
        for s in difat[:self.n_fat]:
            if s in (ENDOFCHAIN, FREESECT):
                continue
            fat.extend(struct.unpack("<%dI" % (self.ssz // 4), self._sector(s)))
        return fat

    def _build_minifat(self) -> list:
        mf = []
        for s in self._chain(self.mini_start, self._fat):
            mf.extend(struct.unpack("<%dI" % (self.ssz // 4), self._sector(s)))
        return mf

    def _read_dir(self) -> dict:
        entries = {}
        self._root = None
        for sid in self._chain(self.dir_start, self._fat):
            sec = self._sector(sid)
            for i in range(0, len(sec), 128):
                e = sec[i:i + 128]
                if len(e) < 128:
                    break
                nlen = struct.unpack_from("<H", e, 64)[0]
                if nlen < 2:
                    continue
                name = e[:nlen - 2].decode("utf-16-le", "ignore")
                typ = e[66]
                start = struct.unpack_from("<I", e, 116)[0]
                size = struct.unpack_from("<Q", e, 120)[0]
                if typ == 5:
                    self._root = (start, size)
                elif typ == 2:
                    entries.setdefault(name, (start, size))
        return entries

    def _read_ministream(self) -> bytes:
        if not self._root:
            return b""
        start, size = self._root
        out = b"".join(self._sector(s) for s in self._chain(start, self._fat))
        return out[:size]

    def names(self) -> list:
        return sorted(self._dir)

    def read(self, name: str) -> bytes:
        # 디렉토리를 평면으로 읽으므로 "BodyText/Section0" 도 "Section0" 로 받아준다
        if name not in self._dir and "/" in name:
            name = name.rsplit("/", 1)[-1]
        if name not in self._dir:
            raise KeyError(name)
        start, size = self._dir[name]
        if size < self.cutoff:
            out = b""
            for s in self._chain(start, self._minifat):
                off = s * self.mssz
                out += self._ministream[off:off + self.mssz]
            return out[:size]
        out = b"".join(self._sector(s) for s in self._chain(start, self._fat))
        return out[:size]


# ── HWP 문서 계층 ─────────────────────────────────────────────────────────
def file_header(b: bytes) -> dict:
    props = struct.unpack_from("<I", b, 36)[0]
    ver = struct.unpack_from("<4B", b, 32)
    return {
        "signature": b[:17].decode("ascii", "ignore"),
        "version": "%d.%d.%d.%d" % (ver[3], ver[2], ver[1], ver[0]),
        "compressed": bool(props & 0x01),
        "encrypted": bool(props & 0x02),
        "distributed": bool(props & 0x04),
    }


def decompress(raw: bytes, compressed: bool) -> bytes:
    return zlib.decompress(raw, -15) if compressed else raw


def iter_records(buf: bytes):
    i, n = 0, len(buf)
    while i + 4 <= n:
        v = struct.unpack_from("<I", buf, i)[0]
        tag = v & 0x3FF
        level = (v >> 10) & 0x3FF
        size = (v >> 20) & 0xFFF
        i += 4
        if size == 0xFFF:
            size = struct.unpack_from("<I", buf, i)[0]
            i += 4
        yield tag, level, buf[i:i + size]
        i += size


# 문단 텍스트 안의 제어문자. 확장/인라인은 8워드(16바이트)를 차지한다.
_CTRL_EXTENDED = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}
_CTRL_INLINE = {4, 5, 6, 7, 8, 9, 19, 20}
GSO = "gso"


def para_text(payload: bytes) -> str:
    out = []
    i, n = 0, len(payload) - 1
    while i < n:
        c = struct.unpack_from("<H", payload, i)[0]
        if c in _CTRL_EXTENDED:
            if c == 11:
                out.append(GSO)          # 그리기 개체 앵커 — 자리를 남긴다
            i += 16
        elif c in _CTRL_INLINE:
            if c == 9:
                out.append("\t")
            i += 16
        elif c < 32:
            if c in (10, 13):
                out.append("\n")
            i += 2
        else:
            out.append(chr(c))
            i += 2
    return "".join(out)


def cell_header(payload: bytes) -> dict:
    """표 셀의 LIST_HEADER. 스트림 순서가 아니라 이 좌표로 배치해야 한다."""
    if len(payload) < 16:
        return {}
    n_paras = struct.unpack_from("<H", payload, 0)[0]
    col, row, cspan, rspan = struct.unpack_from("<4H", payload, 8)
    return {"n_paras": n_paras, "col": col, "row": row,
            "col_span": cspan or 1, "row_span": rspan or 1}


def ctrl_id(payload: bytes) -> str:
    """CTRL_HEADER 의 ctrl id 는 리틀엔디언이라 뒤집혀 저장된다."""
    return payload[:4][::-1].decode("ascii", "ignore") if len(payload) >= 4 else ""


def bin_data(raw: bytes) -> tuple:
    """BinData 압축은 항목별이다. 전역 플래그를 믿지 말고 매직바이트로 확정한다."""
    for cand in (lambda: zlib.decompress(raw, -15), lambda: raw):
        try:
            b = cand()
        except Exception:
            continue
        if b[:2] == b"BM":
            return b, "bmp"
        if b[:8] == b"\x89PNG\r\n\x1a\n":
            return b, "png"
        if b[:3] == b"\xff\xd8\xff":
            return b, "jpg"
        if b[:3] == b"GIF":
            return b, "gif"
    return raw, "bin"
