"""
资产价格联动模块 — 基于新浪财经 API（主）+ 备用源

相比 Yahoo Finance 的优势：
- 国内访问稳定，无数据中心 IP 限流问题
- 实时行情（15分钟延迟）
- 覆盖美股、ETF、指数、外汇、期货

支持的资产类型：
- 美股/ETF：AAPL, TSLA, TLT, GLD, SPY, QQQ 等 → gb_前缀
- 指数：道琼斯、纳斯达克、标普500、VIX → int_前缀
- 外汇：美元/人民币、欧元/美元 → fx_前缀
- 期货：黄金(GC)、原油(CL) → hf_前缀
- 加密货币：BTC, ETH → 备用源

使用方式：
    from src.analysis.asset_price import enrich_brief_with_prices
    brief_with_prices = enrich_brief_with_prices(brief_data)
"""
from __future__ import annotations

import time
import re
from datetime import datetime, timedelta
from typing import Any
import json
from pathlib import Path

import requests

# ── 资产符号映射表 ──────────────────────────────────────────────
# 将常见的资产别名映射到新浪财经的代码格式
# 格式: (sina_code, 数据类型)
SYMBOL_MAP = {
    # ── 美股大盘 ETF ──
    "SPY": ("gb_spy", "us_etf"),
    "QQQ": ("gb_qqq", "us_etf"),
    "DIA": ("gb_dia", "us_etf"),
    "IWM": ("gb_iwm", "us_etf"),
    "VTI": ("gb_vti", "us_etf"),
    "SPX": ("int_sp500", "index"),
    "S&P500": ("int_sp500", "index"),
    "标普500": ("int_sp500", "index"),
    "DJI": ("int_dji", "index"),
    "道琼斯": ("int_dji", "index"),
    "IXIC": ("int_nasdaq", "index"),
    "纳斯达克": ("int_nasdaq", "index"),
    "纳指": ("int_nasdaq", "index"),
    "VIX": ("int_vix", "index"),
    "波动率": ("int_vix", "index"),

    # ── 美债/固收 ETF ──
    "TLT": ("gb_tlt", "us_etf"),
    "IEF": ("gb_ief", "us_etf"),
    "SHY": ("gb_shy", "us_etf"),
    "BND": ("gb_bnd", "us_etf"),
    "LQD": ("gb_lqd", "us_etf"),
    "HYG": ("gb_hyg", "us_etf"),
    "TIP": ("gb_tip", "us_etf"),
    "美债": ("gb_tlt", "us_etf"),
    "长债": ("gb_tlt", "us_etf"),

    # ── 黄金/贵金属 ──
    "GLD": ("gb_gld", "us_etf"),
    "IAU": ("gb_iau", "us_etf"),
    "SLV": ("gb_slv", "us_etf"),
    "黄金": ("hf_GC", "future"),
    "金价": ("hf_GC", "future"),
    "Gold": ("hf_GC", "future"),
    "GOLD": ("gb_gld", "us_etf"),
    "COMEX黄金": ("hf_GC", "future"),
    "白银": ("hf_SI", "future"),
    "Silver": ("hf_SI", "future"),

    # ── 原油/能源 ──
    "USO": ("gb_uso", "us_etf"),
    "XLE": ("gb_xle", "us_etf"),
    "UNG": ("gb_ung", "us_etf"),
    "原油": ("hf_CL", "future"),
    "油价": ("hf_CL", "future"),
    "Oil": ("hf_CL", "future"),
    "WTI": ("hf_CL", "future"),
    "WTI原油": ("hf_CL", "future"),
    "CL=F": ("hf_CL", "future"),
    "天然气": ("hf_NG", "future"),
    "布伦特": ("hf_BZ", "future"),

    # ── 科技股 ──
    "AAPL": ("gb_aapl", "us_stock"),
    "MSFT": ("gb_msft", "us_stock"),
    "GOOGL": ("gb_googl", "us_stock"),
    "GOOG": ("gb_goog", "us_stock"),
    "AMZN": ("gb_amzn", "us_stock"),
    "META": ("gb_meta", "us_stock"),
    "NVDA": ("gb_nvda", "us_stock"),
    "TSLA": ("gb_tsla", "us_stock"),
    "NFLX": ("gb_nflx", "us_stock"),
    "AMD": ("gb_amd", "us_stock"),
    "INTC": ("gb_intc", "us_stock"),
    "ORCL": ("gb_orcl", "us_stock"),
    "CRM": ("gb_crm", "us_stock"),
    "ADBE": ("gb_adbe", "us_stock"),
    "CSCO": ("gb_csco", "us_stock"),
    "IBM": ("gb_ibm", "us_stock"),
    "AVGO": ("gb_avgo", "us_stock"),
    "MU": ("gb_mu", "us_stock"),
    "AMAT": ("gb_amat", "us_stock"),
    "ASML": ("gb_asml", "us_stock"),
    "TSM": ("gb_tsm", "us_stock"),
    "台积电": ("gb_tsm", "us_stock"),
    "PLTR": ("gb_pltr", "us_stock"),
    "COIN": ("gb_coin", "us_stock"),
    "MSTR": ("gb_mstr", "us_stock"),

    # ── 金融/银行 ──
    "JPM": ("gb_jpm", "us_stock"),
    "BAC": ("gb_bac", "us_stock"),
    "GS": ("gb_gs", "us_stock"),
    "MS": ("gb_ms", "us_stock"),
    "C": ("gb_c", "us_stock"),
    "WFC": ("gb_wfc", "us_stock"),
    "XLF": ("gb_xlf", "us_etf"),
    "KRE": ("gb_kre", "us_etf"),
    "BRK": ("gb_brk-b", "us_stock"),
    "BRK.B": ("gb_brk-b", "us_stock"),
    "巴菲特": ("gb_brk-b", "us_stock"),

    # ── 医疗/消费 ──
    "JNJ": ("gb_jnj", "us_stock"),
    "UNH": ("gb_unh", "us_stock"),
    "PFE": ("gb_pfe", "us_stock"),
    "XLV": ("gb_xlv", "us_etf"),
    "XLP": ("gb_xlp", "us_etf"),
    "XLY": ("gb_xly", "us_etf"),

    # ── 加密货币（CoinGecko 真实价格，优先） ──
    "BTC": ("bitcoin", "crypto"),
    "Bitcoin": ("bitcoin", "crypto"),
    "比特币": ("bitcoin", "crypto"),
    "ETH": ("ethereum", "crypto"),
    "以太坊": ("ethereum", "crypto"),
    "SOL": ("solana", "crypto"),
    "Solana": ("solana", "crypto"),
    "BNB": ("binancecoin", "crypto"),
    "XRP": ("ripple", "crypto"),
    "DOGE": ("dogecoin", "crypto"),
    "ADA": ("cardano", "crypto"),
    "AVAX": ("avalanche-2", "crypto"),
    "DOT": ("polkadot", "crypto"),
    "MATIC": ("matic-network", "crypto"),
    "LINK": ("chainlink", "crypto"),
    # ETF 代理（备用，价格低很多，仅作参考）
    "BITO": ("gb_bito", "us_etf"),
    "ETHE": ("gb_ethe", "us_etf"),

    # ── 外汇 ──
    "DXY": ("fx_susdcny", "forex"),  # 用美元/人民币代理（新浪没有DXY）
    "美元指数": ("fx_susdcny", "forex"),
    "USDCNY": ("fx_susdcny", "forex"),
    "人民币": ("fx_susdcny", "forex"),
    "EURUSD": ("fx_seurusd", "forex"),
    "欧元": ("fx_seurusd", "forex"),
    "USDJPY": ("fx_susdjpy", "forex"),
    "日元": ("fx_susdjpy", "forex"),

    # ── 中概/港股 ──
    "BABA": ("gb_baba", "us_stock"),
    "阿里巴巴": ("gb_baba", "us_stock"),
    "PDD": ("gb_pdd", "us_stock"),
    "拼多多": ("gb_pdd", "us_stock"),
    "JD": ("gb_jd", "us_stock"),
    "京东": ("gb_jd", "us_stock"),
    "BIDU": ("gb_bidu", "us_stock"),
    "百度": ("gb_bidu", "us_stock"),
    "NIO": ("gb_nio", "us_stock"),
    "XPEV": ("gb_xpev", "us_stock"),
    "LI": ("gb_li", "us_stock"),
    "TCEHY": ("gb_tcehy", "us_stock"),
    "腾讯": ("gb_tcehy", "us_stock"),
    "KWEB": ("gb_kweb", "us_etf"),
    "中概": ("gb_kweb", "us_etf"),
    "FXI": ("gb_fxi", "us_etf"),
    "MCHI": ("gb_mchi", "us_etf"),

    # ── 主题 ETF ──
    "ARKK": ("gb_arkk", "us_etf"),
    "ARK": ("gb_arkk", "us_etf"),
    "SMH": ("gb_smh", "us_etf"),
    "半导体": ("gb_smh", "us_etf"),
    "SOXX": ("gb_soxx", "us_etf"),
    "SOXL": ("gb_soxl", "us_etf"),
    "TAN": ("gb_tan", "us_etf"),
    "ICLN": ("gb_icln", "us_etf"),
    "XBI": ("gb_xbi", "us_etf"),
    "IBB": ("gb_ibb", "us_etf"),
    "QQQM": ("gb_qqqm", "us_etf"),
    "SCHD": ("gb_schd", "us_etf"),
    "VNQ": ("gb_vnq", "us_etf"),
}

