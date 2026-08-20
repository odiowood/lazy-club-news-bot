"""
The Lazy Club — AI 뉴스 알림봇

하는 일:
  1) 글로벌 AI 소스들의 RSS를 긁어온다
  2) 이미 올린 글은 걸러낸다 (seen.json)
  3) 클로드에게 "우리 멤버들한테 쓸모 있는 것만" 최대 3건 고르게 한다
  4) 한국어로 번역·요약해서 디스코드에 올린다
  5) 쓸 만한 게 없으면 아무것도 올리지 않는다  ← 스팸 방지의 핵심

실행:
  python fetch_news.py                 # 실제 발행
  python fetch_news.py --dry-run       # 디스코드에 안 올리고 결과만 출력 (테스트용)
  python fetch_news.py --check-sources # 어느 뉴스 소스가 살아있는지 점검

필요한 환경변수:
  ANTHROPIC_API_KEY   클로드 API 키
  DISCORD_WEBHOOK_URL #ai-뉴스 채널의 웹훅 URL
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
from anthropic import Anthropic

# ─────────────────────────────────────────────────────────────
# 설정 — 여기만 고치면 됩니다
# ─────────────────────────────────────────────────────────────

# 모델명은 바뀔 수 있습니다. 최신 목록: https://docs.claude.com/en/docs/about-claude/models
MODEL = os.environ.get("MODEL", "claude-sonnet-4-5")

MAX_PICKS = 3           # 한 번에 올릴 최대 개수
LOOKBACK_DAYS = 4       # 며칠 이내 글까지 후보로 볼지. 매일 발행이지만 4일로 둡니다 —
                        # 실행이 한두 번 실패해도 그 사이 글을 놓치지 않습니다 (중복은 seen.json이 막음)
MAX_CANDIDATES = 90     # 클로드에 넘길 최대 후보 수 (토큰 절약). 소스별로 골고루 뽑습니다 — _balance() 참고
SEEN_FILE = Path(__file__).parent / "seen.json"
SEEN_KEEP = 500         # seen.json에 유지할 최근 URL 개수

SOURCES = [
    # 1차 소스 — 만드는 쪽이 직접 쓰는 글
    #   Anthropic 블로그는 RSS를 제공하지 않습니다(2026-08 확인). 대신 클로드 코드
    #   릴리스 노트를 봅니다 — 새로 생긴 기능이 여기 가장 먼저 적힙니다.
    ("Claude Code 릴리스", "https://github.com/anthropics/claude-code/releases.atom"),
    ("OpenAI",           "https://openai.com/blog/rss.xml"),
    ("Google DeepMind",  "https://deepmind.google/blog/rss.xml"),
    ("Hugging Face",     "https://huggingface.co/blog/feed.xml"),
    # 실전 담론 — 하니스 엔지니어링, 에이전트 설계 같은 게 여기서 먼저 돕니다
    ("Simon Willison",   "https://simonwillison.net/atom/everything/"),
    ("Latent Space",     "https://www.latent.space/feed"),
    ("Ethan Mollick",    "https://www.oneusefulthing.org/feed"),
    ("Hacker News",      "https://hnrss.org/newest?q=AI+OR+LLM+OR+Claude&points=100"),
    ("r/ChatGPTCoding",  "https://www.reddit.com/r/ChatGPTCoding/top/.rss?t=week"),
    # 만들기·배포·자동화 — 멤버들이 지금 실제로 하려는 것
    ("n8n",              "https://blog.n8n.io/rss/"),
    ("Replit",           "https://blog.replit.com/feed.xml"),
    ("Streamlit",        "https://blog.streamlit.io/feed/"),
    ("Vercel",           "https://vercel.com/atom"),
    # 도구 변경사항 — 당장 써볼 수 있는 새 기능이 여기 먼저 적힙니다
    ("Cursor",           "https://cursor.com/changelog/rss.xml"),
    # 국내
    ("GeekNews",         "https://news.hada.io/rss/news"),
    ("요즘IT",            "https://yozm.wishket.com/magazine/feed/"),
]

# ─────────────────────────────────────────────────────────────
# 큐레이션 기준 — 우리 멤버가 누구인지 클로드에게 알려주는 부분
# ─────────────────────────────────────────────────────────────

MEMBER_CONTEXT = """
이 뉴스를 받는 사람들은 경희대 AI 스터디 'The Lazy Club' 1기 멤버 5명이다.

