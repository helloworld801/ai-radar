#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 情报雷达 (AI Info Radar)
============================
零依赖(纯 Python 标准库)的 AI 信息搜集程序,面向 X(Twitter) 内容创作。

功能:
  1. 抓取多路信息源: RSS/Atom 订阅、Hacker News 搜索 API、Reddit JSON
  2. 按四大类关键词打分归类: 羊毛优惠 / 新品发布 / 热点话题 / 技巧灵感
  3. 自动去重(记住已见过的链接,不重复推送)
  4. 生成每日 Markdown 简报 (reports/YYYY-MM-DD.md),含创作候选 Top 榜
  5. 可选推送: Telegram Bot / Server酱(微信)

用法:
  python3 ai_radar.py                 # 抓取最近 26 小时,生成今日简报
  python3 ai_radar.py --hours 48      # 扫描窗口改为 48 小时
  python3 ai_radar.py --demo          # 用内置样例数据跑一遍(无需联网,用于验证)
  python3 ai_radar.py --no-notify     # 只生成报告,不推送

定时运行 (Linux/macOS crontab, 每天早 8 点):
  0 8 * * * cd /path/to/ai-radar && python3 ai_radar.py >> radar.log 2>&1
Windows 用"任务计划程序"添加每日任务即可。

推送配置(可选,设为环境变量):
  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID   -> Telegram 推送
  SERVERCHAN_KEY                          -> Server酱 微信推送
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SEEN_PATH = os.path.join(BASE_DIR, "seen.json")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 ai-radar/1.0")
CST = timezone(timedelta(hours=8))  # 北京时间

