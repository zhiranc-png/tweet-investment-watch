#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书日报精简版推送（交互式卡片）

功能：
1. 读取当日采集数据（X简报、雪球、价格、资讯）
2. 与上次快照对比，找出变化
3. 生成精简版飞书互动卡片
4. 通过飞书自定义机器人 webhook 发送

设计原则：精简、突出变化、一眼看完核心信息
"""
import json
import sys
import os
import datetime as dt
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "src"))

TZ8 = dt.timezone(dt.timedelta(hours=8))
now = dt.datetime.now(TZ8)
today_str = now.strftime("%Y%m%d")
DATA_DIR = os.path.join(BASE, "data")
SNAPSHOT_FILE = os.path.join(DATA_DIR, "last_snapshot.json")

# ── 工具函数 ──────────────────────────────────────────────

def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def get_session_label():
    """判断是午间版还是晚间版"""
    hour = now.hour
    if hour < 14:
        return "午间版"
    return "晚间版"


def fmt_pct(val):
    if val is None:
        return "—"
    try:
        v = float(val)
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.2f}%"
    except (ValueError, TypeError):
        return "—"


def arrow_pct(val):
    """涨跌幅箭头"""
    if val is None:
        return ""
    try:
        v = float(val)
        if v > 0:
            return "📈"
        elif v < 0:
            return "📉"
        return "➖"
    except (ValueError, TypeError):
        return ""


# ── 数据加载 ──────────────────────────────────────────────

def load_current_data():
    """加载今日所有数据"""
    data = {}

    # X 简报
    brief = load_json(os.path.join(DATA_DIR, f"brief_{today_str}.json"), {})
    data["brief"] = brief

    # 价格
    prices = load_json(os.path.join(DATA_DIR, f"prices_{today_str}.json"), {})
    data["prices"] = prices

    # 雪球
    xueqiu = load_json(os.path.join(DATA_DIR, f"xueqiu_tweets_{today_str}.json"), {})
    data["xueqiu"] = xueqiu

    # 资讯
    news = load_json(os.path.join(DATA_DIR, f"news_{today_str}.json"), [])
    data["news"] = news

    return data


# ── 变化检测 ──────────────────────────────────────────────

def detect_changes(current, snapshot):
    """对比当前数据和上次快照，找出变化"""
    changes = {
        "price_changes": [],      # 价格显著变化
        "new_topics": [],         # 新增热门主题
        "sentiment_shifts": [],   # 情绪转向
        "new_news": [],           # 重要资讯
    }

    if not snapshot:
        return changes

    # 价格变化（涨跌幅 > 1% 或绝对值变化显著）
    cur_prices = current.get("prices", {})
    prev_prices = snapshot.get("prices", {})

    for name, cur in cur_prices.items():
        prev = prev_prices.get(name, {})
        cur_chg = cur.get("change_pct")
        prev_chg = prev.get("change_pct")

        # 价格本身的变化（不是涨跌幅的变化）
        cur_price = cur.get("price")
        prev_price = prev.get("price")

        if cur_price and prev_price:
            try:
                diff_pct = (float(cur_price) - float(prev_price)) / float(prev_price) * 100
                if abs(diff_pct) >= 0.5:  # 0.5% 以上算显著
                    direction = "上涨" if diff_pct > 0 else "下跌"
                    changes["price_changes"].append({
                        "name": name,
                        "direction": direction,
                        "diff_pct": diff_pct,
                        "cur_price": cur_price,
                        "prev_price": prev_price,
                    })
            except (ValueError, TypeError, ZeroDivisionError):
                pass

    # 主题变化
    cur_themes = current.get("brief", {}).get("theme_signals", []) or current.get("brief", {}).get("top_themes", [])
    prev_themes = snapshot.get("brief", {}).get("theme_signals", []) or snapshot.get("brief", {}).get("top_themes", [])

    cur_theme_names = {t.get("theme", t.get("name", "")) for t in cur_themes[:5]}
    prev_theme_names = {t.get("theme", t.get("name", "")) for t in prev_themes[:5]}

    new_topics = cur_theme_names - prev_theme_names
    for t in cur_themes[:5]:
        name = t.get("theme", t.get("name", ""))
        if name in new_topics:
            changes["new_topics"].append(name)

    # 情绪转向（同一主题多空方向变了）
    cur_theme_map = {}
    for t in cur_themes:
        name = t.get("theme", t.get("name", ""))
        cur_theme_map[name] = t.get("sentiment", "neutral")

    prev_theme_map = {}
    for t in prev_themes:
        name = t.get("theme", t.get("name", ""))
        prev_theme_map[name] = t.get("sentiment", "neutral")

    for name, cur_sent in cur_theme_map.items():
        prev_sent = prev_theme_map.get(name)
        if prev_sent and cur_sent != prev_sent:
            changes["sentiment_shifts"].append({
                "name": name,
                "from": prev_sent,
                "to": cur_sent,
            })

    # 重要资讯（取前3条）
    news = current.get("news", [])
    if news:
        changes["new_news"] = news[:3]

    # 按变化幅度排序
    changes["price_changes"].sort(key=lambda x: abs(x["diff_pct"]), reverse=True)

    return changes


# ── 卡片生成 ──────────────────────────────────────────────

def build_card(data, changes):
    """生成飞书互动卡片（精简版）"""
    session = get_session_label()
    date_display = now.strftime("%m月%d日")

    brief = data.get("brief", {})
    prices = data.get("prices", {})
    xueqiu = data.get("xueqiu", {})
    news = data.get("news", [])

    # 统计数据
    stats = brief.get("stats", {}) if brief else {}
    x_count = stats.get("total_tweets", 0)
    x_authors = stats.get("unique_authors", 0)
    xq_count = len(xueqiu.get("tweets", [])) if xueqiu else 0
    xq_ok = xueqiu.get("kols_ok", 0) if xueqiu else 0
    news_count = len(news)

    total_items = x_count + xq_count + news_count

    # 主题列表
    themes = brief.get("theme_signals", []) or brief.get("top_themes", []) or []

    # ── 构建卡片 ────────────────────────────────────────
    card = {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": f"📊 投资舆情日报 · {date_display} {session}"
            }
        },
        "elements": []
    }

    elements = card["elements"]

    # 数据概览
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"**合计 {total_items} 条** · X {x_count} 条 / 雪球 {xq_count} 条 / 资讯 {news_count} 条"
        }
    })

    elements.append({"tag": "hr"})

    # ── 7 大资产速览 ────────────────────────────────────
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": "**🗂️ 7 大资产速览**"
        }
    })

    # 构建资产速览表
    asset_rows = []

    # 美债
    y10 = prices.get("10年期美债", {})
    y10_val = y10.get("value", "—")
    asset_rows.append(f"📈 **美债** 偏空 · 10Y {y10_val}%")

    # 黄金
    g = prices.get("黄金", {})
    g_price = g.get("price", "—")
    g_chg = fmt_pct(g.get("change_pct"))
    g_arrow = arrow_pct(g.get("change_pct"))
    asset_rows.append(f"🥇 **黄金** 中性 · ${g_price} {g_arrow}{g_chg}")

    # 原油
    o = prices.get("原油", {})
    o_price = o.get("price", "—")
    o_chg = fmt_pct(o.get("change_pct"))
    o_arrow = arrow_pct(o.get("change_pct"))
    asset_rows.append(f"🛢️ **原油** 偏空 · ${o_price} {o_arrow}{o_chg}")

    # A股
    sh = prices.get("上证指数", {})
    sh_price = sh.get("price", "—")
    sh_chg = fmt_pct(sh.get("change_pct"))
    sh_arrow = arrow_pct(sh.get("change_pct"))
    asset_rows.append(f"🇨🇳 **A股** 偏多 · {sh_price} {sh_arrow}{sh_chg}")

    # 科技/AI
    asset_rows.append("🤖 **科技/AI** 中性")

    # 加密
    asset_rows.append("₿ **加密** 偏空")

    # 美元/人民币
    fx = prices.get("美元人民币", {})
    fx_price = fx.get("price", "—")
    fx_chg = fmt_pct(fx.get("change_pct"))
    fx_arrow = arrow_pct(fx.get("change_pct"))
    asset_rows.append(f"💵 **美元/人民币** 中性 · {fx_price} {fx_arrow}{fx_chg}")

    # 两列布局
    left_col = "\n".join(f"• {row}" for row in asset_rows[:4])
    right_col = "\n".join(f"• {row}" for row in asset_rows[4:])

    elements.append({
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": "default",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": left_col}}
                ]
            },
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": right_col}}
                ]
            }
        ]
    })

    elements.append({"tag": "hr"})

    # ── 变化检测 ────────────────────────────────────────
    has_changes = False

    # 价格变化
    if changes.get("price_changes"):
        has_changes = True
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**🔥 价格异动**"
            }
        })
        for pc in changes["price_changes"][:3]:
            emoji = "🔴" if pc["direction"] == "下跌" else "🟢"
            diff_str = f"{pc['diff_pct']:+.2f}%"
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"{emoji} **{pc['name']}** {pc['direction']} {diff_str}  ·  {pc['prev_price']} → {pc['cur_price']}"
                }
            })

    # 新增主题
    if changes.get("new_topics"):
        has_changes = True
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**🆕 新晋热门主题**"
            }
        })
        topic_list = "、".join(changes["new_topics"][:3])
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"• {topic_list}"
            }
        })

    # 情绪转向
    if changes.get("sentiment_shifts"):
        has_changes = True
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**🔄 情绪转向**"
            }
        })
        for shift in changes["sentiment_shifts"][:3]:
            sent_map = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}
            from_label = sent_map.get(shift["from"], shift["from"])
            to_label = sent_map.get(shift["to"], shift["to"])
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"• **{shift['name']}**：{from_label} → {to_label}"
                }
            })

    if not has_changes:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**📌 变化**：与上一期相比无显著变化"
            }
        })

    elements.append({"tag": "hr"})

    # ── 热门主题 Top 5 ──────────────────────────────────
    if themes:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**🏷️ 热门主题 Top 5**"
            }
        })
        theme_lines = []
        for i, t in enumerate(themes[:5], 1):
            name = t.get("theme", t.get("name", ""))
            strength = t.get("signal_strength", t.get("strength", 0))
            sent = t.get("sentiment", "neutral")
            sent_emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(sent, "🟡")
            theme_lines.append(f"{i}. {sent_emoji} **{name}**（强度 {strength}）")
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(theme_lines)
            }
        })
        elements.append({"tag": "hr"})

    # ── 重要资讯 ────────────────────────────────────────
    if news:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**📰 重要资讯**"
            }
        })
        for n in news[:3]:
            title = n.get("title", "")
            time_str = n.get("time", "")
            category = n.get("category", "")
            cat_tag = f"【{category}】" if category else ""
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"• {cat_tag}{title}  \n  🕐 {time_str}"
                }
            })
        elements.append({"tag": "hr"})

    # ── 底部操作区 ──────────────────────────────────────
    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {
                    "tag": "plain_text",
                    "content": "📖 查看完整报告"
                },
                "type": "primary",
                "url": "https://lq53hzd87mw.feishu.cn/docx/"
            }
        ]
    })

    # 生成时间
    elements.append({
        "tag": "note",
        "elements": [
            {
                "tag": "plain_text",
                "content": f"生成时间：{now.strftime('%Y-%m-%d %H:%M')} · 投资舆情监控系统"
            }
        ]
    })

    return card


# ── 快照保存 ──────────────────────────────────────────────

def save_snapshot(data):
    """保存当前快照，用于下次对比"""
    snapshot = {
        "timestamp": now.isoformat(),
        "prices": data.get("prices", {}),
        "brief": {
            "theme_signals": (data.get("brief", {}).get("theme_signals") or
                             data.get("brief", {}).get("top_themes", [])),
        },
    }
    try:
        with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
        print(f"[快照] ✅ 已保存: {SNAPSHOT_FILE}", flush=True)
    except Exception as e:
        print(f"[快照] ⚠️  保存失败: {e}", flush=True)


# ── 发送 ──────────────────────────────────────────────────

def send_card(card, webhook_url):
    """发送飞书卡片"""
    if not webhook_url:
        print("[飞书] ⚠️  缺少 WEBHOOK_URL，跳过推送", flush=True)
        return False

    payload = {
        "msg_type": "interactive",
        "card": card,
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        result = resp.json()
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            print("[飞书] ✅ 推送成功", flush=True)
            return True
        else:
            print(f"[飞书] ❌ 推送失败: {result}", flush=True)
            return False
    except Exception as e:
        print(f"[飞书] ❌ 推送异常: {e}", flush=True)
        return False


# ── 主流程 ────────────────────────────────────────────────

def main():
    print("=" * 50, flush=True)
    print(f"📨 飞书日报推送 · {get_session_label()}", flush=True)
    print(f"🕐 {now.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print("=" * 50, flush=True)

    # 1. 加载当前数据
    print("\n[1/4] 加载数据...", flush=True)
    data = load_current_data()
    print(f"  X简报: {'✅' if data['brief'] else '❌'}", flush=True)
    print(f"  价格: {len(data['prices'])} 个资产", flush=True)
    print(f"  雪球: {len(data['xueqiu'].get('tweets', [])) if data['xueqiu'] else 0} 条", flush=True)
    print(f"  资讯: {len(data['news'])} 条", flush=True)

    # 2. 加载上次快照
    print("\n[2/4] 对比变化...", flush=True)
    snapshot = load_json(SNAPSHOT_FILE, {})
    changes = detect_changes(data, snapshot)
    print(f"  价格异动: {len(changes['price_changes'])} 项", flush=True)
    print(f"  新晋主题: {len(changes['new_topics'])} 个", flush=True)
    print(f"  情绪转向: {len(changes['sentiment_shifts'])} 个", flush=True)

    # 3. 生成卡片
    print("\n[3/4] 生成卡片...", flush=True)
    card = build_card(data, changes)
    print("  ✅ 卡片已生成", flush=True)

    # 4. 发送
    print("\n[4/4] 推送飞书...", flush=True)
    webhook_url = os.environ.get("FEISHU_WEBHOOK", "")
    if not webhook_url:
        print("[飞书] ⚠️  未配置 FEISHU_WEBHOOK，跳过推送", flush=True)
        success = True  # 缺少配置不算失败，只是跳过
    else:
        success = send_card(card, webhook_url)

    # 5. 保存快照（不管推送成功与否，都保存）
    print("\n[快照] 保存本期数据...", flush=True)
    save_snapshot(data)

    print("\n" + "=" * 50, flush=True)
    if success:
        print("✅ 全部完成！", flush=True)
    else:
        print("⚠️  推送未完成（可能缺少 webhook）", flush=True)
    print("=" * 50, flush=True)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