공통점:
- 전원 비전공자이거나 개발 입문 단계다. 논문·벤치마크·모델 아키텍처에는 관심이 없다.
- 목표는 단 하나: 11월까지 각자 만든 것을 실제로 인터넷에 배포하는 것.
- 전원 클로드(Claude) 생태계에 입문 중이다. 스킬, 코워크, 클로드 코드, MCP를
  "이름은 들어봤지만 못 쓰는" 단계다.
- AI를 챗봇으로만 쓰는 단계에서 벗어나고 싶어 한다.

각자 만들고 있는 것:
- 회계사 준비생 A: 소득 상황에 맞춰 절세 플랜을 제안하는 AI 에이전트
- 회계세무 전공 B: 부가세 공제 항목을 자동 추천하는 웹 도구 (개발 경험 거의 0)
- 환경공학 C: 전공 지식 기반 데이터 시각화 웹, 창업 지향
- 신소재 1학년 D: 실험실 환경을 가상으로 구현하는 프로그램, 창업 지향
- 경영 4학년 E: 스크린 차단 앱, 개인용 자동화 도구 (텔레그램 봇 배포 경험 있음)

이들의 실제 관심사는 '업무 자동화', '개인 도구 만들기', '배포', '에이전트'다.
"""

CURATION_PROMPT = """당신은 AI 스터디 클럽의 뉴스 큐레이터다.

{member_context}

아래는 최근 AI 관련 글 후보 목록이다. 이 중에서 **위 멤버들에게 실제로 쓸모 있는 것만**
최대 {max_picks}개 고르고, 한국어로 정리하라.

## 선별 기준 (엄격하게 적용할 것)

반드시 통과해야 하는 질문: **"이걸 읽고 멤버가 이번 주에 뭔가 다르게 할 수 있는가?"**

우선순위 높음:
- 클로드/AI 도구의 새 기능 중 당장 써볼 수 있는 것 (스킬, 코워크, MCP, 클로드 코드 등)
- AI에게 일을 잘 시키는 방법론 (컨텍스트 설계, 하니스 엔지니어링, 에이전트 패턴)
- 비개발자가 뭔가를 만들어서 배포한 실제 사례
- 개인 생산성·업무 자동화에 바로 적용 가능한 것

우선순위 낮음 (거의 항상 탈락):
- 모델 벤치마크 점수, 논문, 아키텍처 해설
- 투자·인수합병·기업 실적·인사 이동
- 규제, 정책, 산업 동향 같은 거시 담론
- 이미 다 아는 뻔한 내용, 홍보성 글

**쓸 만한 게 없으면 빈 배열을 반환하라. 억지로 채우지 마라.**
아무것도 안 올리는 게 쓸모없는 걸 올리는 것보다 낫다. 0개도 완벽히 정상적인 답이다.

## 출력 형식

JSON 배열만 출력하라. 다른 말은 쓰지 마라.

[
  {{
    "title_ko": "한국어 제목 (원문 직역 말고, 내용이 바로 보이게 다시 쓸 것)",
    "summary_ko": "3줄 요약. 각 줄은 '- '로 시작. 원문 인용 없이 한국어로만.",
    "why_ko": "우리 멤버에게 왜 중요한가를 한 문장으로. 구체적으로.",
    "source": "출처명",
    "url": "원문 링크"
  }}
]

## 후보 목록

{candidates}
"""


# ─────────────────────────────────────────────────────────────
# 1단계: RSS 수집
# ─────────────────────────────────────────────────────────────

def collect_entries():
    """모든 소스에서 최근 글을 모은다. 소스 하나가 죽어도 전체가 멈추지 않는다."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    entries = []

    for name, url in SOURCES:
        try:
            feed = _fetch_feed(url)
            if feed is None or not feed.entries:
                print(f"  ⚠️  {name}: 피드를 읽지 못했습니다 — 건너뜁니다")
                continue

            count = 0
            for e in feed.entries:
                published = _parse_date(e)
                if published and published < cutoff:
                    continue

                link = e.get("link", "").strip()
                title = e.get("title", "").strip()
                if not link or not title:
                    continue

                entries.append({
                    "source": name,
                    "title": title,
                    "url": link,
                    "summary": _clean(e.get("summary", ""))[:600],
                    "published": published.isoformat() if published else "",
                })
                count += 1

            print(f"  ✓ {name}: {count}건")

        except Exception as err:
            # 소스 하나가 죽어도 나머지는 계속 간다
            print(f"  ⚠️  {name}: 건너뜁니다 ({err})")

    return entries