# 已知非交易标的（跳过）
SKIP_SYMBOLS = {
    "AI", "CEO", "CFO", "GDP", "CPI", "PCE", "FOMC", "Fed", "FED",
    "SEC", "FDA", "IPO", "ETF", "REIT", "ESG", "SAAS", "ROI",
    "EV", "APP", "DATA", "CORE", "NEXT", "BEST", "TOP",
    "NEW", "BIG", "SMALL", "MID", "LONG", "SHORT",
    "HIGH", "LOW", "OPEN", "CLOSE", "FIRST", "LAST",
    "ONE", "TWO", "THREE", "FOUR", "FIVE",
    "YES", "NO", "ALL", "ANY", "NEWS",
    "TIME", "YEAR", "MONTH", "WEEK", "DAY",
    "USA", "US", "UK", "EU", "CN", "JP",
    "Q1", "Q2", "Q3", "Q4",
    "MONEY", "CASH", "RISK", "BETA", "ALPHA",
    "SAVE", "BUY", "SELL", "HOLD",
    "FUND", "STOCK", "BOND", "MARKET",
    "TRADE", "TRADING", "INVEST", "INVESTING",
    "PROFIT", "LOSS", "GAIN", "DROP",
    "RATE", "YIELD", "PRICE", "VALUE",
    "GROWTH", "QUALITY",
    "GLOBAL", "WORLD", "CHINA", "AMERICA",
}

