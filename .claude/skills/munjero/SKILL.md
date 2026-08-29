---
name: munjero
description: 시험지 HTML을 문항 JSON으로 매핑하고, Codex CLI로 정답·해설을 생성한 뒤, 더블클릭으로 열리는 단일 파일 채점기 HTML을 만든다. "시험지", "문제 HTML", "채점기", "정답 해설 생성", "문항 매핑", "기출문제" 같은 요청에 쓴다. 원본이 PDF나 HWP면 먼저 시험지 HTML로 추출한다.
---

# 문제로 (munjero)

시험지 HTML → 정답·해설 → 채점기 HTML.

## 가장 중요한 규칙

**파이썬 스크립트를 새로 짜지 마라.** 이 레포의 `munjero` CLI를 부른다.
매번 코드를 새로 쓰면 사업기획팀이 직접 돌릴 때 결과가 달라진다.
CLI에 없는 기능이 필요하면 `munjero/` 에 함수를 추가하고 CLI에 노출시킨다.

## 순서

**0. 점검** — `python -m munjero doctor --smoke`

통과 못 하면 여기서 멈추고 사용자에게 알린다. 특히 인증은 **실호출로만** 판정한다.
`codex login status` 와 `auth.json` 검사는 둘 다 만료를 못 잡고 "로그인됨"이라고 답한다.

**1. 추출** (원본이 PDF/HWP일 때만) — `python -m munjero extract <원본>`

→ `work/<id>/01_extract.html`. **이 파일을 Read로 열어 `.todo` 와 낮은 confidence를 직접 확인한다.**
고칠 수 있는 것은 Edit으로 고친다. 마크업 규약은 `reference/MARKUP.md`.

**2. 매핑** — `python -m munjero parse work/<id>`

→ `02_items.json` + 콘솔 리포트. 검수 필요 목록을 사용자에게 **표로** 보여준다.
문항 수가 시험 공고와 다르면 반드시 짚는다.

**3. 해설** — 먼저 `--limit 3` 으로 3문항만 돌린다.

해설을 사용자에게 보여주고 톤·분량을 확인받은 뒤 전체를 돌린다.
100문항을 다 돌린 뒤에 "말투가 마음에 안 든다"는 말을 듣지 않기 위해서다.

**4. 빌드** — `python -m munjero build work/<id>`

→ `dist/<id>.html`. 파일 크기와 배지 개수(확인 필요·확신 낮음·정답 없음)를 보고한다.

한 번에 관통시키려면 `python -m munjero run <시험지.html>`.

## 하지 않는 것

- `OPENAI_API_KEY` 를 찾거나 `openai` 패키지를 쓰지 않는다. Codex CLI만 쓴다.
- `dist/*.html` 을 직접 편집하지 않는다. 원본 JSON을 고치고 다시 build한다.
- 문항 몇 개가 미심쩍다고 파이프라인을 멈추지 않는다. 문제는 배지로 끝까지 끌고 간다.
- 색상 값을 CSS에 직접 쓰지 않는다. `templates/grader.html` 의 `:root` 를 고친다.
- `source: "manual"` 인 정답을 덮어쓰지 않는다. 사람이 고친 것이다.

## 사용자에게 반드시 전할 것

**정답은 AI가 생성한 것이다.** 시험지에 정답이 없기 때문이다.
공식 정답표 대조가 필요하다는 점을 결과 보고에 반드시 포함한다.

## 참조 (필요할 때만 읽는다)

- `reference/MARKUP.md` — 시험지 HTML 클래스 계약
- `reference/SCHEMA.md` — items/answers 필드 사전
- `reference/CODEX.md` — codex exec 플래그, 에러별 대응
- `reference/DESIGN.md` — Teal 토큰표, 정답 초록 충돌 회피
