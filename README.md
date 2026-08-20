# 🦥 레이지 뉴스봇

The Lazy Club 디스코드 `#ai-뉴스` 채널에 **월·수·금 오전 9시**, AI 소식을 한국어로 최대 3건 올립니다.

서버를 빌리지 않습니다. 깃허브가 정해진 시각에 대신 코드를 실행해줍니다. (GitHub Actions)

## 특징

- **원문 노출 없음.** 전부 한국어로 번역·요약합니다.
- **스팸 안 합니다.** 클로드가 "우리 멤버한테 쓸모 있나"로 걸러서, 없으면 **아무것도 안 올립니다.**
- **중복 없음.** 한 번 올린 글은 `seen.json`에 기록돼 다시 안 올라옵니다.
- 소스 하나가 죽어도 나머지는 정상 작동합니다.

---

# 설치 (한 번만, 약 15분)

## 1단계 — 디스코드 웹훅 URL 얻기

웹훅은 "이 주소로 글을 보내면 채널에 대신 써주는 우체통"입니다. 봇 계정을 따로 안 만들어도 됩니다.

1. 디스코드에서 `#ai-뉴스` 채널 옆 **톱니바퀴(채널 편집)** 클릭
2. 왼쪽 **연동** → **웹후크** → **새 웹후크**
3. 이름을 `레이지 뉴스`로 바꾸기
4. **웹후크 URL 복사** 클릭 → 어딘가에 붙여넣어 두기

> ⚠️ 이 URL을 아는 사람은 누구나 그 채널에 글을 쓸 수 있습니다. 공개된 곳에 올리지 마세요.

## 2단계 — 클로드 인증 정보 얻기

두 가지 방법이 있습니다. **1번을 권합니다 — 추가 요금이 없습니다.**

### 방법 1. 구독 토큰 (권장 · 요금 0원 · 카드 불필요)

이미 쓰고 있는 클로드 구독으로 인증합니다.

```bash
npm install -g @anthropic-ai/claude-code   # 이미 있으면 생략
claude setup-token
```

브라우저가 열리고, 승인하면 터미널에 토큰이 찍힙니다. 그걸 복사해 두세요.
이 토큰의 이름은 `CLAUDE_CODE_OAUTH_TOKEN` 입니다.

### 방법 2. API 키 (카드 등록 필요)

방법 1이 안 될 때만 씁니다.

1. https://console.anthropic.com 접속 → 로그인
2. **API Keys** → **Create Key** → 복사
3. **Billing**에서 결제 수단 등록 (한 달 예상 비용 1,000원 미만)

이 키의 이름은 `ANTHROPIC_API_KEY` 입니다.

> 챗으로 쓰는 클로드 구독료와 API 요금은 **별개**입니다. 방법 2는 구독과 무관하게 따로 과금됩니다.

## 3단계 — 깃허브 저장소 만들기

1. https://github.com/new
2. 저장소 이름: `lazy-club-news-bot`
3. **Public**을 선택하세요 ← 중요. 공개 저장소여야 Actions가 무료 무제한입니다.
4. **Create repository**

## 4단계 — 코드 올리기

받은 폴더에서 터미널을 열고:

```bash
git init
git add .
git commit -m "레이지 뉴스봇 첫 커밋"
git branch -M main
git remote add origin https://github.com/<본인아이디>/lazy-club-news-bot.git
git push -u origin main
```

## 5단계 — 비밀값 등록

키를 코드에 직접 적으면 안 됩니다. 깃허브 금고에 넣습니다.

저장소 페이지 → **Settings** → 왼쪽 **Secrets and variables** → **Actions** → **New repository secret**

두 개를 등록합니다. 이름은 **대소문자·밑줄까지 정확히** 적어야 합니다.

| Name | Secret |
|---|---|
| `DISCORD_WEBHOOK_URL` | 1단계에서 복사한 URL |
| `CLAUDE_CODE_OAUTH_TOKEN` | 2단계 **방법 1**에서 받은 토큰 |

2단계에서 방법 2(API 키)를 골랐다면, 두 번째 것 대신 `ANTHROPIC_API_KEY` 를 등록합니다.
둘 다 등록된 경우 구독 토큰이 우선 사용됩니다.

## 6단계 — 지금 바로 한 번 돌려보기

저장소 → **Actions** 탭 → 왼쪽 **AI 뉴스 발행** → 오른쪽 **Run workflow** → 초록 버튼

1~2분 뒤 디스코드 `#ai-뉴스`에 글이 올라오면 성공입니다.

> 아무것도 안 올라왔다면 정상일 수도 있습니다. Actions 로그에 `오늘은 올릴 만한 게 없다고 판단했습니다`가 찍혀 있으면 필터가 제대로 작동한 겁니다.

---

# 내 컴퓨터에서 테스트하기

```bash
pip install -r requirements.txt

export CLAUDE_CODE_OAUTH_TOKEN="2단계에서 받은 토큰"    # 또는 ANTHROPIC_API_KEY
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

python fetch_news.py --dry-run   # 디스코드엔 안 올리고 결과만 출력
python fetch_news.py             # 실제 발행
```

---

# 고치고 싶을 때

전부 `fetch_news.py` 위쪽에 모여 있습니다.

| 하고 싶은 것 | 고칠 곳 |
|---|---|
| 발행 개수 늘리기/줄이기 | `MAX_PICKS` |
| 뉴스 소스 추가·삭제 | `SOURCES` 리스트 |
| 발행 요일·시간 변경 | `.github/workflows/news.yml`의 `cron` |
| 선별 기준 바꾸기 | `CURATION_PROMPT`의 "선별 기준" 부분 |
| 멤버 프로필 갱신 | `MEMBER_CONTEXT` |

### cron 시간 계산법

깃허브는 UTC 기준입니다. **한국시간에서 9시간을 뺀 값**을 적습니다.

| 원하는 시각 (KST) | cron |
|---|---|
| 월·수·금 오전 9시 | `0 0 * * 1,3,5` |
| 매일 오전 8시 | `0 23 * * *` |
| 매주 화 오후 8시 | `0 11 * * 2` |

> GitHub Actions의 스케줄은 몇 분에서 길게는 십수 분까지 밀릴 수 있습니다. 정시 발행이 보장되진 않지만 뉴스 알림엔 문제없습니다.

---

# 문제가 생기면

| 증상 | 확인할 것 |
|---|---|
| Actions가 빨간 X | Actions 탭 → 실패한 실행 클릭 → 로그 확인 |
| `인증 정보가 없습니다` | 5단계 Secret 이름 오타 확인 (대소문자 구분) |
| `python fetch_news.py --check-sources` 에 ❌ | 그 뉴스 소스가 RSS를 내리거나 주소를 바꾼 것. `SOURCES`에서 빼거나 주소를 고치세요 |
| 디스코드 발행 실패 `[401]` | 웹훅 URL이 만료됐거나 잘못 복사됨. 1단계 다시 |
| 모델 관련 오류 | API 키 방식일 때만 해당. `MODEL` 값 확인: https://docs.claude.com/en/docs/about-claude/models |
| 매번 0건만 나옴 | `CURATION_PROMPT`의 기준이 너무 빡셈. "우선순위 낮음" 항목을 줄여보세요 |
