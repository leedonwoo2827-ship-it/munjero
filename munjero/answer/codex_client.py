# -*- coding: utf-8 -*-
"""Codex CLI 호출 — ChatGPT 구독 로그인만 쓴다. API 키 경로는 만들지 않는다."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile


class CodexError(RuntimeError):
    pass


class NotAuthenticated(CodexError):
    pass


# Windows 는 실행 정책이 기본 Restricted 라 npm 이 만든 codex.ps1 이
# PSSecurityException 으로 막힌다. .cmd 를 먼저 찾는다.
_CANDIDATES = ("codex.cmd", "codex.exe", "codex")
_FALLBACKS = (
    os.path.expandvars(r"%APPDATA%\npm\codex.cmd"),
    os.path.expandvars(r"%APPDATA%\npm\codex"),
    os.path.expanduser("~/.local/bin/codex"),
)


def find_codex() -> str:
    override = os.environ.get("CODEX_BIN")
    if override and os.path.isfile(override):
        return override
    for name in _CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    for p in _FALLBACKS:
        if p and os.path.isfile(p):
            return p
    raise CodexError(
        "codex CLI 를 찾지 못했습니다.\n"
        "  설치:  npm i -g @openai/codex\n"
        "  로그인: codex.cmd login")


def run(prompt: str, schema: dict | None = None, *, model: str = "",
        timeout: int = 300) -> dict | str:
    """codex exec 를 한 번 돌린다. schema 를 주면 JSON 객체를 돌려준다.

    -s read-only + 빈 작업 디렉토리로 도구 사용을 억제한다. codex 는 에이전트라
    놔두면 파일을 뒤지려 들고, 그만큼 느려지고 답이 흔들린다.
    """
    exe = find_codex()
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "last.txt")
        cmd = [exe, "exec", "--skip-git-repo-check", "--ephemeral",
               "-s", "read-only", "-C", td, "--color", "never",
               "-o", out]
        if schema is not None:
            sp = os.path.join(td, "schema.json")
            with open(sp, "w", encoding="utf-8") as f:
                json.dump(schema, f, ensure_ascii=False)
            cmd += ["--output-schema", sp]
        if model:
            cmd += ["-m", model]
        cmd += ["-"]

        try:
            r = subprocess.run(cmd, input=prompt.encode("utf-8"),
                               capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise CodexError("응답이 %d초를 넘겼습니다." % timeout)

        err = r.stderr.decode("utf-8", "replace")
        if r.returncode != 0 or not os.path.exists(out):
            low = err.lower()
            if "401" in err or "token" in low and "invalid" in low or "log in again" in low:
                raise NotAuthenticated(
                    "ChatGPT 로그인이 만료되었습니다.\n"
                    "  터미널에서:  codex.cmd login\n"
                    "  (codex login status 는 파일만 보고 만료를 못 잡습니다)")
            raise CodexError("codex 종료코드 %d\n%s" % (r.returncode, err[-1200:]))

        raw = open(out, encoding="utf-8").read()

    return _loads(raw) if schema is not None else raw.strip()


def _loads(raw: str) -> dict:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1].rsplit("```", 1)[0]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < 0:
        raise CodexError("응답에서 JSON 을 찾지 못했습니다:\n" + raw[:600])
    return json.loads(s[i:j + 1])


def smoke() -> str:
    """파일 검사를 믿지 않고 실제로 한 번 부딪혀 본다.

    codex login status 도, auth.json 의 access_token 존재 확인도 만료를 못 잡는다.
    둘 다 '로그인됨' 이라고 답하면서 실제 호출은 401 로 죽는다.
    """
    return run("Reply with exactly: PONG", timeout=120)