# --------------------------------------------------------------------------
# 默认配置(可被 config.json 覆盖)
# --------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "hours": 26,                # 扫描窗口(小时)
    "min_score": 1,             # 收录门槛分
    "top_candidates": 5,        # 创作候选条数
    "rss_sources": [
        {"name": "OpenAI Blog",        "url": "https://openai.com/news/rss.xml"},
        {"name": "Google AI Blog",     "url": "https://blog.google/technology/ai/rss/"},
        {"name": "Hugging Face Blog",  "url": "https://huggingface.co/blog/feed.xml"},
        {"name": "TechCrunch AI",      "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
        {"name": "VentureBeat AI",     "url": "https://venturebeat.com/category/ai/feed/"},
        {"name": "The Verge AI",       "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
        {"name": "MIT Tech Review AI", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed"},
        {"name": "少数派",              "url": "https://sspai.com/feed"},
        {"name": "爱范儿",              "url": "https://www.ifanr.com/feed"}
    ],
    "hn_queries": ["AI free credits", "free tier LLM", "open source model release"],
    "reddit_subs": ["LocalLLaMA", "artificial", "ChatGPT"],
    "categories": {
        "yangmao": {
            "title": "🧧 羊毛 / 白嫖优惠",
            "keywords": [
                "free credit", "free credits", "free tier", "free trial", "giveaway",
                "promo", "coupon", "discount", "waive", "no cost", "$0", "free for students",
                "student offer", "edu", "免费", "羊毛", "白嫖", "限免", "限时免费", "赠金",
                "优惠", "折扣", "学生", "教育优惠", "免费额度", "试用"
            ],
            "weight": 2
        },
        "release": {
            "title": "🚀 新品 / 新功能发布",
            "keywords": [
                "launch", "launches", "release", "releases", "released", "announce",
                "announces", "introducing", "unveils", "new model", "now available",
                "beta", "GA", "preview", "发布", "上线", "推出", "开源", "新模型", "更新",
                "gpt", "claude", "gemini", "grok", "llama", "qwen", "deepseek", "kimi",
                "mistral", "midjourney", "sora", "copilot"
            ],
            "weight": 1
        },
        "hot": {
            "title": "🔥 热点话题 / 爆款素材",
            "keywords": [
                "viral", "controversy", "backlash", "debate", "lawsuit", "ban", "bans",
                "layoff", "layoffs", "fired", "outage", "leak", "leaked", "milestone",
                "record", "surpass", "热议", "争议", "刷屏", "爆火", "裁员", "起诉",
                "封禁", "宕机", "泄露", "破纪录"
            ],
            "weight": 1
        },
        "tips": {
            "title": "💡 技巧 / 教程灵感",
            "keywords": [
                "how to", "guide", "tutorial", "tips", "trick", "workflow", "prompt",
                "prompting", "best practices", "cheat sheet", "教程", "技巧", "攻略",
                "指南", "玩法", "提示词", "工作流", "实战"
            ],
            "weight": 1
        }
    }
}

# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------

def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg.update(user_cfg)
        except Exception as e:
            print(f"[warn] config.json 解析失败,使用默认配置: {e}")
    return cfg


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_html(text):
    return re.sub(r"<[^>]+>", " ", unescape(text or "")).strip()


def parse_time(value):
    """尽力解析 RSS/Atom 的各种时间格式,返回 aware datetime 或 None。"""
    if not value:
        return None
    value = value.strip()
    try:
        return parsedate_to_datetime(value)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(re.sub(r"Z$", "+0000", value), fmt)
        except Exception:
            continue
    return None


def item_key(link, title):
    return hashlib.sha1((link or title).encode("utf-8")).hexdigest()

# --------------------------------------------------------------------------
# 信息源抓取
# --------------------------------------------------------------------------

def fetch_rss(source, raw=None):
    """解析 RSS 2.0 / Atom,返回 item 列表。raw 供离线测试注入。"""
    items = []
    try:
        data = raw if raw is not None else http_get(source["url"])
        root = ET.fromstring(data)
    except Exception as e:
        print(f"[warn] 抓取失败 {source['name']}: {e}")
        return items

    def text(el, *tags):
        for t in tags:
            found = el.find(t)
            if found is not None and (found.text or found.get("href")):
                return found.text or found.get("href")
        return ""

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    # RSS 2.0
    for it in root.iter("item"):
        items.append({
            "title": strip_html(text(it, "title")),
            "link": (text(it, "link") or "").strip(),
            "summary": strip_html(text(it, "description"))[:500],
            "time": parse_time(text(it, "pubDate", "{http://purl.org/dc/elements/1.1/}date")),
            "source": source["name"],
        })
    # Atom
    for it in root.iter("{http://www.w3.org/2005/Atom}entry"):
        link = ""
        for l in it.findall("atom:link", ns):
            if l.get("rel") in (None, "alternate"):
                link = l.get("href", "")
                break
        items.append({
            "title": strip_html(text(it, "atom:title".replace("atom:", "{http://www.w3.org/2005/Atom}"))),
            "link": link.strip(),
            "summary": strip_html(text(it, "{http://www.w3.org/2005/Atom}summary",
                                       "{http://www.w3.org/2005/Atom}content"))[:500],
            "time": parse_time(text(it, "{http://www.w3.org/2005/Atom}published",
                                    "{http://www.w3.org/2005/Atom}updated")),
            "source": source["name"],
        })
    return items


def fetch_hn(query, since_ts):
    """Hacker News Algolia 搜索 API。"""
    url = ("https://hn.algolia.com/api/v1/search_by_date?query="
           + urllib.parse.quote(query)
           + f"&tags=story&numericFilters=created_at_i>{int(since_ts)}&hitsPerPage=30")
    items = []
    try:
        data = json.loads(http_get(url))
        for hit in data.get("hits", []):
            link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            items.append({
                "title": hit.get("title") or "",
                "link": link,
                "summary": f"HN 热度: {hit.get('points', 0)} 分 / {hit.get('num_comments', 0)} 评论",
                "time": datetime.fromtimestamp(hit.get("created_at_i", 0), tz=timezone.utc),
                "source": f"HackerNews ({query})",
            })
    except Exception as e:
        print(f"[warn] HN 搜索失败 '{query}': {e}")
    return items


def fetch_reddit(sub):
    url = f"https://www.reddit.com/r/{sub}/hot.json?limit=40"
    items = []
    try:
        data = json.loads(http_get(url))
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            if d.get("stickied"):
                continue
            items.append({
                "title": d.get("title") or "",
                "link": "https://www.reddit.com" + d.get("permalink", ""),
                "summary": (f"r/{sub} · {d.get('score', 0)} 赞 / "
                            f"{d.get('num_comments', 0)} 评论 · "
                            + strip_html(d.get("selftext", ""))[:200]),
                "time": datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc),
                "source": f"Reddit r/{sub}",
            })
    except Exception as e:
        print(f"[warn] Reddit 抓取失败 r/{sub}: {e}")
    return items

# --------------------------------------------------------------------------
# 分类打分 / 去重 / 报告
# --------------------------------------------------------------------------

CJK_RE = re.compile(r"[一-鿿]")


def translate_zh(text):
    """把英文文本翻译成中文(零依赖,走 Google 免费翻译接口)。
    失败时返回 None,不影响主流程。已含中文的文本直接跳过。"""
    text = (text or "").strip()
    if not text or CJK_RE.search(text):
        return None
    try:
        url = ("https://translate.googleapis.com/translate_a/single"
               "?client=gtx&sl=auto&tl=zh-CN&dt=t&q=" +
               urllib.parse.quote(text[:500]))
        data = json.loads(http_get(url, timeout=12).decode("utf-8"))
        return "".join(seg[0] for seg in data[0] if seg and seg[0]).strip() or None
    except Exception:
        return None


def translate_items(grouped, config):
    """给收录条目补上中文标题 it['zh'](上限 40 条,防止超时)。"""
    if not config.get("translate_to_zh", True):
        return
    budget = 40
    done = 0
    for items in grouped.values():
        for it in items:
            if budget <= 0:
                break
            zh = translate_zh(it["title"])
            budget -= 1
            if zh:
                it["zh"] = zh
                done += 1
                time.sleep(0.2)
    if done:
        print(f"[ok] 已翻译 {done} 条英文标题")


def classify(item, categories):
    """返回 (最佳分类key, 得分, 命中词)。无命中返回 (None, 0, [])。"""
    text = f"{item['title']} {item['summary']}".lower()
    best = (None, 0, [])
    for key, cat in categories.items():
        hits = [kw for kw in cat["keywords"] if kw.lower() in text]
        score = len(hits) * cat.get("weight", 1)
        if score > best[1]:
            best = (key, score, hits)
    return best


def load_seen():
    if os.path.exists(SEEN_PATH):
        try:
            with open(SEEN_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_seen(seen):
    cutoff = time.time() - 30 * 86400  # 只保留 30 天记录
    seen = {k: v for k, v in seen.items() if v > cutoff}
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(seen, f)


def render_report(grouped, config, now, total_scanned):
    lines = [f"# AI 情报雷达 · {now.strftime('%Y-%m-%d')}",
             "",
             f"> 扫描时间: {now.strftime('%Y-%m-%d %H:%M')} (北京时间) · "
             f"扫描窗口: 最近 {config['hours']} 小时 · "
             f"共扫描 {total_scanned} 条,收录 {sum(len(v) for v in grouped.values())} 条",
             ""]

    # 创作候选 Top N
    all_items = [it for its in grouped.values() for it in its]
    top = sorted(all_items, key=lambda x: -x["score"])[:config["top_candidates"]]
    if top:
        lines += ["## ✍️ 今日创作候选 Top {}".format(len(top)), ""]
        for i, it in enumerate(top, 1):
            lines.append(f"{i}. **{it['title']}** — {it['source']} "
                         f"(热度分 {it['score']},命中: {', '.join(it['hits'][:5])})  ")
            if it.get("zh"):
                lines.append(f"   译: {it['zh']}  ")
            lines.append(f"   {it['link']}")
        lines.append("")

    for key, cat in config["categories"].items():
        items = grouped.get(key, [])
        lines += [f"## {cat['title']} ({len(items)})", ""]
        if not items:
            lines += ["今日无新增。", ""]
            continue
        for it in sorted(items, key=lambda x: -x["score"]):
            t = it["time"].astimezone(CST).strftime("%m-%d %H:%M") if it["time"] else "时间未知"
            lines.append(f"- **[{it['title']}]({it['link']})**  ")
            if it.get("zh"):
                lines.append(f"  译: {it['zh']}  ")
            lines.append(f"  {it['source']} · {t} · 分数 {it['score']}  ")
            if it["summary"]:
                lines.append(f"  {it['summary'][:180]}")
            lines.append("")
    return "\n".join(lines)

# --------------------------------------------------------------------------
# 推送
# --------------------------------------------------------------------------

def notify(title, digest):
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat:
        try:
            payload = urllib.parse.urlencode(
                {"chat_id": tg_chat, "text": f"{title}\n\n{digest}"[:4000]}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                data=payload, headers={"User-Agent": UA})
            urllib.request.urlopen(req, timeout=15)
            print("[ok] Telegram 已推送")
        except Exception as e:
            print(f"[warn] Telegram 推送失败: {e}")

    sc_key = os.environ.get("SERVERCHAN_KEY")
    if sc_key:
        try:
            payload = urllib.parse.urlencode(
                {"title": title, "desp": digest[:4000]}).encode()
            req = urllib.request.Request(
                f"https://sctapi.ftqq.com/{sc_key}.send",
                data=payload, headers={"User-Agent": UA})
            urllib.request.urlopen(req, timeout=15)
            print("[ok] Server酱 已推送")
        except Exception as e:
            print(f"[warn] Server酱 推送失败: {e}")

# --------------------------------------------------------------------------
# 内置样例数据(--demo 离线验证用)
# --------------------------------------------------------------------------

DEMO_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Demo Feed</title>
<item><title>Anthropic offers $50 free credits for new Claude API users</title>
<link>https://example.com/claude-free-credits</link>
<description>Limited-time promo: new developers get free credits, students get extra edu discount.</description>
<pubDate>{now}</pubDate></item>
<item><title>Google launches Gemini 4 preview, now available in beta</title>
<link>https://example.com/gemini-4</link>
<description>Google announces its new model with major upgrades.</description>
<pubDate>{now}</pubDate></item>
<item><title>OpenAI faces backlash over new pricing, debate goes viral</title>
<link>https://example.com/openai-backlash</link>
<description>The controversy sparked heated debate across social media.</description>
<pubDate>{now}</pubDate></item>
<item><title>How to build a prompt workflow: complete guide with tips</title>
<link>https://example.com/prompt-guide</link>
<description>A hands-on tutorial covering prompting best practices.</description>
<pubDate>{now}</pubDate></item>
<item><title>Old news from last month should be filtered out</title>
<link>https://example.com/old</link>
<description>free credits but too old</description>
<pubDate>{old}</pubDate></item>
</channel></rss>"""

# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def run(args):
    config = load_config()
    if args.hours:
        config["hours"] = args.hours
    now = datetime.now(CST)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config["hours"])

    # 1. 抓取
    raw_items = []
    if args.demo:
        fmt = "%a, %d %b %Y %H:%M:%S +0000"
        demo = DEMO_RSS.format(
            now=datetime.now(timezone.utc).strftime(fmt),
            old=(datetime.now(timezone.utc) - timedelta(days=30)).strftime(fmt))
        raw_items += fetch_rss({"name": "Demo Feed", "url": ""}, raw=demo)
        print(f"[demo] 使用内置样例数据 ({len(raw_items)} 条)")
    else:
        for src in config["rss_sources"]:
            got = fetch_rss(src)
            print(f"[ok] {src['name']}: {len(got)} 条")
            raw_items += got
        for q in config["hn_queries"]:
            raw_items += fetch_hn(q, cutoff.timestamp())
        for sub in config["reddit_subs"]:
            raw_items += fetch_reddit(sub)

    total_scanned = len(raw_items)

    # 2. 时间过滤 + 去重 + 分类
    seen = {} if args.demo else load_seen()
    grouped = {k: [] for k in config["categories"]}
    for it in raw_items:
        if not it["title"] or not it["link"]:
            continue
        if it["time"] and it["time"] < cutoff:
            continue
        key = item_key(it["link"], it["title"])
        if key in seen:
            continue
        cat, score, hits = classify(it, config["categories"])
        if cat is None or score < config["min_score"]:
            continue
        it.update(score=score, hits=hits)
        grouped[cat].append(it)
        seen[key] = time.time()

    if not args.demo:
        save_seen(seen)
        # 2.5 英文标题翻译成中文(--demo 保持离线,不翻译)
        translate_items(grouped, config)

    # 3. 生成报告
    os.makedirs(REPORT_DIR, exist_ok=True)
    report = render_report(grouped, config, now, total_scanned)
    suffix = "-demo" if args.demo else ""
    path = os.path.join(REPORT_DIR, f"{now.strftime('%Y-%m-%d')}{suffix}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    collected = sum(len(v) for v in grouped.values())
    print(f"[done] 收录 {collected} 条 -> {path}")

    # 4. 推送摘要
    if collected and not args.no_notify and not args.demo:
        digest_lines = []
        for k, cat in config["categories"].items():
            for it in sorted(grouped[k], key=lambda x: -x["score"])[:3]:
                digest_lines.append(f"· {it.get('zh') or it['title']}\n  {it['link']}")
        notify(f"AI 雷达 {now.strftime('%m-%d')}: 收录 {collected} 条",
               "\n".join(digest_lines))
    return path


def main():
    p = argparse.ArgumentParser(description="AI 情报雷达")
    p.add_argument("--hours", type=int, help="扫描窗口(小时),默认 26")
    p.add_argument("--demo", action="store_true", help="用内置样例数据离线验证")
    p.add_argument("--no-notify", action="store_true", help="不推送,只生成报告")
    args = p.parse_args()
    run(args)


if __name__ == "__main__":
    main()