# ── 缓存 ───────────────────────────────────────────────────────
_price_cache: dict[str, dict] = {}
_cache_timestamp: float = 0
CACHE_TTL = 1800  # 30分钟缓存（行情是实时的，不能缓存太久）

_SINA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.sina.com.cn/",
}


def _resolve_sina_code(symbol: str, asset_type: str = "") -> tuple[str, str] | None:
    """将资产符号解析为 (新浪代码, 数据类型)，加密货币返回 None（走 CoinGecko）"""
    if not symbol:
        return None

    sym_clean = symbol.strip().lstrip("$")

    # 跳过已知非交易标的
    if sym_clean.upper() in SKIP_SYMBOLS:
        return None

    # 直接映射（不区分大小写）
    sym_upper = sym_clean.upper()
    sym_lower = sym_clean.lower()

    for key, val in SYMBOL_MAP.items():
        if key.upper() == sym_upper or key.lower() == sym_lower:
            # 加密货币走 CoinGecko，不走新浪
            if val[1] == "crypto":
                return None
            return val

    # 如果已经是新浪格式，直接返回
    if sym_clean.startswith("gb_"):
        return (sym_clean, "us_stock")
    if sym_clean.startswith("int_"):
        return (sym_clean, "index")
    if sym_clean.startswith("hf_"):
        return (sym_clean, "future")
    if sym_clean.startswith("fx_"):
        return (sym_clean, "forex")

    # 纯大写字母（1-5个），可能是美股代码，尝试 gb_ 前缀
    if 1 <= len(sym_upper) <= 5 and sym_upper.isalpha():
        return ("gb_" + sym_lower, "us_stock")

    return None


