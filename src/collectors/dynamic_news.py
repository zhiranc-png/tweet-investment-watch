# -*- coding: utf-8 -*-
"""
动态资讯采集器（稳定版）
多源聚合：新浪财经快讯 + 财新 RSS（可选）

稳定性改进：
- 每个源独立 try-except，单源失败不影响整体
- 3 次重试 + 指数退避
- feedparser 可选依赖，没有就自动跳过财新
- 去重 + 分类
"""
import datetime as dt
import json
import re
import time
import requests
from typing import List, Dict, Optional

TZ8 = dt.timezone(dt.timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

MAX_RETRIES = 3
BASE_BACKOFF = 1.5


def _retry_request(url, headers=None, timeout=10, retries=MAX_RETRIES):
    """带重试的 HTTP GET"""
    backoff = BASE_BACKOFF
    last_error = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers or {}, timeout=timeout)
            r.raise_for_status()
            return r
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError) as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 2
            else:
                raise
    raise last_error


# ── 新浪财经 7x24 快讯（主力源） ─────────────────────────

def fetch_sina_live(count: int = 20) -> List[Dict]:
    """
    新浪财经 7x24 小时快讯
    接口: zhibo.sina.com.cn/api/zhibo/feed
    """
    url = ("https://zhibo.sina.com.cn/api/zhibo/feed"
           f"?page=1&page_size={count}&zhibo_id=152&tag_id=0&dire=f")
    try:
        r = _retry_request(
            url,
            headers={"User-Agent": UA, "Referer": "https://finance.sina.com.cn"},
            timeout=10,
        )
        data = r.json()
        items = data.get("result", {}).get("data", {}).get("feed", {}).get("list", [])
        results = []
        for item in items:
            text = item.get("rich_text", "") or item.get("text", "")
            if not text:
                continue
            # 清理 HTML
            text = re.sub(r"<[^>]+>", "", text).strip()
            create_time = item.get("create_time", "")
            docurl = item.get("docurl", "")
            # 从 tag 里取分类
            tags = item.get("tag", [])
            cat = tags[0].get("name", "") if isinstance(tags, list) and tags else ""
            results.append({
                "title": text[:80] + ("…" if len(text) > 80 else ""),
                "content": text,
                "time": create_time,
                "source": "sina_live",
                "source_name": "新浪财经7x24",
                "category": cat or _classify_news(text),
                "url": docurl,
            })
        return results[:count]
    except Exception as e:
        print(f"[news] sina_live 失败: {e}", flush=True)
        return []


# ── 财新网 RSS（补充源，可选） ──────────────────────────

def fetch_caixin_latest(count: int = 10) -> List[Dict]:
    """
    财新网最新文章（RSS）
    需要 feedparser 库，没有就返回空列表（自动降级）
    """
    try:
        import feedparser
    except ImportError:
        return []  # 没有库就跳过，不报错

    try:
        feed = feedparser.parse("https://www.caixin.com/rss/economy.xml")
        results = []
        for entry in feed.entries[:count]:
            results.append({
                "title": entry.get("title", ""),
                "content": entry.get("summary", "")[:200],
                "time": entry.get("published", ""),
                "source": "caixin",
                "source_name": "财新网",
                "category": "宏观经济",
                "url": entry.get("link", ""),
            })
        return results
    except Exception as e:
        print(f"[news] caixin 失败: {e}", flush=True)
        return []


# ── 新闻分类 ────────────────────────────────────────────

