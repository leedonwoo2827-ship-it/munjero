# -*- coding: utf-8 -*-
"""문제로 CLI — 시험지 HTML 을 넣으면 채점기 HTML 이 나온다."""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(HERE, "work")
DIST = os.path.join(HERE, "dist")


def _p(*a):
    print(*a)
    sys.stdout.flush()


def _slug(path):
    from .ingest import slugify
    return slugify(path)


def _workdir(target):
    """경로가 work/<id> 면 그대로, 아니면 id 로 본다."""
    if os.path.isdir(target):
        return target
    d = os.path.join(WORK, target)
    if os.path.isdir(d):
        return d
    raise SystemExit("작업 폴더를 찾지 못했습니다: %s\n  먼저 extract 를 돌리세요." % target)


def _load(path):
    return json.load(open(path, encoding="utf-8"))


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
        ok = False
        _p("  %-16s 없음" % "codex CLI")
        _p("     %s" % str(e).replace("\n", "\n     "))
        return 1 if not args.smoke else 1

    _p("  %-16s %s" % ("OPENAI_API_KEY", "없음 - 정상입니다. 이 도구는 API 키를 쓰지 않습니다."))
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


# ── extract ───────────────────────────────────────────────────────────────
def cmd_extract(args):
    from . import ingest
    exam_id = args.exam_id or _slug(args.src)
    out = os.path.join(WORK, exam_id)
    _p("추출: %s" % os.path.basename(args.src))
    r = ingest.extract(args.src, out, exam_id=exam_id, title=args.title or "")
    _p("  -> %s" % r["path"])
    _p("  문항 %d · 구획 %d · 검수 필요 %d" % (r["items"], r["sections"], r["review"]))
    _p("")
    _p("  브라우저에서 열어 확인한 뒤 다음을 실행하세요:")
    _p("    python -m munjero parse %s" % exam_id)
    return 0


# ── parse ─────────────────────────────────────────────────────────────────
def cmd_parse(args):
    from .parse import html_to_items as P
    d = _workdir(args.target)
    src = args.html or os.path.join(d, "01_extract.html")
    if not os.path.isfile(src):
        raise SystemExit("시험지 HTML 이 없습니다: %s" % src)
    doc = P.parse_html(src)
    out = os.path.join(d, "02_items.json")
    P.save(doc, out)
    _p(P.report(doc))
    _p("")
    _p("  -> %s" % out)
    return 0


# ── answer ────────────────────────────────────────────────────────────────
def cmd_answer(args):
    from .answer import batch, codex_client as C
    d = _workdir(args.target)
    doc = _load(os.path.join(d, "02_items.json"))
    out = os.path.join(d, "03_answers.json")
    _p("정답·해설 생성: %s" % doc["exam_title"])
    try:
        store = batch.answer_all(doc, out, batch=args.batch, limit=args.limit,
                                 force=args.force, model=args.model, log=_p)
    except C.NotAuthenticated as e:
        _p("")
        _p(str(e))
        return 1
    n = len(store.doc["answers"])
    e = len(store.doc["errors"])
    _p("")
    _p("  완료 %d문항%s" % (n, (" · 실패 %d문항" % e) if e else ""))
    _p("  -> %s" % out)
    return 0


# ── build ─────────────────────────────────────────────────────────────────
def cmd_build(args):
    from .build import grader
    d = _workdir(args.target)
    items = _load(os.path.join(d, "02_items.json"))
    apath = os.path.join(d, "03_answers.json")
    answers = _load(apath) if os.path.isfile(apath) else None
    if answers is None:
        _p("  주의: 03_answers.json 이 없습니다. 정답 없이 빌드합니다.")
    out = args.out or os.path.join(DIST, items["exam_id"] + ".html")
    r = grader.build(items, answers, out, base_dir=d, no_cdn=args.no_cdn)
    _p("빌드 완료")
    _p("  -> %s  (%.0f KB)" % (r["path"], r["bytes"] / 1024.0))
    if r["images"]:
        _p("  그림 %d개를 파일 안에 심었습니다." % r["images"])
    if r["missing"]:
        _p("  정답 없음 %d문항: %s" % (len(r["missing"]), ", ".join(map(str, r["missing"][:12]))))
    if r["stale"]:
        _p("  본문이 바뀌어 낡은 정답 %d문항: %s"
           % (len(r["stale"]), ", ".join(map(str, r["stale"][:12]))))
    _p("")
    _p("  탐색기에서 더블클릭하면 바로 열립니다.")
    return 0


