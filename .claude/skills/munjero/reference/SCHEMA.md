# 파일 계약

단계 사이는 **파일로 끊는다.** 각 단계는 앞 단계 산출 파일만 읽고 다음 파일만 쓴다.
사업기획팀이 중간 파일을 손으로 고치고 그 다음 단계만 다시 돌릴 수 있어야 한다.

```
work/<exam_id>/
  01_extract.html    시험지 HTML — 사람이 브라우저에서 열고 고치는 파일
  02_items.json      문항 구조
  03_answers.json    정답·해설 (별도 파일)
  figs/              그림
dist/<exam_id>.html  채점기
```

## 02_items.json

```jsonc
{
  "schema": "munjero/items@1",
  "exam_id": "2019-1-trade-english-1-A",
  "exam_title": "2019년 제1회 무역영어 1급 A형",
  "source_file": "2019-1 무역영어 1급 A형.pdf",
  "extractor": "pdf_2col_kcci@1",
  "sections": [{"no": 1, "name": "영문해석", "boundary_confidence": "inferred"}],
  "items": [{
    "id": "2019-1-trade-english-1-A#11",
    "number": "11",
    "subject": "영문해석",
    "answer_type": "single",          // single = 채점 / free = 해설만
    "question": "What is the main purpose?",
    "passage": "…공유지문 + 문항 지문…",
    "stimulus": "11-12",
    "tables": [{"columns": [], "rows": [[]]}],
    "figures": ["figs/BIN0002.png"],
    "choices": ["to complain", "to order", "to apologize", "to inquire"],
    "markers": ["①", "②", "③", "④"],
    "answer_index": null,             // 여기에 손으로 정답을 넣고 3단계를 건너뛸 수도 있다
    "explanation": null,
    "source": {"page": 3, "confidence": 0.94},
    "item_hash": "sha1:9f2c…",        // 재개와 stale 판정의 근거
    "warnings": [],
    "needs_review": false
  }]
}
```

`item_hash` = `sha1(question + "\0" + "\0".join(choices))`.

## 03_answers.json — 왜 분리했는가

대조는 사업기획팀이 한다. 해설을 고친 뒤 다시 돌렸을 때 검수분이 날아가면
그 팀은 이 도구를 두 번 안 쓴다.

| | 단일 파일 | 분리 |
|---|---|---|
| 재개 | items 전체를 다시 써야 함 | answers만 append |
| 본문 수정 후 | 정답이 덮어써짐 | `item_hash` 불일치 → stale 표시, 나머지 보존 |
| 손으로 수정 | 수천 줄에서 문항 탐색 | id → answer_index 맵 |
| Ctrl+C | 중간 상태 손실 | 배치마다 원자적 저장(tmp → replace) |

```jsonc
{
  "schema": "munjero/answers@1",
  "exam_id": "2019-1-trade-english-1-A",
  "engine": {"cli": "codex", "auth": "chatgpt"},
  "answers": {
    "2019-1-trade-english-1-A#11": {
      "answer_index": 3,              // 0-base. free 문항은 -1
      "explanation": "…",
      "confidence": "high",           // high | medium | low
      "wrong_reasons": ["…", "", "…", "…"],   // 보기 순서대로. 정답 자리는 빈 문자열
      "item_hash": "sha1:9f2c…",
      "source": "codex"               // codex | manual
    }
  },
  "errors": {
    "…#37": {"reason": "timeout after 2 retries", "number": "37"}
  }
}
```

**`source: "manual"` 은 `--force` 에도 덮어쓰지 않는다.** 사람이 고친 답이다.

## axexam 스키마에서 바뀐 것

**뺐다** (전부 DB 전용): `pr_key` `pr_hash` `src_id` `rd_no` `n_choices`
`has_figure` `has_sql` `has_table` `verified` `edited_by`.

**`bundle` 삭제.** axexam의 `bundle` 은 "10문제 = 1묶음" DB 규칙 때문에 있던 것이고
DB가 없으면 의미가 없다. `keyOf(p) = (p.bundle||"")+"#"+p.number` 대신 **`id` 단일 키**로 간다.
JS도 한 줄로 줄고, 디자인팀이 `data-id` 를 읽을 때도 뜻이 통한다.

**`sql` → `code` 로 일반화.** SQL 시험이 아니다. axexam의 `sqlRun()` 자동 감지
(SQL 키워드로 맨텍스트를 코드블록화)는 오탐만 만들어 쓰지 않는다.

**더했다**: `source` `item_hash` `confidence` `warnings` `needs_review`.
검수가 이 도구의 실제 목적이기 때문이다.