def _classify_news(text: str) -> str:
    """简易新闻分类"""
    text_lower = text.lower()
    categories = [
        ("宏观经济", ["gdp", "通胀", "cpi", "pce", "美联储", "加息", "降息", "利率", "央行", "经济", "衰退", "增长", "m2", "社融"]),
        ("A股市场", ["a股", "沪指", "上证", "深证", "创业板", "科创板", "北向资金", "沪深", "证监会", "IPO"]),
        ("港股市场", ["港股", "恒生", "恒指", "港交所", "南下资金", "港股通"]),
        ("美股市场", ["美股", "纳指", "道指", "标普", "nasdaq", "s&p", "dow", "美联储"]),
        ("加密货币", ["比特币", "btc", "eth", "加密", "币圈", "crypto", "bitcoin", "以太坊"]),
        ("大宗商品", ["原油", "黄金", "白银", "铜", "铁矿石", "大宗商品", "opec", "油价", "期货"]),
        ("外汇市场", ["汇率", "人民币", "美元", "日元", "欧元", "外汇", "cny", "usd", "央行"]),
        ("科技行业", ["ai", "人工智能", "芯片", "英伟达", "nvda", "科技", "互联网", "半导体"]),
        ("地产行业", ["房地产", "楼市", "房价", "地产", "恒大", "碧桂园", "万科", "保利"]),
        ("能源行业", ["新能源", "光伏", "锂电", "储能", "煤炭", "电力"]),
    ]
    for cat, keywords in categories:
        for kw in keywords:
            if kw.lower() in text_lower:
                return cat
    return "其他"


# ── 统一入口 ────────────────────────────────────────────

def collect_dynamic_news(max_items: int = 20) -> List[Dict]:
    """
    聚合所有新闻源，按时间倒序返回
    max_items: 返回条数
    每个源独立 try-except，单源失败不影响整体
    """
    all_news = []
    sources_ok = []
    sources_fail = []

    # 1. 新浪财经 7x24 快讯（主力源）
    try:
        sina_news = fetch_sina_live(count=max_items)
        if sina_news:
            all_news.extend(sina_news)
            sources_ok.append(f"新浪财经({len(sina_news)}条)")
        else:
            sources_fail.append("新浪财经(无数据)")
    except Exception as e:
        sources_fail.append(f"新浪财经({str(e)[:40]})")

    # 2. 财新（补充源）
    try:
        caixin_news = fetch_caixin_latest(count=8)
        if caixin_news:
            all_news.extend(caixin_news)
            sources_ok.append(f"财新({len(caixin_news)}条)")
    except Exception:
        pass  # 财新失败不影响

    # 按时间排序
    def _sort_key(n):
        t = n.get("time", "")
        return t if t else "0"

    all_news.sort(key=_sort_key, reverse=True)

    # 去重（标题前 30 字相同视为重复）
    seen = set()
    unique = []
    for n in all_news:
        key = n["title"][:30]
        if key not in seen:
            seen.add(key)
            unique.append(n)

    result = unique[:max_items]
    print(f"[news] 采集完成: {len(result)} 条，源: {', '.join(sources_ok)}", flush=True)
    if sources_fail:
        print(f"[news] 失败源: {', '.join(sources_fail)}", flush=True)

    return result


def format_news_markdown(news_list: List[Dict]) -> str:
    """格式化为 Markdown 列表"""
    if not news_list:
        return "> ⚠️ 暂无动态资讯数据（所有新闻源暂不可用）"

    lines = []
    for i, n in enumerate(news_list, 1):
        time_str = n.get("time", "")
        source = n.get("source_name", n.get("source", ""))
        category = n.get("category", "")
        title = n.get("title", "")
        url = n.get("url", "")

        tag = f"【{category}】" if category else ""
        meta = f"{time_str} · {source}" if time_str else source

        if url:
            lines.append(f"**{i}. {tag}{title}**  \n   🕐 {meta}  \n   [查看原文 →]({url})")
        else:
            lines.append(f"**{i}. {tag}{title}**  \n   🕐 {meta}")

    return "\n\n".join(lines)


if __name__ == "__main__":
    news = collect_dynamic_news(15)
    print(f"\n共 {len(news)} 条动态资讯")
    for n in news[:5]:
        print(f"  [{n['category']}] {n['title'][:60]} ({n['source']})")
