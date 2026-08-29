# -*- coding: utf-8 -*-
"""문제로 CLI — 시험지 HTML 을 넣으면 채점기 HTML 이 나온다.

산출물은 레포 밖 munjero-output/<시험id>/ 에 단계별로 쌓인다. config.py 참조.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys

from . import config as CFG

HERE = CFG.REPO


def _p(*a):
    print(*a)
    sys.stdout.flush()


def _slug(path):
    from .ingest import slugify
    return slugify(path)


def _load(path):
    return json.load(open(path, encoding="utf-8"))


def _resolve(target, root=""):
    """시험 id · 출력 폴더 · 원본 파일 경로 중 무엇을 줘도 (exam_id, root) 로 만든다.

    사람이 방금 map 에 넣은 파일 경로를 그대로 다시 치는 게 자연스럽다.
    id 를 따로 외우게 하지 않는다.
    """
    if os.path.isdir(target) and os.path.isfile(os.path.join(target, "_exam.json")):
        target = os.path.abspath(target.rstrip("/\\"))
        return os.path.basename(target), os.path.dirname(target)

    cands = [target]
    if os.path.isfile(target) or os.path.splitext(target)[1]:
        cands.insert(0, _slug(target))          # 파일 경로면 id 로 바꿔서 먼저 찾는다
    for c in cands:
        if os.path.isdir(CFG.exam_dir(c, root)):
            return c, root

    # id 를 직접 지정했으면 slug 가 안 맞는다. 원본 파일 이름으로 되찾는다.
    found = _by_source(os.path.basename(target), root)
    if found:
        return found, root

    raise SystemExit(
        "시험 폴더를 찾지 못했습니다: %s\n"
        "  찾은 위치: %s\n"
        "  먼저 map 을 돌리세요:  python -m munjero map <파일>"
        % (target, CFG.exam_dir(cands[0], root)))


def _by_source(basename, root=""):
    """만들어 둔 시험 중 이 원본으로 만든 것을 찾는다."""
    base = CFG.out_root(root)
    if not os.path.isdir(base):
        return ""
    for d in sorted(os.listdir(base)):
        mf = os.path.join(base, d, "_exam.json")
        if not os.path.isfile(mf):
            continue
        try:
            m = json.load(open(mf, encoding="utf-8"))
        except Exception:
            continue
        if m.get("source_file") == basename or m.get("source_path", "").endswith(basename):
            return d
    return ""


def _stage_line(name, note=""):
    _p("  %-12s %s" % (name, note))


# ── doctor ────────────────────────────────────────────────────────────────
def cmd_doctor(args):
    _p("문제로 — 환경 점검")
    _p("-" * 52)
    ok = True

    _p("  %-16s %s" % ("Python", sys.version.split()[0]))
    for mod, why in (("fitz", "PDF 읽기"), ("bs4", "HTML 파싱"),
                     ("lxml", "HTML 파서"), ("PIL", "HWP 그림 변환")):
        try:
            __import__(mod)
            _p("  %-16s 있음" % mod)
        except ImportError:
            ok = False
            _p("  %-16s 없음  <- %s. pip install -r requirements.txt" % (mod, why))

    from .answer import codex_client as C
    try:
        exe = C.find_codex()
        _p("  %-16s %s" % ("codex CLI", exe))
    except C.CodexError as e:
        _p("  %-16s 없음" % "codex CLI")
        _p("     %s" % str(e).replace("\n", "\n     "))
        return 1

    _p("  %-16s %s" % ("OPENAI_API_KEY", "없음 - 정상입니다. 이 도구는 API 키를 쓰지 않습니다."))
    _p("  %-16s %s" % ("출력 폴더", CFG.out_root(args.out_root)))
    _p("-" * 52)

    if args.smoke:
        _p("  실호출 확인 중... (파일 검사는 만료를 못 잡습니다)")
        try:
            r = C.smoke()
            _p("  응답: %s" % (r[:60] or "(빈 응답)"))
            _p("  로그인 정상입니다.")
        except C.NotAuthenticated as e:
            _p("  " + str(e).replace("\n", "\n  "))
            return 1
        except C.CodexError as e:
            _p("  호출 실패: %s" % str(e)[:300])
            return 1
    else:
        _p("  --smoke 를 붙이면 1문항으로 실제 호출을 시험합니다.")
    return 0 if ok else 1


# ── extract : 00_source -> 01_paper ───────────────────────────────────────
def cmd_extract(args):
    from . import ingest
    exam_id = args.exam_id or _slug(args.src)
    title = args.title or os.path.splitext(os.path.basename(args.src))[0]
    root = args.out_root

    src_dir = CFG.stage(exam_id, "00_source", root)
    kept = os.path.join(src_dir, os.path.basename(args.src))
    if os.path.abspath(args.src) != os.path.abspath(kept):
        shutil.copy2(args.src, kept)          # 원본을 곁에 둔다. 재현이 가능해야 한다

    paper_dir = CFG.stage(exam_id, "01_paper", root)
    _p("[01] 추출: %s" % os.path.basename(args.src))
    r = ingest.extract(kept, paper_dir, exam_id=exam_id, title=title)
    final = os.path.join(paper_dir, "paper.html")
    if os.path.abspath(r["path"]) != os.path.abspath(final):
        os.replace(r["path"], final)

    CFG.write_readme(exam_id, title, root)
    m = CFG.load_manifest(exam_id, root)
    m["title"] = title
    m["source_file"] = os.path.basename(args.src)
    CFG.save_manifest(m, exam_id, root)
    CFG.mark(exam_id, "01_paper",
             {"items": r["items"], "sections": r["sections"], "review": r["review"]}, root)

    _p("  -> %s" % final)
    _p("  문항 %d · 구획 %d · 검수 필요 %d" % (r["items"], r["sections"], r["review"]))
    if r.get("figures"):
        _p("  그림 %d개" % r["figures"])
    for name, why in (r.get("dropped_figures") or []):
        _p("  그림 제외  %-14s %s" % (name, why))
    _p("")
    _p("  브라우저에서 열어 확인한 뒤:")
    _p("    python -m munjero parse %s" % exam_id)
    return 0


# ── parse : 01_paper -> 02_items ──────────────────────────────────────────
def cmd_parse(args):
    from .parse import html_to_items as P
    exam_id, root = _resolve(args.target, args.out_root)
    src = args.html or CFG.find_paper(exam_id, root)
    if not src or not os.path.isfile(src):
        raise SystemExit("01_paper 안에 시험지 HTML 이 없습니다.")

    doc = P.parse_html(src)
    out = CFG.paths(exam_id, root)["items"]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    P.save(doc, out)

    _p("[02] " + P.report(doc))
    CFG.mark(exam_id, "02_items",
             {"items": len(doc["items"]),
              "needs_review": sum(1 for i in doc["items"] if i["needs_review"])}, root)
    _p("")
    _p("  -> %s" % out)
    return 0


# ── answer : 02_items -> 03_answers ───────────────────────────────────────
def cmd_answer(args):
    from .answer import batch, codex_client as C
    exam_id, root = _resolve(args.target, args.out_root)
    p = CFG.paths(exam_id, root)
    if not os.path.isfile(p["items"]):
        raise SystemExit("02_items 가 없습니다. 먼저 parse 를 돌리세요.")
    doc = _load(p["items"])
    os.makedirs(os.path.dirname(p["answers"]), exist_ok=True)

    _p("[03] 정답·해설 생성: %s" % doc["exam_title"])
    try:
        store = batch.answer_all(doc, p["answers"], batch=args.batch, limit=args.limit,
                                 force=args.force, model=args.model, log=_p)
    except C.NotAuthenticated as e:
        _p("")
        _p(str(e))
        return 1

    n, e = len(store.doc["answers"]), len(store.doc["errors"])
    CFG.mark(exam_id, "03_answers", {"answers": n, "errors": e}, root)
    _p("")
    _p("  완료 %d문항%s" % (n, (" · 실패 %d문항" % e) if e else ""))
    _p("  -> %s" % p["answers"])
    return 0


# ── build : 02+03 -> 04_grader ────────────────────────────────────────────
def cmd_build(args):
    from .build import grader
    exam_id, root = _resolve(args.target, args.out_root)
    p = CFG.paths(exam_id, root)
    if not os.path.isfile(p["items"]):
        raise SystemExit("02_items 가 없습니다. 먼저 parse 를 돌리세요.")
    items = _load(p["items"])
    answers = _load(p["answers"]) if os.path.isfile(p["answers"]) else None
    if answers is None:
        _p("  주의: 03_answers 가 없습니다. 정답 없이 빌드합니다.")

    out = args.out or p["grader"]
    r = grader.build(items, answers, out, base_dir=p["paper"], no_cdn=args.no_cdn)
    _p("[04] 빌드 완료")
    _p("  -> %s  (%.0f KB)" % (r["path"], r["bytes"] / 1024.0))
    if r["images"]:
        _p("  그림 %d개를 파일 안에 심었습니다." % r["images"])
    if r.get("lost_images"):
        _p("  그림 %d개를 찾지 못했습니다: %s"
           % (len(r["lost_images"]), ", ".join(r["lost_images"][:5])))
    if r["missing"]:
        _p("  정답 없음 %d문항: %s" % (len(r["missing"]), ", ".join(map(str, r["missing"][:12]))))
    if r["stale"]:
        _p("  본문이 바뀌어 낡은 정답 %d문항: %s"
           % (len(r["stale"]), ", ".join(map(str, r["stale"][:12]))))
    CFG.mark(exam_id, "04_grader",
             {"bytes": r["bytes"], "missing": len(r["missing"]),
              "stale": len(r["stale"])}, root)
    _p("")
    _p("  탐색기에서 더블클릭하면 바로 열립니다.")
    return 0


# ── map : 추출 + 매핑까지만 ───────────────────────────────────────────────
def cmd_map(args):
    """배치가 맞는지 사람이 확인할 수 있는 데까지만 간다.

    배치가 틀린 채로 해설을 만들면 그 시간이 통째로 버려진다.
    확인 지점을 넘기지 않는 것이 이 명령의 존재 이유다.
    """
    from .parse import html_to_items as P

    src = args.src
    root = args.out_root
    ext = os.path.splitext(src)[1].lower()
    exam_id = args.exam_id or _slug(src)

    if ext in (".pdf", ".hwp", ".hwpx"):
        ns = argparse.Namespace(src=src, exam_id=exam_id, title=args.title,
                                out_root=root)
        if cmd_extract(ns) != 0:
            return 1
        paper = CFG.find_paper(exam_id, root)
        _p("")
    else:
        paper_dir = CFG.stage(exam_id, "01_paper", root)
        paper = os.path.join(paper_dir, "paper.html")
        if os.path.abspath(src) != os.path.abspath(paper):
            shutil.copy2(src, paper)
            figs = os.path.join(os.path.dirname(os.path.abspath(src)), "figs")
            if os.path.isdir(figs):
                shutil.copytree(figs, os.path.join(paper_dir, "figs"),
                                dirs_exist_ok=True)

    p = CFG.paths(exam_id, root)
    doc = P.parse_html(paper)
    os.makedirs(os.path.dirname(p["items"]), exist_ok=True)
    P.save(doc, p["items"])
    CFG.write_readme(exam_id, doc.get("exam_title") or exam_id, root)
    m = CFG.load_manifest(exam_id, root)
    m["source_file"] = os.path.basename(src)     # 나중에 파일 이름만으로 되찾는다
    m["source_path"] = os.path.abspath(src)
    CFG.save_manifest(m, exam_id, root)
    CFG.mark(exam_id, "02_items",
             {"items": len(doc["items"]),
              "needs_review": sum(1 for i in doc["items"] if i["needs_review"])}, root)

    _p("[02] " + P.report(doc))
    _p("")
    _p("  시험지  %s" % paper)
    _p("  문항    %s" % p["items"])
    _p("")
    _p("  ── 확인해 주세요 ──────────────────────────────")
    _p("  시험지 HTML 을 열어 문항 번호·보기·지문이 제자리에 있는지 봅니다.")
    _p("  틀린 곳은 그 HTML 을 직접 고치고 이 명령을 다시 돌리면 됩니다.")
    _p("")
    _p("  맞으면 다음 단계:")
    _p("    python -m munjero answer %s" % exam_id)
    _p("    python -m munjero build  %s" % exam_id)
    if args.open:
        try:
            os.startfile(paper)          # noqa: S606
        except Exception:
            pass
    return 0


# ── run : 전 단계 ─────────────────────────────────────────────────────────
def cmd_run(args):
    from .parse import html_to_items as P
    from .answer import batch, codex_client as C
    from .build import grader

    src = args.html
    root = args.out_root
    ext = os.path.splitext(src)[1].lower()

    # 원본(PDF/HWP)을 주면 추출부터, 시험지 HTML 을 주면 매핑부터
    if ext in (".pdf", ".hwp", ".hwpx"):
        ns = argparse.Namespace(src=src, exam_id=args.exam_id, title="", out_root=root)
        if cmd_extract(ns) != 0:
            return 1
        exam_id = args.exam_id or _slug(src)
        paper = CFG.find_paper(exam_id, root)
        _p("")
    else:
        exam_id = args.exam_id or _slug(src)
        paper_dir = CFG.stage(exam_id, "01_paper", root)
        paper = os.path.join(paper_dir, "paper.html")
        if os.path.abspath(src) != os.path.abspath(paper):
            shutil.copy2(src, paper)
            figs = os.path.join(os.path.dirname(os.path.abspath(src)), "figs")
            if os.path.isdir(figs):
                shutil.copytree(figs, os.path.join(paper_dir, "figs"), dirs_exist_ok=True)

    p = CFG.paths(exam_id, root)

    _p("[02] 매핑")
    doc = P.parse_html(paper)
    os.makedirs(os.path.dirname(p["items"]), exist_ok=True)
    P.save(doc, p["items"])
    _p(P.report(doc))
    CFG.write_readme(exam_id, doc.get("exam_title") or exam_id, root)
    CFG.mark(exam_id, "02_items", {"items": len(doc["items"])}, root)

    _p("")
    _p("[03] 정답·해설 생성")
    os.makedirs(os.path.dirname(p["answers"]), exist_ok=True)
    try:
        store = batch.answer_all(doc, p["answers"], batch=args.batch,
                                 limit=args.limit, model=args.model, log=_p)
    except C.NotAuthenticated as e:
        _p("")
        _p(str(e))
        return 1
    CFG.mark(exam_id, "03_answers",
             {"answers": len(store.doc["answers"]),
              "errors": len(store.doc["errors"])}, root)

    _p("")
    _p("[04] 채점기 빌드")
    answers = _load(p["answers"])
    out = args.out or p["grader"]
    r = grader.build(doc, answers, out, base_dir=p["paper"], no_cdn=args.no_cdn)
    CFG.mark(exam_id, "04_grader", {"bytes": r["bytes"]}, root)
    _p("  -> %s  (%.0f KB)" % (r["path"], r["bytes"] / 1024.0))
    _p("")
    _p("  폴더: %s" % p["base"])
    return 0


# ── list ──────────────────────────────────────────────────────────────────
def cmd_list(args):
    root = CFG.out_root(args.out_root)
    _p("출력 폴더: %s" % root)
    if not os.path.isdir(root):
        _p("  아직 없습니다.")
        return 0
    names = [d for d in sorted(os.listdir(root))
             if os.path.isfile(os.path.join(root, d, "_exam.json"))]
    if not names:
        _p("  시험이 없습니다.")
        return 0
    _p("")
    for n in names:
        m = CFG.load_manifest(n, args.out_root)
        st = m.get("stages", {})
        done = "".join("O" if k in st else "." for k in
                       ("01_paper", "02_items", "03_answers", "04_grader"))
        _p("  [%s]  %-34s %s" % (done, n, m.get("title", "")))
    _p("")
    _p("  [01 02 03 04]  O=완료  .=아직")
    return 0


# ── wizard ────────────────────────────────────────────────────────────────
def cmd_wizard(args):
    _p("=" * 54)
    _p("  문제로 - 시험지를 채점기로 바꿉니다")
    _p("=" * 54)
    _p("")
    pats = ("*.html", "*.pdf", "*.hwp", "*.hwpx")
    cands = []
    for pat in pats:
        cands += glob.glob(os.path.join(HERE, "input", pat))
    cands = sorted(cands)
    if not cands:
        os.makedirs(os.path.join(HERE, "input"), exist_ok=True)
        _p("  input 폴더에 시험지를 넣고 다시 실행하세요.")
        _p("    %s" % os.path.join(HERE, "input"))
        _p("")
        _p("  넣을 수 있는 것: 시험지 HTML, PDF, HWP")
        return 1

    for i, c in enumerate(cands, 1):
        _p("  %d) %s" % (i, os.path.basename(c)))
    _p("")
    try:
        sel = input("  번호를 고르세요 (엔터=1): ").strip() or "1"
        idx = int(sel) - 1
    except (ValueError, EOFError):
        idx = 0
    if not (0 <= idx < len(cands)):
        _p("  잘못된 번호입니다.")
        return 1
    _p("")
    ns = argparse.Namespace(html=cands[idx], exam_id="", batch=5, limit=0,
                            model="", out="", no_cdn=False, out_root="")
    return cmd_run(ns)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="munjero", description="시험지 -> 채점기 HTML")
    ap.add_argument("--out-root", default="",
                    help="출력 폴더 (기본: 레포와 나란한 munjero-output)")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("doctor", help="환경·로그인 점검")
    p.add_argument("--smoke", action="store_true")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("extract", help="[01] 원본 PDF/HWP -> 시험지 HTML")
    p.add_argument("src")
    p.add_argument("--exam-id", default="")
    p.add_argument("--title", default="")
    p.set_defaults(fn=cmd_extract)

    p = sub.add_parser("parse", help="[02] 시험지 HTML -> 문항 JSON")
    p.add_argument("target")
    p.add_argument("--html", default="")
    p.set_defaults(fn=cmd_parse)

    p = sub.add_parser("answer", help="[03] 정답·해설 생성")
    p.add_argument("target")
    p.add_argument("--batch", type=int, default=5)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--force", action="store_true")
    p.add_argument("--model", default="")
    p.set_defaults(fn=cmd_answer)

    p = sub.add_parser("build", help="[04] 채점기 HTML 빌드")
    p.add_argument("target")
    p.add_argument("--out", default="")
    p.add_argument("--no-cdn", action="store_true")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("map", help="[01-02] 추출 + 매핑까지 — 배치 확인 지점에서 멈춘다")
    p.add_argument("src")
    p.add_argument("--exam-id", default="")
    p.add_argument("--title", default="")
    p.add_argument("--open", action="store_true", help="끝나면 시험지 HTML 을 연다")
    p.set_defaults(fn=cmd_map)

    p = sub.add_parser("run", help="원본이나 시험지 HTML -> 채점기 (전 단계, 확인 없이)")
    p.add_argument("html")
    p.add_argument("--exam-id", default="")
    p.add_argument("--batch", type=int, default=5)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--model", default="")
    p.add_argument("--out", default="")
    p.add_argument("--no-cdn", action="store_true")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("list", help="만든 시험 목록")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("wizard", help="대화형")
    p.set_defaults(fn=cmd_wizard)

    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        ap.print_help()
        return 0
    if not hasattr(args, "out_root"):
        args.out_root = ""
    return args.fn(args)