def _resolve_coingecko_id(symbol: str, asset_type: str = "") -> str | None:
    """将资产符号解析为 CoinGecko coin id（仅加密货币）"""
    if not symbol:
        return None

    sym_clean = symbol.strip().lstrip("$")
    sym_upper = sym_clean.upper()
    sym_lower = sym_clean.lower()

    for key, val in SYMBOL_MAP.items():
        if key.upper() == sym_upper or key.lower() == sym_lower:
            if val[1] == "crypto":
                return val[0]

    return None


def _parse_sina_response(raw_line: str, data_type: str) -> dict | None:
    """解析新浪财经的返回数据"""
    # 格式: var hq_str_CODE="字段1,字段2,...";
    match = re.search(r'var hq_str_([^=]+)="([^"]*)"', raw_line)
    if not match:
        return None

    code = match.group(1)
    data_str = match.group(2)

    if not data_str:
        return None

    fields = data_str.split(",")

    try:
        if data_type in ("us_stock", "us_etf"):
            # 美股格式: 名称,现价,涨跌幅,日期时间,涨跌额,开盘,最高,最低,52周高,52周低,成交量,...
            if len(fields) < 9:
                return None
            name = fields[0]
            price = float(fields[1])
            change_pct = float(fields[2])
            change_amt = float(fields[4]) if fields[4] else 0
            open_price = float(fields[5]) if fields[5] else 0
            high = float(fields[6]) if fields[6] else 0
            low = float(fields[7]) if fields[7] else 0
            date_time = fields[3] if len(fields) > 3 else ""

            return {
                "ticker": code,
                "name": name,
                "price": round(price, 2),
                "change": round(change_amt, 2),
                "change_pct_1d": round(change_pct, 2),
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "latest_date": date_time.split(" ")[0] if " " in date_time else date_time,
                "data_type": data_type,
                "source": "sina",
            }

        elif data_type == "index":
            # 指数格式: 名称,现价,涨跌额,开盘,最高,最低,昨收,买一,卖一,成交量,成交额,涨跌幅...
            if len(fields) < 7:
                return None
            name = fields[0]
            price = float(fields[1])
            change_amt = float(fields[2])
            prev_close = float(fields[6]) if fields[6] else 0
            change_pct = (change_amt / prev_close * 100) if prev_close else 0

            return {
                "ticker": code,
                "name": name,
                "price": round(price, 2),
                "change": round(change_amt, 2),
                "change_pct_1d": round(change_pct, 2),
                "prev_close": round(prev_close, 2),
                "latest_date": "",
                "data_type": data_type,
                "source": "sina",
            }

        elif data_type == "future":
            # 期货格式比较复杂，取前几个关键字段
            if len(fields) < 3:
                return None
            # 期货: 现价,买价,卖价,最高,最低,昨结,开盘,持仓量,成交量...
            try:
                price = float(fields[0])
                prev_settle = float(fields[5]) if len(fields) > 5 and fields[5] else 0
                change = price - prev_settle if prev_settle else 0
                change_pct = (change / prev_settle * 100) if prev_settle else 0
            except (ValueError, IndexError):
                return None

            return {
                "ticker": code,
                "name": code.replace("hf_", ""),
                "price": round(price, 2),
                "change": round(change, 2),
                "change_pct_1d": round(change_pct, 2),
                "prev_settle": round(prev_settle, 2),
                "latest_date": "",
                "data_type": data_type,
                "source": "sina",
            }

        elif data_type == "forex":
            # 外汇格式: 时间, 买价, 卖价, 最高, 最低, 昨收, 开盘...
            if len(fields) < 7:
                return None
            # 外汇的字段顺序不太一样，需要特殊处理
            # 新浪外汇: 时间,买入价,卖出价,最高价,最低价,昨收,开盘
            try:
                price = float(fields[1])  # 买入价作为当前价
                prev_close = float(fields[5]) if len(fields) > 5 and fields[5] else 0
                change = price - prev_close if prev_close else 0
                change_pct = (change / prev_close * 100) if prev_close else 0
            except (ValueError, IndexError):
                return None

            return {
                "ticker": code,
                "name": code.replace("fx_", ""),
                "price": round(price, 4),
                "change": round(change, 4),
                "change_pct_1d": round(change_pct, 2),
                "prev_close": round(prev_close, 4) if prev_close else None,
                "latest_date": fields[0] if fields[0] else "",
                "data_type": data_type,
                "source": "sina",
            }

    except (ValueError, IndexError):
        return None

    return None


