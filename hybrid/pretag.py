# -*- coding: utf-8 -*-
"""采集端候选信号预打标（第二批优化 B 项，2026-08-27）

读取当日 data/hybrid_tweets_YYYYMMDD.json，用「方向性关键词 + 互动量阈值」
启发式预打标，把 candidate_signals 字段写回同一 JSON，让日报环节的人工阅读量
从几百条压缩到几十条。

定位：启发式粗筛，不是信号判定。允许少量误报（宁多勿漏方向词）；
最终是否成为日报信号，由日报环节按 SOP §3/§3.1（行动准入门槛 + 置信度评分）决定。

用法：
    python hybrid/pretag.py                # 自动定位当日（UTC）数据文件
    python hybrid/pretag.py <json_path>    # 指定文件
"""
import datetime as dt
import json
import os
import re
import sys

# ── 阈值（可按日报反馈调整）──
ENGAGEMENT_MIN = 500        # 互动分 = likes + 2*retweets + replies，方向帖入选门槛
VIEWS_MIN = 200_000         # 或浏览量达标（有些号赞少但浏览大）
HIGH_ENGAGEMENT_OTHER = 1500  # 无方向词但互动极高的帖子另列（防漏官方/突发大事件）

# ── 方向性关键词 ──
# 中文：直接子串匹配
KW_BULLISH_ZH = [
    "看多", "看涨", "做多", "买入", "加仓", "增持", "建仓", "抄底",
    "逢低买", "逢低吸", "低多", "多头", "满仓", "牛市", "看好后市",
    "目标价上调", "上调评级", "买入评级",
]
KW_BEARISH_ZH = [
    "看空", "看跌", "做空", "卖出", "减仓", "减持", "清仓", "空单",
    "空头", "逃顶", "高抛", "熊市", "目标价下调", "下调评级", "卖出评级",
]
# 英文：词边界正则；排除 long-term / short-term 这类期限表述
KW_BULLISH_EN = [
    r"\bbullish\b", r"(?<!-)\bbuy\b", r"(?<!-)\bbuying\b", r"\baccumulate\b",
    r"\bgo(?:ing)?\s+long\b", r"\blong\b(?![- ]?(?:term|time|run|story|awaited))",
    r"\bload\s+up\b", r"\bbid\s+up\b", r"(?<!earnings )\bcalls\b", r"\bcall\s+options?\b",
    r"\bupside\s+target\b", r"\bbreakout\b",
    r"\boverweight\b", r"\boutperform\b",
]
KW_BEARISH_EN = [
    r"\bbearish\b", r"(?<!-)\bsell(?:ing|s)?\b", r"(?<![-a-z])short\b(?![- ]?(?:term|s?queezed?))",
    r"\bshorting\b", r"\bgo(?:ing)?\s+short\b", r"\bdump(?:ing)?\b",
    r"\bputs?\b", r"\bselloff\b", r"\bsell[- ]off\b", r"\bbreakdown\b",
    r"\bunderweight\b", r"\bunderperform\b", r"\breduce\s+exposure\b",
    r"\bexit(?:ing)?\s+(?:my\s+)?position", r"\bcapitulation\b",
]

BULLISH = "bullish"
BEARISH = "bearish"


def _match(text: str, zh_list, en_patterns):
    """返回命中的关键词列表（中文原词，英文命中则记模式主干）。"""
    hits = [kw for kw in zh_list if kw in text]
    for pat in en_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            hits.append(m.group(0).lower())
    return hits


def engagement_score(t: dict) -> int:
    return int(t.get("likes", 0)) + 2 * int(t.get("retweets", 0)) + int(t.get("replies", 0))


def pretag(data: dict) -> dict:
    tweets = data.get("tweets", [])
    candidates, other_high = [], []
    for t in tweets:
        text = t.get("text", "")
        if not text:
            continue
        bull = _match(text, KW_BULLISH_ZH, KW_BULLISH_EN)
        bear = _match(text, KW_BEARISH_ZH, KW_BEARISH_EN)
        eng = engagement_score(t)
        views = int(t.get("views", 0) or 0)
        hot = eng >= ENGAGEMENT_MIN or views >= VIEWS_MIN

        entry = {
            "handle": t.get("handle", ""),
            "display_name": t.get("display_name", ""),
            "tweet_id": t.get("tweet_id", ""),
            "url": t.get("url", ""),
            "created_at": t.get("created_at", ""),
            "likes": t.get("likes", 0),
            "retweets": t.get("retweets", 0),
            "replies": t.get("replies", 0),
            "views": views,
            "engagement": eng,
            "text": text,
        }
        if bull and bear:
            entry["direction"] = "mixed"
            entry["matched_bullish"] = bull
            entry["matched_bearish"] = bear
            if hot:
                candidates.append(entry)
        elif bull or bear:
            entry["direction"] = BULLISH if bull else BEARISH
            entry["matched"] = bull or bear
            if hot:
                candidates.append(entry)
        elif eng >= HIGH_ENGAGEMENT_OTHER:
            entry["direction"] = "none"
            other_high.append(entry)

    candidates.sort(key=lambda x: (-x["engagement"], -x["views"]))
    other_high.sort(key=lambda x: (-x["engagement"], -x["views"]))
    return {
        "candidate_signals": candidates,
        "high_engagement_other": other_high,
        "pretag_meta": {
            "version": 1,
            "rules": {
                "engagement_min": ENGAGEMENT_MIN,
                "views_min": VIEWS_MIN,
                "high_engagement_other": HIGH_ENGAGEMENT_OTHER,
                "engagement_formula": "likes + 2*retweets + replies",
            },
            "stats": {
                "tweets_total": len(tweets),
                "candidates": len(candidates),
                "high_engagement_other": len(other_high),
            },
        },
    }


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        today = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
        path = os.path.join("data", f"hybrid_tweets_{today}.json")
    if not os.path.exists(path):
        print(f"pretag: 找不到 {path}，跳过（SEED_ONLY 或采集失败）", flush=True)
        return
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    result = pretag(data)
    data.update(result)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    s = result["pretag_meta"]["stats"]
    print(
        f"pretag: {s['tweets_total']} 条推文 -> 候选信号 {s['candidates']} 条"
        f"（另有高互动无方向 {s['high_engagement_other']} 条）-> {path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
