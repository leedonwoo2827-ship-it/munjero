# Codex CLI 사용법과 에러 대응

ChatGPT 구독 로그인만 쓴다. **API 키 경로는 만들지 않는다** — `openai` 임포트도,
`OPENAI_API_KEY` 참조도 코드에 없다.

## 호출 형태

```python
codex.cmd exec --skip-git-repo-check --ephemeral \
    -s read-only -C <빈 임시폴더> --color never \
    --output-schema schema.json -o out.txt -
```

플래그마다 이유가 있다.

| 플래그 | 왜 |
|---|---|
| `--output-schema` | JSON을 스키마로 강제한다. 프롬프트로 "JSON만 뱉어"라고 빌 필요가 없다 |
| `-o` | 최종 메시지만 파일로. JSONL 이벤트 스트림을 파싱하지 않아도 된다 |
| `--skip-git-repo-check` | 레포 밖에서 돈다 |
| `--ephemeral` | `~/.codex/sessions` 를 더럽히지 않는다 |
| `-s read-only` | 파일 쓰기·명령 실행 차단 |
| `-C <빈 폴더>` | 뒤질 게 없게 한다. codex는 에이전트라 놔두면 파일을 탐색하고, 그만큼 느려진다 |

프롬프트는 stdin으로 넣는다(`-`). 명령줄 인자로 넣으면 길이 제한에 걸린다.

## 스키마 제약

OpenAI structured outputs의 strict 규칙을 지켜야 한다. 어기면 스키마 오류로 죽는다.

- 모든 property가 `required` 에 있어야 한다
- `additionalProperties: false` 여야 한다
- 선택 필드는 `["string","null"]` 로 만들고 `required` 에 넣는다

문항마다 다른 제약(`answer_index < len(choices)`)은 스키마 한 벌로 표현이 안 되므로
파이썬에서 검증한다(`batch._validate`).

## 배치 크기

**5, 순차.** 실측 근거다.

| 배치 | 100문항 기준 호출 수 | 문제 |
|---|---|---|
| 1 | 100 | 부팅 오버헤드(5~10초)가 전체의 절반을 먹는다 |
| **5** | **20** | **배치당 약 30초. 출력 ~3KB로 잘리지 않는다** |
| 20 | 5 | 출력이 12KB를 넘겨 뒤쪽 해설이 짧아진다. 1회 실패로 20문항을 잃는다 |

동시 실행은 기본 1이다. ChatGPT 구독에는 rate limit이 있다.

## 실패 처리

배치가 실패하면 **이진 분할**로 내려간다.

```
배치5 실패 → 재시도 1회 → [3]+[2] → … → 1개까지
1개도 실패하면 errors[id] 에 기록하고 계속 간다
```

전체를 멈추지 않는 게 핵심이다. 99개가 되고 1개는 사람이 채운다.

배치 실패 판정: 응답 id 불일치 · `answer_index` 범위 밖 · 해설 20자 미만.

## 인증 — 함정

**`codex login status` 를 믿지 마라.** 파일만 읽고 유효성은 검증하지 않는다.
토큰이 서버에서 폐기돼도 "Logged in using ChatGPT" 라고 답한다.

`auth.json` 의 `access_token` 존재를 확인하는 방식도 같은 거짓 양성을 낸다.
이 패턴이 사내 여러 프로젝트에 복사돼 있어 전부 같이 초록불이 켜진다.

**짧은 실호출로만 판정한다** — `munjero doctor --smoke` 가 그것이다.

만료 시 메시지:

```
ERROR: Your access token could not be refreshed because your refresh token was revoked.
```

대응은 `codex.cmd login` 뿐이다. 브라우저에서 계정 승인 후 워크스페이스를 고른다.

## Windows 실행 정책

PowerShell 기본 정책이 `Restricted` 라 npm이 만든 `codex.ps1` 이 막힌다.

```
+ CategoryInfo : 보안 오류: (:) [], PSSecurityException
+ FullyQualifiedErrorId : UnauthorizedAccess
```

**`codex.cmd` 를 쓰면 된다.** `.ps1` 이 아니라서 정책 대상이 아니다.
`codex_client.find_codex()` 가 `.cmd` 를 먼저 찾는 이유다.