def _fetch_sina_batch(codes: list[str], data_types: dict[str, str]) -> dict[str, dict]:
    """批量获取新浪行情（一次请求最多 ~80 个代码）"""
    if not codes:
        return {}

    results = {}
    # 分批获取，每批 50 个
    batch_size = 50
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        url = "https://hq.sinajs.cn/list=" + ",".join(batch)

        try:
            r = requests.get(url, headers=_SINA_HEADERS, timeout=10)
            r.encoding = "gbk"
            lines = r.text.strip().split("\n")

            for line in lines:
                match = re.search(r'var hq_str_([^=]+)="', line)
                if match:
                    code = match.group(1)
                    dtype = data_types.get(code, "us_stock")
                    parsed = _parse_sina_response(line, dtype)
                    if parsed:
                        results[code] = parsed
        except Exception:
            pass

        # 批次之间休息一下
        if i + batch_size < len(codes):
            time.sleep(0.5)

    return results


def _fetch_coingecko_batch(coin_ids: list[str]) -> dict[str, dict]:
    """批量获取 CoinGecko 加密货币行情（一次最多 250 个）"""
    if not coin_ids:
        return {}

    results = {}
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": ",".join(coin_ids),
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_last_updated_at": "true",
        }
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            for cid, info in data.items():
                price = info.get("usd", 0)
                change_24h = info.get("usd_24h_change", 0)
                results[cid] = {
                    "ticker": cid,
                    "name": cid.capitalize(),
                    "price": round(price, 2),
                    "change": round(price * change_24h / 100, 2) if price else 0,
                    "change_pct_1d": round(change_24h, 2),
                    "latest_date": "",
                    "data_type": "crypto",
                    "source": "coingecko",
                }
    except Exception:
        pass

    return results


def _get_price(symbol: str, asset_type: str = "", use_cache: bool = True) -> dict | None:
    """获取单个资产的价格（带缓存）"""
    global _price_cache, _cache_timestamp

    resolved = _resolve_sina_code(symbol, asset_type)
    if not resolved:
        return None

    sina_code, dtype = resolved

    # 缓存命中
    now = time.time()
    if use_cache and sina_code in _price_cache and (now - _cache_timestamp) < CACHE_TTL:
        return _price_cache[sina_code]

    # 实际获取
    results = _fetch_sina_batch([sina_code], {sina_code: dtype})
    result = results.get(sina_code)

    if result:
        _price_cache[sina_code] = result
        _cache_timestamp = now

    return result


