# -*- coding: utf-8 -*-
"""화면이 부르는 API.

핵심은 매핑 확인이다. 시험지에서 뽑아낸 문항을 사람이 보고 고친 뒤
**입력 확정**을 눌러야 정답 생성으로 넘어간다. 확정 전에는 막는다 —
자리가 틀린 채로 10~15분을 쓰는 일을 없애려는 것이다.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import traceback

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from munjero import config as CFG
from munjero.answer import batch, codex_client
from munjero.build import grader
from munjero.parse import html_to_items as P

router = APIRouter(prefix="/api")

INBOX = os.path.join(CFG.REPO, "input")
JOBS: dict = {}
_LOCK = threading.Lock()


# ── 공통 ──────────────────────────────────────────────────────────────────
def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _exam_or_404(exam_id):
    if not os.path.isdir(CFG.exam_dir(exam_id)):
        raise HTTPException(404, "그런 시험이 없습니다: %s" % exam_id)
    return CFG.paths(exam_id)


def _summary(exam_id):
    m = CFG.load_manifest(exam_id)
    p = CFG.paths(exam_id)
    st = m.get("stages", {})
    n_items = n_review = n_ans = 0
    if os.path.isfile(p["items"]):
        d = _load(p["items"])
        n_items = len(d["items"])
        n_review = sum(1 for i in d["items"] if i["needs_review"])
    if os.path.isfile(p["answers"]):
        n_ans = len(_load(p["answers"]).get("answers") or {})
    mf = p["manifest"]
    updated = os.path.getmtime(mf) if os.path.isfile(mf) else 0
    if os.path.isfile(p["grader"]):
        stage = "done"
    elif n_ans:
        stage = "answers"
    elif m.get("confirmed"):
        stage = "confirmed"
    else:
        stage = "mapping"
    return {
        "exam_id": exam_id,
        "title": m.get("title") or exam_id,
        "updated": updated,
        "stage": stage,
        "answers_confirmed": bool(m.get("answers_confirmed")),
        "source_file": m.get("source_file", ""),
        "confirmed": bool(m.get("confirmed")),
        "items": n_items,
        "needs_review": n_review,
        "answers": n_ans,
        "has_paper": bool(CFG.find_paper(exam_id)),
        "has_grader": os.path.isfile(p["grader"]),
        "stages": list(st),
    }


# ── 설정 · 실행현황 ───────────────────────────────────────────────────────
class OutRoot(BaseModel):
    path: str


@router.get("/settings")
def get_settings():
    return {"out_root": CFG.out_root(), "default": CFG.default_out_root(),
            "env_locked": bool(os.environ.get("MUNJERO_OUT")), "repo": CFG.REPO}


@router.post("/settings/out-root")
def set_out_root(body: OutRoot):
    if os.environ.get("MUNJERO_OUT"):
        raise HTTPException(400,
                            "MUNJERO_OUT 환경변수가 걸려 있어 화면에서 바꿀 수 없습니다.")
    try:
        p = CFG.set_out_root(body.path)
    except OSError as e:
        raise HTTPException(400, "그 위치에 폴더를 만들 수 없습니다: %s" % e)
    return {"out_root": p}


class CodexAct(BaseModel):
    action: str


@router.post("/codex")
def codex_action(body: CodexAct):
    """codex login / logout 을 새 콘솔 창에서 띄운다.

    로그인은 브라우저를 열고 사람의 승인을 기다린다. 서버가 그 프로세스를
    붙잡고 있으면 응답이 막히므로, 창을 따로 띄우고 바로 돌아온다.
    """
    import subprocess
    import sys

    act = (body.action or "").strip()
    if act not in ("login", "logout"):
        raise HTTPException(400, "login 또는 logout 만 됩니다.")
    try:
        exe = codex_client.find_codex()
    except codex_client.CodexError as e:
        raise HTTPException(400, str(e))
    try:
        if sys.platform == "win32":
            CREATE_NEW_CONSOLE = 0x00000010
            subprocess.Popen(["cmd", "/c", exe, act],
                             creationflags=CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen([exe, act])
    except Exception as e:      # noqa: BLE001
        raise HTTPException(500, "실행하지 못했습니다: %s" % e)
    return {"ok": True, "action": act}


@router.get("/codex/check")
def codex_check():
    """파일 검사를 믿지 않고 실제로 한 번 부딪혀 본다."""
    try:
        r = codex_client.smoke()
        return {"ok": True, "reply": r[:60]}
    except codex_client.NotAuthenticated as e:
        return {"ok": False, "need_login": True, "error": str(e)}
    except codex_client.CodexError as e:
        return {"ok": False, "need_login": False, "error": str(e)[:300]}


@router.get("/activity")
def activity(exam_id: str = ""):
    """우측 실행현황. 지금 무엇이 돌고 있고 무엇이 남아 있는지."""
    running = [{"exam_id": k, "done": v.get("done", 0), "total": v.get("total", 0),
                "error": v.get("error", "")}
               for k, v in JOBS.items() if v.get("running")]
    out = {"running": running, "out_root": CFG.out_root(), "stages": [], "log": []}
    if not exam_id:
        return out

    p = CFG.paths(exam_id)
    m = CFG.load_manifest(exam_id)
    st = m.get("stages", {})

    def size(path):
        return os.path.getsize(path) if os.path.isfile(path) else 0

    paper = CFG.find_paper(exam_id)
    n_items = st.get("02_items", {}).get("items", 0)
    n_ans = st.get("03_answers", {}).get("answers", 0)
    out["stages"] = [
        {"key": "00_source", "name": "원본", "ok": os.path.isdir(p["source"]),
         "note": m.get("source_file", "")},
        {"key": "01_paper", "name": "시험지 HTML", "ok": bool(paper),
         "note": ("%d KB" % (size(paper) // 1024)) if paper else ""},
        {"key": "02_items", "name": "문항", "ok": os.path.isfile(p["items"]),
         "note": ("%d문항" % n_items) if n_items else "",
         "gate": "확정됨" if m.get("confirmed") else "확정 대기"},
        {"key": "03_answers", "name": "정답·해설", "ok": os.path.isfile(p["answers"]),
         "note": ("%d개" % n_ans) if n_ans else "",
         "gate": "확정됨" if m.get("answers_confirmed") else "확정 대기"},
        {"key": "04_grader", "name": "채점기", "ok": os.path.isfile(p["grader"]),
         "note": ("%d KB" % (size(p["grader"]) // 1024))
                 if os.path.isfile(p["grader"]) else ""},
    ]
    hist = os.path.join(p["base"], "04_grader", "이전")
    out["versions"] = sorted(os.listdir(hist), reverse=True)[:8]         if os.path.isdir(hist) else []
    job = JOBS.get(exam_id)
    if job:
        out["log"] = (job.get("log") or [])[-12:]
        out["job"] = {"running": job.get("running"), "done": job.get("done", 0),
                      "total": job.get("total", 0), "error": job.get("error", "")}
    return out


# ── 상태 ──────────────────────────────────────────────────────────────────
@router.get("/health")
def health():
    try:
        exe = codex_client.find_codex()
        return {"ok": True, "codex": exe, "out_root": CFG.out_root()}
    except codex_client.CodexError as e:
        return {"ok": False, "codex": "", "error": str(e), "out_root": CFG.out_root()}


@router.get("/exams")
def exams(q: str = "", stage: str = "", limit: int = 0):
    """시험이 쌓이면 목록이 길어진다. 최근 순으로 주고, 검색·거르기를 받는다."""
    root = CFG.out_root()
    if not os.path.isdir(root):
        return {"exams": [], "total": 0}
    out = []
    for d in os.listdir(root):
        if os.path.isfile(os.path.join(root, d, "_exam.json")):
            out.append(_summary(d))
    total = len(out)
    if q:
        k = q.strip().lower()
        out = [e for e in out
               if k in e["title"].lower() or k in e["exam_id"].lower()]
    if stage:
        out = [e for e in out if e["stage"] == stage]
    out.sort(key=lambda e: e["updated"], reverse=True)
    if limit:
        out = out[:limit]
    return {"exams": out, "total": total}


@router.delete("/exam/{exam_id}")
def delete_exam(exam_id: str):
    """시험 폴더를 통째로 지운다. 되돌릴 수 없으므로 화면에서 한 번 더 묻는다."""
    p = _exam_or_404(exam_id)
    shutil.rmtree(p["base"], ignore_errors=True)
    return {"ok": True, "exam_id": exam_id}


@router.delete("/exams")
def delete_all():
    """만들어 둔 시험지를 전부 지운다. 화면에서 두 번 확인하고 부른다."""
    root = CFG.out_root()
    n = 0
    if os.path.isdir(root):
        for d in os.listdir(root):
            p = os.path.join(root, d)
            if os.path.isfile(os.path.join(p, "_exam.json")):
                shutil.rmtree(p, ignore_errors=True)
                n += 1
    return {"deleted": n}


@router.get("/exam/{exam_id}")
def exam(exam_id: str):
    _exam_or_404(exam_id)
    return _summary(exam_id)


# ── 1단계: 올리고 읽어내기 ────────────────────────────────────────────────
def _safe_name(raw: str) -> str:
    """올라온 파일 이름을 되살린다.

    한글 파일 이름은 클라이언트마다 다르게 실려 온다. 브라우저는 UTF-8 로 보내지만,
    어떤 경로로 오면 그 바이트가 latin-1 로 한 번 더 해석돼 "Ã¦120..." 처럼 깨지고,
    surrogate 가 섞이면 파일로 저장하는 순간 터진다. 여기서 한 번 되돌려 놓는다.
    """
    name = os.path.basename(raw or "")
    if not name:
        return ""

    # surrogate 가 섞였으면 원래 바이트를 되찾아 UTF-8 → CP949 순으로 시도한다
    if any("\ud800" <= c <= "\udfff" for c in name):
        b = name.encode("utf-8", "surrogateescape")
        for enc in ("utf-8", "cp949", "euc-kr"):
            try:
                return os.path.basename(b.decode(enc))
            except UnicodeDecodeError:
                continue
        return os.path.basename(b.decode("utf-8", "replace"))

    # 바이트를 latin-1 로 읽어 버린 흔한 형태. 되돌려서 **한글이 나오면** 채택한다.
    # 한글이 나왔다는 것 자체가 원래 인코딩을 맞게 짚었다는 증거다 —
    # 조건 없이 바꾸면 멀쩡한 라틴 문자 이름을 망친다.
    if not _has_hangul(name):
        try:
            raw_bytes = name.encode("latin-1")
        except UnicodeEncodeError:
            return name
        for enc in ("utf-8", "cp949", "euc-kr"):
            try:
                fixed = raw_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
            if _has_hangul(fixed):
                return os.path.basename(fixed)
    return name


def _has_hangul(s: str) -> bool:
    return any("가" <= c <= "힣" or "ㄱ" <= c <= "ㆎ" for c in s)


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    name = _safe_name(file.filename or "")
    ext = os.path.splitext(name)[1].lower()
    if ext not in (".html", ".htm", ".pdf", ".hwp", ".hwpx", ".docx", ".zip"):
        raise HTTPException(
            400,
            "HTML · 워드(.docx) · 한글(.hwp) · PDF 만 됩니다. 받은 것: %s\n"
            "  .doc 는 워드에서 .docx 로 저장한 뒤 다시 넣어 주세요."
            % (ext or "확장자 없음"))
    os.makedirs(INBOX, exist_ok=True)
    dest = os.path.join(INBOX, name)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    from munjero.ingest import slugify

    if ext == ".zip":
        try:
            dest = _unpack_zip(dest)
        except ValueError as e:
            raise HTTPException(400, str(e))
        name = os.path.basename(dest)

    exam_id = slugify(name)
    try:
        _do_map(dest, exam_id)
    except SystemExit as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, "읽어내지 못했습니다: %s" % e)
    return _summary(exam_id)


def _unpack_zip(zpath: str) -> str:
    """zip 을 풀고 그 안의 시험지 파일 경로를 돌려준다.

    "웹 페이지(완전)" 으로 저장하면 HTML 옆에 그림 폴더가 따로 생긴다.
    HTML 만 올리면 그림이 통째로 빠지므로, 폴더째 zip 으로 받는 길을 둔다.
    푼 자리에 그대로 두면 상대경로가 살아 있어서 그림이 붙는다.
    """
    import zipfile

    out = os.path.join(INBOX, os.path.splitext(os.path.basename(zpath))[0])
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out, exist_ok=True)

    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            # zip 안의 이름은 인코딩이 제각각이다. cp437 로 잘못 읽힌 한글을 되살린다.
            raw = info.filename
            if not info.flag_bits & 0x800:      # UTF-8 플래그가 없으면 cp437 로 읽힌 상태
                for enc in ("cp949", "euc-kr", "utf-8"):
                    try:
                        cand = raw.encode("cp437").decode(enc)
                        if any("가" <= c <= "힣" for c in cand):
                            raw = cand
                            break
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        continue
            rel = os.path.normpath(raw).lstrip("\\/")
            if rel.startswith("..") or os.path.isabs(rel):
                continue                        # zip 밖으로 나가는 경로는 버린다
            target = os.path.join(out, rel)
            os.makedirs(os.path.dirname(target) or out, exist_ok=True)
            with z.open(info) as fsrc, open(target, "wb") as fdst:
                shutil.copyfileobj(fsrc, fdst)

    # 시험지로 쓸 파일 하나를 고른다. 얕은 곳에 있는 것을 먼저 본다.
    best, best_depth = "", 99
    for root, _dirs, files in os.walk(out):
        depth = root[len(out):].count(os.sep)
        for f in files:
            e = os.path.splitext(f)[1].lower()
            if e not in (".html", ".htm", ".docx", ".hwp", ".hwpx", ".pdf"):
                continue
            rank = depth + (0 if e in (".html", ".htm") else 1)
            if rank < best_depth:
                best, best_depth = os.path.join(root, f), rank
    if not best:
        raise ValueError(
            "zip 안에서 시험지를 찾지 못했습니다.\n"
            "  HTML · 워드 · 한글 · PDF 중 하나가 들어 있어야 합니다.")
    return best


def _do_map(src, exam_id):
    """원본 → 시험지 HTML → 문항 JSON. 확정 상태는 지운다(내용이 바뀌었으므로)."""
    from munjero import ingest

    ext = os.path.splitext(src)[1].lower()
    paper_dir = CFG.stage(exam_id, "01_paper")
    title = os.path.splitext(os.path.basename(src))[0]

    if ext in (".pdf", ".hwp", ".hwpx", ".docx"):
        src_dir = CFG.stage(exam_id, "00_source")
        kept = os.path.join(src_dir, os.path.basename(src))
        if os.path.abspath(src) != os.path.abspath(kept):
            shutil.copy2(src, kept)
        r = ingest.extract(kept, paper_dir, exam_id=exam_id, title=title)
        final = os.path.join(paper_dir, "paper.html")
        if os.path.abspath(r["path"]) != os.path.abspath(final):
            os.replace(r["path"], final)
        paper = final
        dropped = r.get("dropped_figures") or []
    else:
        paper = os.path.join(paper_dir, "paper.html")
        if os.path.abspath(src) != os.path.abspath(paper):
            shutil.copy2(src, paper)
            figs = os.path.join(os.path.dirname(os.path.abspath(src)), "figs")
            if os.path.isdir(figs):
                shutil.copytree(figs, os.path.join(paper_dir, "figs"), dirs_exist_ok=True)
        dropped = []

    doc = P.parse_html(paper)
    p = CFG.paths(exam_id)
    os.makedirs(os.path.dirname(p["items"]), exist_ok=True)
    P.save(doc, p["items"])

    CFG.write_readme(exam_id, doc.get("exam_title") or title)
    m = CFG.load_manifest(exam_id)
    m["title"] = doc.get("exam_title") or title
    m["source_file"] = os.path.basename(src)
    m["source_path"] = os.path.abspath(src)
    m["confirmed"] = False                      # 다시 읽었으면 확정은 무효다
    m["dropped_figures"] = [{"name": n, "why": w} for n, w in dropped]
    m["missing_figures"] = doc.get("missing_figures") or []
    CFG.save_manifest(m, exam_id)
    CFG.mark(exam_id, "02_items", {"items": len(doc["items"])})
    return doc


@router.post("/exam/{exam_id}/remap")
def remap_exam(exam_id: str):
    """시험지 HTML 을 사람이 고친 뒤 다시 읽어낸다."""
    _exam_or_404(exam_id)
    paper = CFG.find_paper(exam_id)
    if not paper:
        raise HTTPException(400, "시험지 HTML 이 없습니다.")
    _do_map(paper, exam_id)
    return _summary(exam_id)


# ── 2단계: 매핑 확인 · 수정 · 확정 ────────────────────────────────────────
@router.get("/exam/{exam_id}/items")
def items(exam_id: str):
    p = _exam_or_404(exam_id)
    if not os.path.isfile(p["items"]):
        raise HTTPException(404, "아직 읽어내지 않았습니다.")
    d = _load(p["items"])
    m = CFG.load_manifest(exam_id)
    return {"exam_id": exam_id, "title": d["exam_title"],
            "confirmed": bool(m.get("confirmed")),
            "dropped_figures": m.get("dropped_figures") or [],
            "missing_figures": m.get("missing_figures") or [],
            "sections": d.get("sections") or [],
            "items": d["items"]}


class ItemPatch(BaseModel):
    id: str
    number: str | None = None
    question: str | None = None
    passage: str | None = None
    choices: list[str] | None = None
    answer_type: str | None = None
    drop: bool = False
    resolved: bool = False          # 사람이 보고 괜찮다고 판단한 것
    reviewed: bool | None = None    # 한 문항씩 넘기며 확인한 표시


@router.post("/exam/{exam_id}/items")
def patch_items(exam_id: str, patches: list[ItemPatch]):
    """화면에서 고친 내용을 문항 JSON 에 반영한다.

    본문이 바뀌면 item_hash 가 달라져서, 이미 만든 정답은 '낡음'으로 표시된다.
    그게 맞다 — 문제가 바뀌었으면 정답도 다시 봐야 한다.
    """
    p = _exam_or_404(exam_id)
    d = _load(p["items"])
    by_id = {i["id"]: i for i in d["items"]}
    changed = 0

    for q in patches:
        it = by_id.get(q.id)
        if it is None:
            continue
        if q.drop:
            d["items"] = [x for x in d["items"] if x["id"] != q.id]
            changed += 1
            continue
        if q.number is not None:
            it["number"] = q.number
        if q.question is not None:
            it["question"] = q.question.strip()
        if q.passage is not None:
            it["passage"] = q.passage.strip() or None
        if q.choices is not None:
            it["choices"] = [c.strip() for c in q.choices]
            it["markers"] = it.get("markers") or []
        if q.answer_type is not None:
            it["answer_type"] = q.answer_type
        if q.resolved:
            it["needs_review"] = False
            it["warnings"] = []
        if q.reviewed is not None:
            it["reviewed"] = bool(q.reviewed)
        it["item_hash"] = P.item_hash(it["question"], it["choices"])
        it["edited"] = True
        changed += 1

    P.save(d, p["items"])
    m = CFG.load_manifest(exam_id)
    m["confirmed"] = False              # 고쳤으면 다시 확정해야 한다
    CFG.save_manifest(m, exam_id)
    return {"changed": changed, **_summary(exam_id)}


@router.post("/exam/{exam_id}/confirm")
def confirm(exam_id: str):
    """입력 확정. 이걸 눌러야 정답 생성이 열린다."""
    p = _exam_or_404(exam_id)
    if not os.path.isfile(p["items"]):
        raise HTTPException(400, "아직 읽어내지 않았습니다.")
    d = _load(p["items"])
    if not d["items"]:
        raise HTTPException(400, "문항이 하나도 없습니다.")
    m = CFG.load_manifest(exam_id)
    m["confirmed"] = True
    m["confirmed_items"] = len(d["items"])
    CFG.save_manifest(m, exam_id)
    return _summary(exam_id)


@router.get("/exam/{exam_id}/paper")
def paper(exam_id: str):
    _exam_or_404(exam_id)
    f = CFG.find_paper(exam_id)
    if not f:
        raise HTTPException(404, "시험지 HTML 이 없습니다.")
    return FileResponse(f, media_type="text/html")


@router.get("/exam/{exam_id}/paper/figs/{name}")
def paper_fig(exam_id: str, name: str):
    _exam_or_404(exam_id)
    f = os.path.join(CFG.exam_dir(exam_id), "01_paper", "figs", os.path.basename(name))
    if not os.path.isfile(f):
        raise HTTPException(404, "없는 그림입니다.")
    return FileResponse(f)


# ── 3단계: 정답·해설 (오래 걸리므로 백그라운드 + 진행률) ──────────────────
@router.post("/exam/{exam_id}/answer")
def start_answer(exam_id: str, force: bool = False):
    p = _exam_or_404(exam_id)
    m = CFG.load_manifest(exam_id)
    if not m.get("confirmed"):
        raise HTTPException(400,
                            "입력 확정을 먼저 눌러 주세요. "
                            "자리가 틀린 채로 만들면 그 시간이 버려집니다.")
    with _LOCK:
        job = JOBS.get(exam_id)
        if job and job.get("running"):
            return job
        JOBS[exam_id] = {"running": True, "done": 0, "total": 0,
                         "log": [], "error": "", "started": time.time()}

    t = threading.Thread(target=_run_answer, args=(exam_id, p, force), daemon=True)
    t.start()
    return JOBS[exam_id]


def _run_answer(exam_id, p, force):
    job = JOBS[exam_id]

    def log(*a):
        line = " ".join(str(x) for x in a).strip()
        if line:
            job["log"].append(line)
            del job["log"][:-200]

    try:
        doc = _load(p["items"])
        job["total"] = len(doc["items"])
        os.makedirs(os.path.dirname(p["answers"]), exist_ok=True)

        store = batch.Store(p["answers"], exam_id)
        todo = store.pending(doc["items"], force=force)
        job["done"] = job["total"] - len(todo)
        if not todo:
            log("이미 모두 만들어져 있습니다.")
        else:
            log("%d문항을 만듭니다." % len(todo))
            groups = [todo[i:i + batch.BATCH] for i in range(0, len(todo), batch.BATCH)]
            for n, g in enumerate(groups, 1):
                ok = batch._run_group(doc, g, store, "", log, "[%d/%d]" % (n, len(groups)))
                job["done"] += ok
        CFG.mark(exam_id, "03_answers",
                 {"answers": len(store.doc["answers"]),
                  "errors": len(store.doc["errors"])})
        job["errors"] = len(store.doc["errors"])
    except codex_client.NotAuthenticated as e:
        job["error"] = str(e)
        job["need_login"] = True
    except Exception as e:                       # noqa: BLE001
        job["error"] = "%s\n%s" % (e, traceback.format_exc()[-600:])
    finally:
        job["running"] = False


@router.get("/exam/{exam_id}/answer/progress")
def answer_progress(exam_id: str):
    job = JOBS.get(exam_id)
    if not job:
        p = CFG.paths(exam_id)
        n = len(_load(p["answers"]).get("answers") or {}) \
            if os.path.isfile(p["answers"]) else 0
        return {"running": False, "done": n, "total": n, "log": [], "error": ""}
    return job


# ── 해설 검토 · 확정 ──────────────────────────────────────────────────────
@router.get("/exam/{exam_id}/answers")
def get_answers(exam_id: str):
    """해설 초안을 문항과 나란히 돌려준다. 사람이 읽고 고칠 화면용."""
    p = _exam_or_404(exam_id)
    if not os.path.isfile(p["answers"]):
        raise HTTPException(404, "아직 해설이 없습니다.")
    items_doc = _load(p["items"])
    ans = _load(p["answers"])
    a = ans.get("answers") or {}
    m = CFG.load_manifest(exam_id)

    rows = []
    for it in items_doc["items"]:
        v = a.get(it["id"]) or {}
        rows.append({
            "id": it["id"], "number": it["number"],
            "answer_type": it["answer_type"],
            "question": it["question"], "choices": it["choices"],
            "markers": it.get("markers") or [],
            "answer_index": v.get("answer_index"),
            "explanation": v.get("explanation") or "",
            "wrong_reasons": v.get("wrong_reasons") or [],
            "diagram_svg": v.get("diagram_svg"),
            "confidence": v.get("confidence"),
            "source": v.get("source", ""),
            "stale": bool(v) and v.get("item_hash") != it["item_hash"],
        })
    return {"exam_id": exam_id, "title": items_doc["exam_title"],
            "confirmed": bool(m.get("answers_confirmed")),
            "errors": ans.get("errors") or {}, "rows": rows}


class AnswerPatch(BaseModel):
    id: str
    answer_index: int | None = None
    explanation: str | None = None
    wrong_reasons: list[str] | None = None
    drop_diagram: bool = False


@router.post("/exam/{exam_id}/answers")
def patch_answers(exam_id: str, patches: list[AnswerPatch]):
    """고친 해설은 source 를 manual 로 바꾼다 — 다시 돌려도 덮어쓰지 않는다."""
    p = _exam_or_404(exam_id)
    if not os.path.isfile(p["answers"]):
        raise HTTPException(404, "아직 해설이 없습니다.")
    doc = _load(p["answers"])
    a = doc.setdefault("answers", {})
    items_by_id = {i["id"]: i for i in _load(p["items"])["items"]}
    changed = 0

    for q in patches:
        v = a.get(q.id)
        it = items_by_id.get(q.id)
        if it is None:
            continue
        if v is None:
            v = a[q.id] = {"answer_index": -1, "explanation": "",
                           "wrong_reasons": [], "item_hash": it["item_hash"]}
        if q.answer_index is not None:
            v["answer_index"] = q.answer_index
        if q.explanation is not None:
            v["explanation"] = q.explanation.strip()
        if q.wrong_reasons is not None:
            v["wrong_reasons"] = q.wrong_reasons
        if q.drop_diagram:
            v["diagram_svg"] = None
        v["item_hash"] = it["item_hash"]        # 사람이 봤으니 낡음 표시를 푼다
        v["source"] = "manual"
        changed += 1

    tmp = p["answers"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p["answers"])

    m = CFG.load_manifest(exam_id)
    m["answers_confirmed"] = False              # 고쳤으면 다시 확정
    CFG.save_manifest(m, exam_id)
    return {"changed": changed}


@router.post("/exam/{exam_id}/answers/confirm")
def confirm_answers(exam_id: str):
    """해설 확정. 이걸 눌러야 채점기를 만든다."""
    p = _exam_or_404(exam_id)
    if not os.path.isfile(p["answers"]):
        raise HTTPException(400, "아직 해설이 없습니다.")
    m = CFG.load_manifest(exam_id)
    m["answers_confirmed"] = True
    CFG.save_manifest(m, exam_id)
    return _summary(exam_id)


# ── 4단계: 채점기 ─────────────────────────────────────────────────────────
@router.post("/exam/{exam_id}/build")
def build(exam_id: str):
    p = _exam_or_404(exam_id)
    if not os.path.isfile(p["items"]):
        raise HTTPException(400, "아직 읽어내지 않았습니다.")
    items_doc = _load(p["items"])
    answers = _load(p["answers"]) if os.path.isfile(p["answers"]) else None
    r = grader.build(items_doc, answers, p["grader"], base_dir=p["paper"])
    CFG.mark(exam_id, "04_grader", {"bytes": r["bytes"]})
    return {"bytes": r["bytes"], "missing": r["missing"], "stale": r["stale"],
            "images": r["images"], **_summary(exam_id)}


@router.get("/exam/{exam_id}/grader")
def grader_file(exam_id: str, download: bool = False):
    p = _exam_or_404(exam_id)
    if not os.path.isfile(p["grader"]):
        raise HTTPException(404, "아직 채점기를 만들지 않았습니다.")
    if download:
        return FileResponse(p["grader"], media_type="text/html",
                            filename=os.path.basename(p["grader"]))
    return FileResponse(p["grader"], media_type="text/html")


@router.post("/exam/{exam_id}/open-folder")
def open_folder(exam_id: str):
    p = _exam_or_404(exam_id)
    try:
        os.startfile(p["base"])          # noqa: S606
        return {"ok": True}
    except Exception as e:               # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
