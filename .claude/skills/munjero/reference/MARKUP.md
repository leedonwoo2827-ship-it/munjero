# 시험지 HTML 마크업 규약

파서는 **클래스명만** 본다. 태그·인라인 스타일·`<b>`·`<br>`·공백은 전부 자유다.
사람이 브라우저에서 보면서 마음대로 고쳐도 파서가 안 깨지게 하려는 것이다.

## 최소 형태

```html
<meta name="munjero:exam-id" content="2019-1-trade-english-1-A">
<meta name="munjero:title"   content="2019년 제1회 무역영어 1급 A형">

<article class="exam">
 <section class="exam-section" data-section-no="1" data-title="영문해석">

  <section class="stimulus-group" data-covers="11-12">
    <p class="group-directive">Read the following and answer the questions.</p>
    <blockquote class="passage">…공유지문…</blockquote>
  </section>

  <div class="question" data-qno="11" data-answer-type="single"
       data-stimulus="11-12" data-src-page="3" data-confidence="0.94">
    <p class="stem">What is the main purpose of the letter?</p>
    <ol class="choices">
      <li class="choice" data-value="1" data-marker="①">to complain</li>
      <li class="choice" data-value="2" data-marker="②">to order</li>
      <li class="choice" data-value="3" data-marker="③">to apologize</li>
      <li class="choice" data-value="4" data-marker="④">to inquire</li>
    </ol>
    <div class="answer" data-todo="answer-key"></div>
  </div>

 </section>
</article>
```

## 계약

| 클래스 | 의미 | 필수 | 파서 동작 |
|---|---|---|---|
| `.exam` | 루트 | ○ | 없으면 `<body>` 를 루트로 |
| `.exam-section` | 과목·구획 | × | `data-title`, `data-section-no` 를 읽는다 |
| `.stimulus-group` | 여러 문항이 공유하는 지문 | × | `data-covers="11-12"` |
| `.group-directive` | 공유지문의 지시문 | × | 지문 앞에 붙는다 |
| `.question` | 문항 1개 | ○ | **문서 순서 = 출력 순서** |
| `.stem` | 발문 | ○ | 없으면 첫 텍스트 노드 + 경고 |
| `.passage` | 지문 | × | 여러 개면 빈 줄로 이어붙인다 |
| `.choices > .choice` | 보기 | 채점형만 | 문서 순서가 0-base 인덱스 |
| `.data-table` | 표 | × | `<table>` 을 그대로 읽는다 |
| `.figure img` | 그림 | × | `src` 를 상대경로로 받는다 |
| `.unresolved` | 미해결 표시 | × | **있으면 무조건 검수 대상** |

## 속성

| 속성 | 위치 | 뜻 |
|---|---|---|
| `data-qno` | `.question` | 문항 번호. 없으면 자동 채번 + 경고 |
| `data-answer-type` | `.question` | `single`(4지선다·채점) / `free`(서술형·해설만) |
| `data-stimulus` | `.question` | 참조할 공유지문의 `data-covers` |
| `data-src-page` | `.question` | 원본 페이지. 대조할 때 쓴다 |
| `data-confidence` | `.question` | 추출 신뢰도 0~1 |
| `data-needs-review` | `.question` | `true` 면 검수 대상으로 표시 |
| `data-value` | `.choice` | 정규화된 번호 1~4 |
| `data-marker` | `.choice` | 원본 글리프 `①` `A` `가` |
| `data-todo` | `.unresolved` | `figure` `equation` `unmapped-glyph` 등 |

`data-value` 와 `data-marker` 를 **둘 다** 유지한다. 채점기는 번호를 재유도할 필요가 없고,
검수자는 원본과 그대로 대조할 수 있다.

## 손으로 고칠 때

- 보기 앞의 `①` `1)` `가.` 는 남겨도 되고 지워도 된다. 파서가 벗긴다.
- `.question` 을 통째로 지우면 그 문항이 사라진다. 번호는 다시 매기지 않는다.
- 실무 서술형처럼 채점하지 않을 문항은 `data-answer-type="free"` 로 두고 `.choices` 를 생략한다.

## TODO 마커

못 살린 것은 버리지 않고 남긴다. **항상 보이게** 렌더한다 — 안 보이는 TODO는 버린 TODO다.

```html
<div class="unresolved" data-todo="unmapped-glyph"
     data-reason="글리프가 비트맵으로 렌더됨; 문자 미상"
     data-src="pdf:p7#xref99"></div>
```