def enrich_assets_with_prices(assets: list[dict]) -> list[dict]:
    """
    为资产列表添加价格数据（批量获取，效率更高）
    支持新浪财经（美股/ETF/指数/期货/外汇）+ CoinGecko（加密货币）

    Args:
        assets: 资产列表，每项需包含 symbol 和 type 字段

    Returns:
        enriched assets list，每项增加 price_data 字段
    """
    enriched = []
    # 新浪财经: sina_code -> list of asset indices
    sina_code_map: dict[str, list[int]] = {}
    sina_data_types: dict[str, str] = {}
    # CoinGecko: coin_id -> list of asset indices
    coingecko_map: dict[str, list[int]] = {}

    # 第一遍：解析所有资产的代码
    for i, asset in enumerate(assets):
        symbol = asset.get("symbol", "")
        atype = asset.get("type", "")
        asset_copy = dict(asset)

        # 先试 CoinGecko（加密货币）
        cg_id = _resolve_coingecko_id(symbol, atype)
        if cg_id:
            asset_copy["_cg_id"] = cg_id
            if cg_id not in coingecko_map:
                coingecko_map[cg_id] = []
            coingecko_map[cg_id].append(i)
            enriched.append(asset_copy)
            continue

        # 再试新浪财经
        resolved = _resolve_sina_code(symbol, atype)
        if resolved:
            sina_code, dtype = resolved
            asset_copy["_sina_code"] = sina_code
            if sina_code not in sina_code_map:
                sina_code_map[sina_code] = []
                sina_data_types[sina_code] = dtype
            sina_code_map[sina_code].append(i)
        else:
            asset_copy["price_data"] = None
            asset_copy["price_available"] = False

        enriched.append(asset_copy)

    # 批量获取新浪价格
    if sina_code_map:
        all_codes = list(sina_code_map.keys())
        price_results = _fetch_sina_batch(all_codes, sina_data_types)
        for sina_code, indices in sina_code_map.items():
            price_data = price_results.get(sina_code)
            for idx in indices:
                if price_data:
                    enriched[idx]["price_data"] = price_data
                    enriched[idx]["price_available"] = True
                else:
                    enriched[idx]["price_data"] = None
                    enriched[idx]["price_available"] = False

    # 批量获取 CoinGecko 价格
    if coingecko_map:
        all_coins = list(coingecko_map.keys())
        cg_results = _fetch_coingecko_batch(all_coins)
        for cg_id, indices in coingecko_map.items():
            price_data = cg_results.get(cg_id)
            for idx in indices:
                if price_data:
                    enriched[idx]["price_data"] = price_data
                    enriched[idx]["price_available"] = True
                else:
                    enriched[idx]["price_data"] = None
                    enriched[idx]["price_available"] = False

    # 清理临时字段
    for a in enriched:
        a.pop("_sina_code", None)
        a.pop("_cg_id", None)

    return enriched


def enrich_brief_with_prices(brief: dict) -> dict:
    """
    为整个简报数据添加价格信息

    在 top_assets 中每个资产增加 price_data 字段，包含：
    - price: 当前价格
    - change_pct_1d: 1日涨跌幅 (%)
    - change: 涨跌额
    - latest_date: 最新数据日期
    - data_type: 数据类型
    """
    if not brief or "top_assets" not in brief:
        return brief

    # 只取前 20 个资产查询价格
    assets = brief.get("top_assets", [])[:20]
    enriched = enrich_assets_with_prices(assets)

    # 回填
    result = dict(brief)
    result["top_assets"] = enriched + brief.get("top_assets", [])[20:]

    # 价格统计
    priced_count = sum(1 for a in enriched if a.get("price_available"))
    result["stats"] = dict(result.get("stats", {}))
    result["stats"]["assets_with_price"] = priced_count
    result["stats"]["assets_total"] = len(brief.get("top_assets", []))

    # 为主题信号添加代表资产价格
    theme_signals = result.get("theme_signals", [])
    theme_rep_map = _get_theme_representatives()

    # 分离新浪和 CoinGecko 的代表资产
    sina_rep_codes = []
    sina_rep_dtypes = {}
    cg_rep_ids = []
    theme_to_code = {}  # theme -> (code, source)

    for theme, (code, source) in theme_rep_map.items():
        theme_to_code[theme] = (code, source)
        if source == "sina":
            sina_rep_codes.append(code)
            # 推断 data_type
            if code.startswith("gb_"):
                sina_rep_dtypes[code] = "us_etf" if code in ("gb_tlt", "gb_spy", "gb_kweb") else "us_stock"
            elif code.startswith("int_"):
                sina_rep_dtypes[code] = "index"
            elif code.startswith("hf_"):
                sina_rep_dtypes[code] = "future"
            elif code.startswith("fx_"):
                sina_rep_dtypes[code] = "forex"
            else:
                sina_rep_dtypes[code] = "us_stock"
        elif source == "coingecko":
            cg_rep_ids.append(code)

    rep_prices = {}
    if sina_rep_codes:
        rep_prices.update(_fetch_sina_batch(sina_rep_codes, sina_rep_dtypes))
    if cg_rep_ids:
        rep_prices.update(_fetch_coingecko_batch(cg_rep_ids))

    for ts in theme_signals:
        theme = ts.get("theme", "")
        if theme in theme_to_code:
            code, _ = theme_to_code[theme]
            if code in rep_prices:
                ts["representative_price"] = rep_prices[code]

    return result