def _fetch_feed(url):
    """
    requests로 먼저 받아온 뒤 feedparser에 넘긴다.

    feedparser가 직접 요청하면 Cloudflare 등에서 403으로 막히는 사이트가 많다.
    브라우저처럼 보이는 User-Agent를 붙여 받아오면 대부분 해결된다.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code >= 400:
            print(f"     (HTTP {r.status_code})")
            return None
        return feedparser.parse(r.content)
    except requests.RequestException as err:
        print(f"     ({err})")
        return None


def check_sources():
    """--check-sources: 어느 소스가 살아있는지 점검한다. 소스를 추가한 뒤 확인용."""
    print("🔍 소스 점검\n")
    alive = 0
    for name, url in SOURCES:
        feed = _fetch_feed(url)
        n = len(feed.entries) if feed else 0
        if n:
            alive += 1
            latest = feed.entries[0].get("title", "")[:60]
            print(f"  ✅ {name:18} {n:3}건   최신: {latest}")
        else:
            print(f"  ❌ {name:18}   응답 없음 — SOURCES에서 빼거나 URL을 고치세요")
    print(f"\n→ {alive}/{len(SOURCES)}개 정상")


def _balance(entries, limit):
    """
    소스별로 한 건씩 돌아가며 뽑는다.

    그냥 앞에서부터 자르면 SOURCES 뒤쪽 소스가 통째로 날아간다.
    글을 많이 쓰는 소스(Vercel 등)가 자리를 독식하는 것도 막는다.
    각 소스 안에서는 최신 글이 먼저 뽑힌다.
    """
    by_source = {}
    for e in entries:
        by_source.setdefault(e["source"], []).append(e)
    for items in by_source.values():
        items.sort(key=lambda e: e.get("published", ""), reverse=True)

    picked, depth = [], 0
    while len(picked) < limit:
        added = False
        for items in by_source.values():
            if depth < len(items):
                picked.append(items[depth])
                added = True
                if len(picked) >= limit:
                    break
        if not added:          # 모든 소스가 바닥났다
            break
        depth += 1
    return picked


def _parse_date(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    return None


def _clean(html):
    """HTML 태그를 대충 걷어낸다. 요약은 어차피 클로드가 다시 쓴다."""
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


# ─────────────────────────────────────────────────────────────
# 2단계: 중복 제거
# ─────────────────────────────────────────────────────────────

def load_seen():
    if not SEEN_FILE.exists():
        return []
    try:
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as err:
        print(f"  ⚠️  seen.json을 읽지 못해 빈 목록으로 시작합니다 ({err})")
        return []


def save_seen(seen):
    try:
        SEEN_FILE.write_text(
            json.dumps(seen[-SEEN_KEEP:], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    except OSError as err:
        print(f"  ⚠️  seen.json 저장 실패 ({err})")


# ─────────────────────────────────────────────────────────────
# 3단계: 클로드에게 선별 + 번역 맡기기
# ─────────────────────────────────────────────────────────────

def curate(candidates):
    """
    선별을 클로드에게 맡긴다. 인증 방법이 두 가지다.

      1) CLAUDE_CODE_OAUTH_TOKEN  — 클로드 구독으로 인증. API 요금 0원. (기본)
      2) ANTHROPIC_API_KEY        — API 키로 인증. 사용량만큼 과금.

    둘 중 있는 걸 자동으로 쓴다. 둘 다 있으면 1번을 쓴다.
    """
    listing = "\n\n".join(
        f"[{i+1}] {c['source']} | {c['title']}\n{c['summary']}\n{c['url']}"
        for i, c in enumerate(candidates[:MAX_CANDIDATES])
    )
    prompt = CURATION_PROMPT.format(
        member_context=MEMBER_CONTEXT,
        max_picks=MAX_PICKS,
        candidates=listing,
    )

    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        print("  · 인증: 클로드 구독 (요금 없음)")
        text = _ask_claude_code(prompt)
    elif os.environ.get("ANTHROPIC_API_KEY"):
        print("  · 인증: API 키 (사용량 과금)")
        text = _ask_api(prompt)
    else:
        sys.exit(
            "❌ 인증 정보가 없습니다.\n"
            "   CLAUDE_CODE_OAUTH_TOKEN 또는 ANTHROPIC_API_KEY 중 하나가 필요합니다."
        )

    return _parse_json(text) if text else []


def _ask_claude_code(prompt):
    """클로드 코드 CLI를 헤드리스로 호출한다. 구독 토큰으로 인증된다."""
    import subprocess

    for attempt in range(3):
        try:
            r = subprocess.run(
                ["claude", "-p", prompt, "--output-format", "json", "--max-turns", "1"],
                capture_output=True, text=True, timeout=300,
            )
            if r.returncode != 0:
                raise RuntimeError(r.stderr[:400] or "종료 코드 " + str(r.returncode))

            out = r.stdout.strip()
            try:
                # --output-format json 은 {"result": "...", ...} 형태를 준다
                return json.loads(out).get("result", out)
            except json.JSONDecodeError:
                return out  # 형식이 바뀌었어도 원문 그대로 넘긴다

        except FileNotFoundError:
            sys.exit(
                "❌ claude 명령을 찾을 수 없습니다.\n"
                "   npm install -g @anthropic-ai/claude-code 로 설치하세요."
            )
        except Exception as err:
            wait = 2 ** attempt
            print(f"  ⚠️  클로드 코드 호출 실패 ({err}) — {wait}초 후 재시도")
            time.sleep(wait)

    print("❌ 3번 모두 실패했습니다. 이번 회차는 건너뜁니다.")
    return ""


def _ask_api(prompt):
    """Anthropic API를 직접 호출한다. API 키가 필요하고 사용량만큼 과금된다."""
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        except Exception as err:
            wait = 2 ** attempt
            print(f"  ⚠️  클로드 호출 실패 ({err}) — {wait}초 후 재시도")
            time.sleep(wait)

    print("❌ 3번 모두 실패했습니다. 이번 회차는 건너뜁니다.")
    return ""


def _parse_json(text):
    """모델이 코드블록으로 감싸는 경우까지 처리한다."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        print(f"  ⚠️  JSON을 찾지 못했습니다. 응답 앞부분: {text[:200]}")
        return []
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as err:
        print(f"  ⚠️  JSON 파싱 실패 ({err})")
        return []


