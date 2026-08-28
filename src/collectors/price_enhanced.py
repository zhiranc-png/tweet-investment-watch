# -*- coding: utf-8 -*-
"""
资产价格增强模块（稳定版）
多源价格获取：新浪财经(A股/港股/期货/外汇) + FRED(美债收益率)

稳定性改进：
- 每个数据源 3 次重试 + 指数退避
- 单资产失败不影响其他
- 5 分钟缓存，避免重复请求
- 全部异常捕获，失败返回 None 而非崩溃
"""
import json
import time
import datetime as dt
from typing import Dict, Optional, List
import requests

TZ8 = dt.timezone(dt.timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

MAX_RETRIES = 3
BASE_BACKOFF = 2.0

# ── 新浪财经行情 ──────────────────────────────────────────

SINA_CODE_MAP = {
    # A股指数
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "创业板指": "sz399006",
    "科创50": "sh000688",
    # 港股
    "恒生指数": "hkHSI",
    "恒生科技": "hkHSTECH",
    # 期货/大宗商品
    "黄金": "hf_GC",
    "原油": "hf_CL",
    "白银": "hf_SI",
    "铜": "hf_CU",
    # 外汇
    "美元人民币": "fx_susdcny",
    "欧元美元": "fx_eurusd",
    "美元日元": "fx_usdjpy",
    # A股个股（核心资产）
    "贵州茅台": "sh600519",
    "宁德时代": "sz300750",
    "比亚迪": "sz002594",
    "招商银行": "sh600036",
    # 港股个股
    "腾讯": "hk00700",
    "阿里巴巴": "hk09988",
    "美团": "hk03690",
}


def _retry_request(url, headers=None, timeout=10, retries=MAX_RETRIES):
    """带重试的 HTTP GET 请求"""
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


def sina_quote(code: str) -> Optional[Dict]:
    """
    新浪财经实时行情
    code: 新浪代码，如 sh000001 / hkHSI / hf_GC
    返回: {name, price, prev_close, change, change_pct, high, low, volume, source, timestamp}
    失败返回 None
    """
    url = f"https://hq.sinajs.cn/list={code}"
    headers = {"Referer": "https://finance.sina.com.cn", "User-Agent": UA}
    try:
        r = _retry_request(url, headers=headers, timeout=10)
        text = r.content.decode("gbk", errors="replace")
        if '="' not in text:
            return None
        body = text.split('="', 1)[1].rstrip('";\n ')
        fields = body.split(",")
        if len(fields) < 4:
            return None

        name = fields[0]

        # 港股字段：0=简称 1=英文名 2=今开 3=昨收 4=最高 5=最低 6=现价 ... 12=成交量
        if code.startswith("hk") and len(fields) > 6:
            prev_close = float(fields[3]) if fields[3] else 0
            price = float(fields[6]) if fields[6] else 0
            high = float(fields[4]) if fields[4] else 0
            low = float(fields[5]) if fields[5] else 0
            volume = float(fields[12]) if len(fields) > 12 and fields[12] else 0
        # 期货字段：0=名称 1=今开 2=昨收 3=最新价 4=最高 5=最低 6=买价 7=卖价 8=昨结 ... 10=成交量
        elif code.startswith("hf_") and len(fields) > 8:
            prev_close = float(fields[8]) if fields[8] else 0  # 昨结算
            price = float(fields[3]) if fields[3] else 0
            high = float(fields[4]) if fields[4] else 0
            low = float(fields[5]) if fields[5] else 0
            volume = float(fields[10]) if len(fields) > 10 and fields[10] else 0
        # A股/指数标准格式：0=名称 1=今开 2=昨收 3=现价 4=最高 5=最低 ... 8=成交量
        else:
            prev_close = float(fields[2]) if fields[2] else 0
            price = float(fields[3]) if fields[3] else 0
            high = float(fields[4]) if fields[4] else 0
            low = float(fields[5]) if fields[5] else 0
            volume = float(fields[8]) if len(fields) > 8 and fields[8] else 0

        if prev_close == 0 or price == 0:
            return None

        change = price - prev_close
        change_pct = (change / prev_close) * 100

        return {
            "name": name,
            "price": round(price, 4),
            "prev_close": round(prev_close, 4),
            "change": round(change, 4),
            "change_pct": round(change_pct, 2),
            "high": round(high, 4),
            "low": round(low, 4),
            "volume": volume,
            "source": "sina_finance",
            "code": code,
            "timestamp": dt.datetime.now(TZ8).isoformat(),
        }
    except Exception as e:
        print(f"[price] sina {code} 失败: {e}", flush=True)
        return None


# ── FRED 美债收益率 ──────────────────────────────────────

FRED_SERIES = {
    "DGS1MO": "1个月美债收益率",
    "DGS3MO": "3个月美债收益率",
    "DGS6MO": "6个月美债收益率",
    "DGS1": "1年期美债收益率",
    "DGS2": "2年期美债收益率",
    "DGS5": "5年期美债收益率",
    "DGS10": "10年期美债收益率",
    "DGS20": "20年期美债收益率",
    "DGS30": "30年期美债收益率",
    "T10Y2Y": "10Y-2Y 利差",
    "DFF": "联邦基金利率",
}


def fred_yield(series_id: str = "DGS10") -> Optional[Dict]:
    """
    FRED 美债收益率（公开 CSV 接口，无鉴权）
    返回: {series_id, name, date, value, source, timestamp}
    失败返回 None（网络问题/数据缺失都返回 None，不崩溃）
    """
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        r = _retry_request(url, timeout=15, retries=2)  # FRED 只重试 2 次，省时间
        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return None
        # 从最后 10 行里找有效值（周末/节假日可能是 .）
        for line in reversed(lines[-10:]):
            parts = line.strip().split(",")
            if len(parts) == 2 and parts[1] != "." and parts[1]:
                date = parts[0]
                value = float(parts[1])
                return {
                    "series_id": series_id,
                    "name": FRED_SERIES.get(series_id, series_id),
                    "date": date,
                    "value": value,
                    "source": "fred",
                    "timestamp": dt.datetime.now(TZ8).isoformat(),
                }
        return None
    except Exception as e:
        print(f"[price] fred {series_id} 失败: {e}", flush=True)
        return None


# ── 统一入口（带缓存） ────────────────────────────────────

_price_cache = {}
_CACHE_TTL = 300  # 5分钟缓存


def get_price(asset_key: str) -> Optional[Dict]:
    """
    统一价格查询入口
    asset_key: 资产名称（中文），如 "黄金" "上证指数" "10年期美债"
    自动选择数据源，带 5 分钟缓存
    """
    now = time.time()
    if asset_key in _price_cache:
        ts, data = _price_cache[asset_key]
        if now - ts < _CACHE_TTL:
            return data

    result = None

    # 1. 新浪财经（代码映射表）
    if asset_key in SINA_CODE_MAP:
        result = sina_quote(SINA_CODE_MAP[asset_key])

    # 2. FRED 美债收益率（新浪没拿到再试 FRED）
    if result is None:
        fred_map = {
            "10年期美债": "DGS10",
            "2年期美债": "DGS2",
            "30年期美债": "DGS30",
            "5年期美债": "DGS5",
            "1年期美债": "DGS1",
            "3个月美债": "DGS3MO",
            "联邦基金利率": "DFF",
            "10Y-2Y利差": "T10Y2Y",
            "美债收益率": "DGS10",
        }
        if asset_key in fred_map:
            result = fred_yield(fred_map[asset_key])
            if result:
                result["name"] = asset_key

    if result:
        _price_cache[asset_key] = (now, result)
    return result


def get_prices_batch(asset_keys: List[str]) -> Dict[str, Dict]:
    """批量查询价格，返回 {asset_key: price_data}，失败的不包含在结果里"""
    results = {}
    for key in asset_keys:
        try:
            r = get_price(key)
            if r:
                results[key] = r
        except Exception as e:
            print(f"[price] 批量查询 {key} 异常: {e}", flush=True)
        time.sleep(0.3)  # 限速
    return results


def get_all_core_prices() -> Dict[str, Dict]:
    """获取所有核心资产价格（报告用），失败的跳过"""
    core_assets = [
        "上证指数", "创业板指", "恒生指数",
        "黄金", "原油", "白银",
        "美元人民币", "欧元美元",
        "10年期美债", "2年期美债", "30年期美债",
        "贵州茅台", "宁德时代", "腾讯",
    ]
    return get_prices_batch(core_assets)


if __name__ == "__main__":
    print("=== 价格测试 ===")
    prices = get_all_core_prices()
    for k, v in prices.items():
        if "change_pct" in v:
            print(f"  {k}: {v['price']} ({v['change_pct']:+.2f}%) - {v['source']}")
        else:
            print(f"  {k}: {v.get('value', v.get('price'))} - {v['source']}")
    print(f"\n成功: {len(prices)}/14")