def _get_theme_representatives() -> dict[str, tuple[str, str]]:
    """获取每个主题的代表性资产
    返回格式: {theme: (code, source_type)}
    source_type: 'sina' 或 'coingecko'
    """
    return {
        "美债_固定收益": ("gb_tlt", "sina"),
        "黄金_贵金属": ("hf_GC", "sina"),
        "原油_能源": ("hf_CL", "sina"),
        "AI_科技": ("gb_nvda", "sina"),
        "加密货币": ("bitcoin", "coingecko"),
        "美股_大盘": ("gb_spy", "sina"),
        "A股_港股": ("gb_kweb", "sina"),
        "外汇_汇率": ("fx_susdcny", "sina"),
        "宏观_利率政策": ("gb_tlt", "sina"),
        "地缘政治": ("int_vix", "sina"),
        "公司_财报": ("gb_spy", "sina"),
    }


def save_cache(filepath: str = "data/price_cache.json") -> None:
    """保存价格缓存到文件"""
    cache_data = {
        "timestamp": _cache_timestamp,
        "data": _price_cache,
    }
    Path(filepath).parent.mkdir(exist_ok=True)
    Path(filepath).write_text(
        json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_cache(filepath: str = "data/price_cache.json") -> bool:
    """从文件加载价格缓存"""
    global _price_cache, _cache_timestamp
    p = Path(filepath)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        _price_cache = data.get("data", {})
        _cache_timestamp = data.get("timestamp", 0)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    # 快速测试
    print("asset_price 模块测试（新浪财经数据源）")
    print("=" * 60)

    test_assets = [
        {"symbol": "BTC", "type": "加密货币", "mention_count": 5},
        {"symbol": "GLD", "type": "黄金_ETF", "mention_count": 3},
        {"symbol": "TLT", "type": "美债_ETF", "mention_count": 2},
        {"symbol": "NVDA", "type": "科技股", "mention_count": 4},
        {"symbol": "SPY", "type": "美股_ETF", "mention_count": 1},
        {"symbol": "黄金", "type": "贵金属", "mention_count": 2},
        {"symbol": "原油", "type": "能源", "mention_count": 1},
        {"symbol": "人民币", "type": "外汇", "mention_count": 1},
        {"symbol": "VIX", "type": "波动率", "mention_count": 1},
        {"symbol": "KWEB", "type": "中概", "mention_count": 1},
    ]

    print(f"\n测试 {len(test_assets)} 个资产...\n")
    enriched = enrich_assets_with_prices(test_assets)

    success = 0
    for a in enriched:
        sym = a["symbol"]
        pd = a.get("price_data")
        if pd:
            success += 1
            name = pd.get("name", sym)
            print(
                f"  ✅ {sym:8s} {name[:15]:>15s}  "
                f"${pd['price']:>10.2f}  "
                f"1d: {pd['change_pct_1d']:+6.2f}%"
            )
        else:
            print(f"  ❌ {sym:8s}  (无价格数据)")

    print(f"\n成功率: {success}/{len(test_assets)} ({success/len(test_assets)*100:.0f}%)")