# ─────────────────────────────────────────────────────────────
# 4단계: 디스코드 발행
# ─────────────────────────────────────────────────────────────

def post_to_discord(picks):
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        sys.exit("❌ DISCORD_WEBHOOK_URL 환경변수가 없습니다.")

    today = datetime.now(timezone(timedelta(hours=9))).strftime("%m월 %d일")

    embeds = []
    for p in picks:
        embeds.append({
            "title": p.get("title_ko", "제목 없음")[:250],
            "url": p.get("url", ""),
            "description": (
                f"{p.get('summary_ko', '')}\n\n"
                f"**💡 왜 중요한가**\n{p.get('why_ko', '')}"
            )[:4000],
            "color": 0x5865F2,
            "footer": {"text": f"출처 · {p.get('source', '?')}"},
        })

    payload = {
        "username": "레이지 뉴스",
        "content": f"## 🦥 오늘의 AI 소식 · {today}",
        "embeds": embeds,
    }

    try:
        r = requests.post(webhook, json=payload, timeout=20)
        if r.status_code >= 400:
            print(f"❌ 디스코드 발행 실패 [{r.status_code}] {r.text[:300]}")
            return False
        print(f"✅ 디스코드에 {len(picks)}건 발행 완료")
        return True
    except requests.RequestException as err:
        print(f"❌ 디스코드 요청 실패 ({err})")
        return False


# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────

def main():
    if "--check-sources" in sys.argv:
        check_sources()
        return

    dry_run = "--dry-run" in sys.argv

    print("📡 RSS 수집 중...")
    entries = collect_entries()
    print(f"→ 총 {len(entries)}건 수집")

    if not entries:
        print("수집된 글이 없습니다. 종료합니다.")
        return

    seen = load_seen()
    seen_set = set(seen)
    fresh = [e for e in entries if e["url"] not in seen_set]
    print(f"→ 새 글 {len(fresh)}건 (중복 {len(entries) - len(fresh)}건 제외)")

    if not fresh:
        print("새로운 글이 없습니다. 아무것도 올리지 않습니다.")
        return

    if len(fresh) > MAX_CANDIDATES:
        fresh = _balance(fresh, MAX_CANDIDATES)
        print(f"→ 소스별로 골고루 {len(fresh)}건만 클로드에게 넘깁니다")

    print("🤖 클로드가 선별하는 중...")
    picks = curate(fresh)

    if not picks:
        print("👍 오늘은 올릴 만한 게 없다고 판단했습니다. 조용히 넘어갑니다.")
        # 후보는 본 것으로 처리해 다음 회차에 다시 검토하지 않게 한다
        if not dry_run:
            save_seen(seen + [e["url"] for e in fresh])
        return

    print(f"→ {len(picks)}건 선별됨")
    for p in picks:
        print(f"   · {p.get('title_ko')}")

    if dry_run:
        print("\n--- DRY RUN: 실제 발행은 하지 않았습니다 ---")
        print(json.dumps(picks, ensure_ascii=False, indent=2))
        return

    if post_to_discord(picks):
        save_seen(seen + [e["url"] for e in fresh])


if __name__ == "__main__":
    main()
