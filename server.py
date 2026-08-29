# -*- coding: utf-8 -*-
"""문제로 — 로컬 웹 화면 (server.py).

콘솔로도 다 되지만, 쓰는 사람이 개발자가 아니다. 검은 창에 y 를 치라고 하면
거기서 멈춘다. 특히 **매핑 확인**은 눈으로 보고 손으로 고쳐야 하는 일이라
화면이 있어야 제대로 된다 — 이 앱의 존재 이유가 그 화면이다.

LLM 호출은 Codex CLI(ChatGPT 로그인)에 위임한다. API 키를 쓰지 않는다.
"""
from __future__ import annotations

import mimetypes
import os


def _fix_mime():
    """윈도우 레지스트리가 .js 를 엉뚱한 타입으로 매핑해 두면 화면이 뜨고도 안 돈다."""
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/css", ".css")


_fix_mime()

from fastapi import FastAPI                     # noqa: E402
from fastapi.responses import FileResponse      # noqa: E402
from fastapi.staticfiles import StaticFiles     # noqa: E402

from munjero import config as CFG               # noqa: E402
from routes.api import router as api_router     # noqa: E402

STATIC = os.path.join(CFG.REPO, "static")

app = FastAPI(title="문제로", description="시험지를 채점기로", version="1.0")
app.include_router(api_router)

app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/favicon.ico")
def favicon():
    """브라우저가 무조건 찾는다. 없으면 콘솔이 404 로 지저분해진다."""
    return FileResponse(os.path.join(STATIC, "favicon.svg"),
                        media_type="image/svg+xml")
