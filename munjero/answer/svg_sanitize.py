# -*- coding: utf-8 -*-
"""모델이 만든 SVG를 화면에 넣기 전에 거른다.

해설은 전부 이스케이프해서 렌더한다. SVG만 예외로 날것을 넣으므로,
여기가 유일한 신뢰 경계다. 허용 목록에 없는 것은 전부 버린다
(차단 목록 방식은 새 공격 표면이 생길 때마다 뚫린다).
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

# 도형과 글자만. script·style·foreignObject·image·use·a 는 넣지 않는다.
ALLOWED_TAGS = {
    "svg", "g", "defs", "marker", "title", "desc",
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan",
}

COMMON_ATTRS = {
    "id", "class", "transform", "fill", "fill-opacity", "fill-rule",
    "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
    "stroke-dasharray", "stroke-opacity", "opacity", "clip-rule",
    "font-size", "font-weight", "font-family", "text-anchor",
    "dominant-baseline", "letter-spacing",
}

TAG_ATTRS = {
    "svg": {"viewBox", "viewbox", "width", "height", "xmlns", "role",
            "aria-label", "preserveAspectRatio", "preserveaspectratio"},
    "path": {"d"},
    "rect": {"x", "y", "width", "height", "rx", "ry"},
    "circle": {"cx", "cy", "r"},
    "ellipse": {"cx", "cy", "rx", "ry"},
    "line": {"x1", "y1", "x2", "y2"},
    "polyline": {"points"},
    "polygon": {"points"},
    "text": {"x", "y", "dx", "dy"},
    "tspan": {"x", "y", "dx", "dy"},
    "marker": {"markerWidth", "markerHeight", "markerwidth", "markerheight",
               "refX", "refY", "refx", "refy", "orient", "markerUnits", "markerunits"},
    "g": set(),
}

# 팔레트 토큰과 몇 가지 기본 색만. url(...) 은 marker 참조에만 쓰이므로 허용한다.
_SAFE_PAINT = re.compile(
    r"^(none|currentColor|transparent|#[0-9a-fA-F]{3,8}"
    r"|var\(--[a-z0-9-]+\)|url\(#[A-Za-z0-9_-]+\)"
    r"|rgba?\([\d\s.,%]+\))$")
_SAFE_NUM = re.compile(r"^[-+0-9.eE\s,%pxremt]*$")
_SAFE_TRANSFORM = re.compile(r"^[a-zA-Z0-9\s(),.\-+]*$")

MAX_BYTES = 24_000
MAX_NODES = 400


class Rejected(ValueError):
    pass


def _clean_attr(tag_name: str, name: str, value: str):
    n = name.lower()
    if n.startswith("on") or n in ("href", "xlink:href", "style", "srcset", "src"):
        return None
    allowed = COMMON_ATTRS | TAG_ATTRS.get(tag_name, set())
    if name not in allowed and n not in {a.lower() for a in allowed}:
        return None
    v = (value or "").strip()
    low = v.lower()
    if "javascript:" in low or "data:" in low or "expression(" in low or "<" in v:
        return None
    if n in ("fill", "stroke"):
        return v if _SAFE_PAINT.match(v) else None
    if n == "transform":
        return v if _SAFE_TRANSFORM.match(v) else None
    if n in ("d", "points"):
        return v if re.match(r"^[-+0-9.eE\s,a-zA-Z]*$", v) else None
    if n == "class":
        return v if re.match(r"^[A-Za-z0-9 _-]*$", v) else None
    return v


def sanitize(svg: str):
    """통과하면 정제된 SVG 문자열, 아니면 None 을 돌려준다."""
    if not svg or not svg.strip():
        return None
    raw = svg.strip()
    if len(raw.encode("utf-8")) > MAX_BYTES:
        return None
    if "<svg" not in raw.lower():
        return None

    soup = BeautifulSoup(raw, "lxml-xml")
    root = soup.find("svg")
    if root is None:
        soup = BeautifulSoup(raw, "html.parser")
        root = soup.find("svg")
    if root is None:
        return None

    nodes = 0
    for el in list(root.find_all(True)) + [root]:
        nodes += 1
        if nodes > MAX_NODES:
            return None
        name = el.name.split(":")[-1]
        if name not in ALLOWED_TAGS:
            el.decompose()
            continue
        el.name = name
        keep = {}
        for k, v in list(el.attrs.items()):
            cleaned = _clean_attr(name, k, v if isinstance(v, str) else " ".join(v))
            if cleaned is not None:
                keep[k] = cleaned
        el.attrs = keep

    # 좌표계가 없으면 반응형으로 못 만든다
    vb = root.get("viewBox") or root.get("viewbox")
    if not vb or not _SAFE_NUM.match(vb):
        return None
    root.attrs.pop("width", None)
    root.attrs.pop("height", None)
    root["viewBox"] = vb
    root.attrs.pop("viewbox", None)
    root["xmlns"] = "http://www.w3.org/2000/svg"
    root["class"] = "q-diagram__svg"

    out = str(root)
    low = out.lower()
    if "<script" in low or "onload" in low or "javascript:" in low:
        return None
    return out