# ── run (전 단계) ─────────────────────────────────────────────────────────
def cmd_run(args):
    """시험지 HTML 하나를 채점기까지 관통시킨다."""
    from .parse import html_to_items as P
    from .answer import batch, codex_client as C
    from .build import grader

    src = args.html
    exam_id = args.exam_id or _slug(src)
    d = os.path.join(WORK, exam_id)
    os.makedirs(d, exist_ok=True)

    _p("[1/3] 매핑")
    doc = P.parse_html(src)
    doc["exam_id"] = doc.get("exam_id") or exam_id
    P.save(doc, os.path.join(d, "02_items.json"))
    _p(P.report(doc))

    _p("")
    _p("[2/3] 정답·해설 생성")
    try:
        batch.answer_all(doc, os.path.join(d, "03_answers.json"),
                         batch=args.batch, limit=args.limit, model=args.model, log=_p)
    except C.NotAuthenticated as e:
        _p("")
        _p(str(e))
        return 1

    _p("")
    _p("[3/3] 채점기 빌드")
    answers = _load(os.path.join(d, "03_answers.json"))
    out = args.out or os.path.join(DIST, exam_id + ".html")
    # 그림 상대경로는 시험지 HTML 옆을 기준으로 한다
    r = grader.build(doc, answers, out, base_dir=os.path.dirname(os.path.abspath(src)),
                     no_cdn=args.no_cdn)
    _p("  -> %s  (%.0f KB)" % (r["path"], r["bytes"] / 1024.0))
    return 0


# ── wizard ────────────────────────────────────────────────────────────────
def cmd_wizard(args):
    _p("=" * 54)
    _p("  문제로 - 시험지 HTML 을 채점기 HTML 로 바꿉니다")
    _p("=" * 54)
    _p("")
    cands = sorted(glob.glob(os.path.join(HERE, "input", "*.html"))
                   + glob.glob(os.path.join(HERE, "*.html")))
    if not cands:
        _p("  input 폴더에 시험지 HTML 을 넣고 다시 실행하세요.")
        _p("    %s" % os.path.join(HERE, "input"))
        os.makedirs(os.path.join(HERE, "input"), exist_ok=True)
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

    ns = argparse.Namespace(html=cands[idx], exam_id="", batch=5, limit=0,
                            model="", out="", no_cdn=False)
    return cmd_run(ns)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="munjero", description="시험지 HTML -> 채점기 HTML")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("doctor", help="환경·로그인 점검")
    p.add_argument("--smoke", action="store_true", help="실제로 1회 호출해 본다")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("extract", help="원본 PDF/HWP -> 시험지 HTML")
    p.add_argument("src")
    p.add_argument("--exam-id", default="")
    p.add_argument("--title", default="")
    p.set_defaults(fn=cmd_extract)

    p = sub.add_parser("parse", help="시험지 HTML -> 문항 JSON")
    p.add_argument("target")
    p.add_argument("--html", default="")
    p.set_defaults(fn=cmd_parse)

    p = sub.add_parser("answer", help="정답·해설 생성")
    p.add_argument("target")
    p.add_argument("--batch", type=int, default=5)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--force", action="store_true")
    p.add_argument("--model", default="")
    p.set_defaults(fn=cmd_answer)

    p = sub.add_parser("build", help="채점기 HTML 빌드")
    p.add_argument("target")
    p.add_argument("--out", default="")
    p.add_argument("--no-cdn", action="store_true")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("run", help="시험지 HTML -> 채점기 (전 단계)")
    p.add_argument("html")
    p.add_argument("--exam-id", default="")
    p.add_argument("--batch", type=int, default=5)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--model", default="")
    p.add_argument("--out", default="")
    p.add_argument("--no-cdn", action="store_true")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("wizard", help="대화형")
    p.set_defaults(fn=cmd_wizard)

    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        ap.print_help()
        return 0
    return args.fn(args)
