# -*- coding: utf-8 -*-
"""경로 규약.

산출물은 **레포 밖**에 쌓인다. 레포는 코드만 들고 있고, 시험 내용은 밖에 남는다
(공개 저장소에 시험지가 딸려 들어가지 않게 하려는 것이기도 하다).

    munjero-output/          (기본 위치. 화면 하단에서 바꿀 수 있다)
      <시험id>/
        _exam.json      이 시험의 메타와 단계별 상태
        README.md       이 폴더가 뭔지 사람이 읽는 설명
        00_source/      원본 PDF/HWP
        01_paper/       시험지 HTML + figs/
        02_items/       문항 JSON
        03_answers/     정답·해설 JSON
        04_grader/      채점기 HTML

단계마다 폴더가 남아서, 중간에 손으로 고치고 그 다음 단계만 다시 돌릴 수 있다.
출력 위치는 MUNJERO_OUT 환경변수나 --out-root 로 바꾼다.
"""
from __future__ import annotations

import json
import os

PKG = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(PKG)

STAGES = [
    ("00_source", "원본 시험지 파일"),
    ("01_paper", "시험지 HTML — 브라우저로 열어 고치는 파일"),
    ("02_items", "문항 JSON"),
    ("03_answers", "정답·해설 JSON"),
    ("04_grader", "채점기 HTML — 더블클릭하면 열립니다"),
]


SETTINGS = os.path.join(REPO, "munjero-settings.json")


def load_settings() -> dict:
    if os.path.isfile(SETTINGS):
        try:
            return json.load(open(SETTINGS, encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_settings(d: dict) -> None:
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SETTINGS)


def default_out_root() -> str:
    # 프로젝트 폴더 안에 둔다. .gitignore 로 막아 두었으니 커밋되지 않는다.
    # 화면 하단에서 다른 위치로 바꿀 수 있다.
    return os.path.join(REPO, "munjero-output")


def out_root(override: str = "") -> str:
    """우선순위: 인자 > 환경변수 > 화면에서 정한 값 > 기본값."""
    if override:
        return os.path.abspath(override)
    env = os.environ.get("MUNJERO_OUT")
    if env:
        return os.path.abspath(env)
    saved = (load_settings().get("out_root") or "").strip()
    if saved:
        return os.path.abspath(saved)
    return default_out_root()


def set_out_root(path: str) -> str:
    """화면에서 출력 폴더를 바꾼다. 없으면 만든다."""
    path = os.path.abspath(os.path.expanduser(path.strip()))
    os.makedirs(path, exist_ok=True)
    d = load_settings()
    d["out_root"] = path
    save_settings(d)
    return path


def exam_dir(exam_id: str, override: str = "") -> str:
    return os.path.join(out_root(override), exam_id)


def stage(exam_id: str, name: str, override: str = "") -> str:
    """단계 폴더 경로. 없으면 만든다."""
    d = os.path.join(exam_dir(exam_id, override), name)
    os.makedirs(d, exist_ok=True)
    return d


def paths(exam_id: str, override: str = "") -> dict:
    base = exam_dir(exam_id, override)
    return {
        "base": base,
        "manifest": os.path.join(base, "_exam.json"),
        "source": os.path.join(base, "00_source"),
        "paper": os.path.join(base, "01_paper"),
        "items": os.path.join(base, "02_items", "items.json"),
        "answers": os.path.join(base, "03_answers", "answers.json"),
        "grader": os.path.join(base, "04_grader", exam_id + ".html"),
    }


def find_paper(exam_id: str, override: str = "") -> str:
    """01_paper 안의 시험지 HTML. 사람이 이름을 바꿨어도 찾는다."""
    d = os.path.join(exam_dir(exam_id, override), "01_paper")
    if not os.path.isdir(d):
        return ""
    named = os.path.join(d, "paper.html")
    if os.path.isfile(named):
        return named
    for f in sorted(os.listdir(d)):
        if f.lower().endswith(".html"):
            return os.path.join(d, f)
    return ""


def load_manifest(exam_id: str, override: str = "") -> dict:
    p = paths(exam_id, override)["manifest"]
    if os.path.isfile(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {"schema": "munjero/exam@1", "exam_id": exam_id, "title": exam_id,
            "stages": {}}


def save_manifest(m: dict, exam_id: str, override: str = "") -> None:
    p = paths(exam_id, override)["manifest"]
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def mark(exam_id: str, name: str, info: dict, override: str = "") -> dict:
    m = load_manifest(exam_id, override)
    m.setdefault("stages", {})[name] = info
    save_manifest(m, exam_id, override)
    return m


README = """# {title}

문제로(munjero)가 만든 폴더입니다. 단계마다 결과가 남아 있어서,
중간 파일을 고치고 그 다음 단계만 다시 돌릴 수 있습니다.

    00_source/    원본 시험지 파일
    01_paper/     시험지 HTML — 브라우저로 열어 확인하고 고치는 파일
    02_items/     문항 JSON
    03_answers/   정답·해설 JSON
    04_grader/    채점기 HTML — 더블클릭하면 열립니다

## 다시 돌리기

시험지 HTML을 고쳤으면 매핑부터:

    python -m munjero parse {exam_id}
    python -m munjero answer {exam_id}
    python -m munjero build {exam_id}

해설만 고쳤으면 빌드만:

    python -m munjero build {exam_id}

## 주의

정답은 AI가 만든 것입니다. 공식 정답표와 대조해 주세요.
03_answers/answers.json 에서 고친 항목은 source 를 "manual" 로 바꿔두면
다시 돌려도 덮어쓰지 않습니다.
"""


def write_readme(exam_id: str, title: str, override: str = "") -> None:
    base = exam_dir(exam_id, override)
    os.makedirs(base, exist_ok=True)
    with open(os.path.join(base, "README.md"), "w", encoding="utf-8") as f:
        f.write(README.format(title=title or exam_id, exam_id=exam_id))
