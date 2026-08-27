"""
资产价格联动模块 — 获取行情数据、计算信号收益

数据源：Yahoo Finance（免费，无需API key）
支持：美股、ETF、加密货币、外汇、大宗商品
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.parse import urlencode


class AssetPriceFetcher:
    """资产价格获取器（基于 Yahoo Finance）"""

    def __init__(self, cache_dir: str = "price_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._cache = {}  # symbol -> {date: price}

    def _get_cache_path(self, symbol: str) -> str:
        return os.path.join(self.cache_dir, f"{symbol.upper()}.json")

    def _load_cache(self, symbol: str) -> Optional[Dict[str, float]]:
        if symbol in self._cache:
            return self._cache[symbol]
        
        path = self._get_cache_path(symbol)
        if os.path.exists(path):
            # 检查缓存是否过期（超过1天）
            mtime = os.path.getmtime(path)
            if time.time() - mtime < 86400:  # 24小时内有效
                with open(path, "r") as f:
                    data = json.load(f)
                self._cache[symbol] = data
                return data
        return None

    def _save_cache(self, symbol: str, data: Dict[str, float]):
        self._cache[symbol] = data
        path = self._get_cache_path(symbol)
        with open(path, "w") as f:
            json.dump(data, f)

    def fetch_historical_prices(
        self,
        symbol: str,
        days: int = 90,
    ) -> Dict[str, float]:
        """
        获取某资产的历史日线价格
        
        返回: {日期字符串(YYYYMMDD): 收盘价}
        """
        # 先查缓存
        cached = self._load_cache(symbol)
        if cached and len(cached) >= days * 0.8:
            return cached
        
        try:
            # Yahoo Finance chart API
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=days + 10)  # 多取几天以防节假日
            
            period1 = int(start_dt.timestamp())
            period2 = int(end_dt.timestamp())
            
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                   f"?period1={period1}&period2={period2}&interval=1d")
            
            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            
            result = data.get("chart", {}).get("result", [])
            if not result:
                return {}
            
            timestamps = result[0].get("timestamp", [])
            closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            
            prices = {}
            for ts, close in zip(timestamps, closes):
                if close is not None:
                    dt = datetime.fromtimestamp(ts)
                    date_str = dt.strftime("%Y%m%d")
                    prices[date_str] = round(float(close), 2)
            
            if prices:
                self._save_cache(symbol, prices)
            
            return prices
            
        except Exception as e:
            print(f"获取 {symbol} 价格失败: {e}")
            return {}

    def get_price_on_date(self, symbol: str, date_str: str) -> Optional[float]:
        """获取某一天的价格（找不到就找最近的）"""
        prices = self.fetch_historical_prices(symbol, days=30)
        if not prices:
            return None
        
        if date_str in prices:
            return prices[date_str]
        
        # 找最近的有数据的日子（前后3天内）
        target_dt = datetime.strptime(date_str, "%Y%m%d")
        for offset in range(1, 4):
            for delta in [-offset, offset]:
                check_dt = target_dt + timedelta(days=delta)
                check_str = check_dt.strftime("%Y%m%d")
                if check_str in prices:
                    return prices[check_str]
        
        return None

    def calculate_return(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> Optional[float]:
        """计算两个日期之间的涨跌幅（百分比）"""
        prices = self.fetch_historical_prices(symbol, days=90)
        if not prices:
            return None
        
        start_price = self.get_price_on_date(symbol, start_date)
        end_price = self.get_price_on_date(symbol, end_date)
        
        if start_price and end_price and start_price > 0:
            return round((end_price - start_price) / start_price * 100, 2)
        
        return None

    def get_recent_performance(
        self,
        symbol: str,
        periods: Optional[List[int]] = None,
    ) -> Dict[str, Optional[float]]:
        """
        获取近期表现（1天/7天/30天/90天涨跌幅）
        
        返回: {"1d": x%, "7d": x%, "30d": x%, "90d": x%}
        """
        if periods is None:
            periods = [1, 7, 30, 90]
        
        prices = self.fetch_historical_prices(symbol, days=100)
        if not prices:
            return {f"{p}d": None for p in periods}
        
        sorted_dates = sorted(prices.keys())
        if not sorted_dates:
            return {f"{p}d": None for p in periods}
        
        latest_date = sorted_dates[-1]
        latest_price = prices[latest_date]
        
        result = {}
        latest_dt = datetime.strptime(latest_date, "%Y%m%d")
        
        for period in periods:
            target_dt = latest_dt - timedelta(days=period)
            target_price = None
            
            # 找最近的有数据的日子
            for offset in range(0, 5):
                for delta in [-offset, offset] if offset > 0 else [0]:
                    check_dt = target_dt + timedelta(days=delta)
                    check_str = check_dt.strftime("%Y%m%d")
                    if check_str in prices and check_str != latest_date:
                        target_price = prices[check_str]
                        break
                if target_price:
                    break
            
            if target_price and target_price > 0:
                result[f"{period}d"] = round((latest_price - target_price) / target_price * 100, 2)
            else:
                result[f"{period}d"] = None
        
        return result


# 常用资产 symbol 映射（中文名 -> Yahoo Finance symbol）
SYMBOL_MAP = {
    # 美股大盘
    "标普500": "SPY",
    "纳斯达克": "QQQ",
    "道琼斯": "DIA",
    "恐慌指数": "^VIX",
    
    # 科技股
    "英伟达": "NVDA",
    "苹果": "AAPL",
    "微软": "MSFT",
    "谷歌": "GOOGL",
    "亚马逊": "AMZN",
    "Meta": "META",
    "特斯拉": "TSLA",
    "AMD": "AMD",
    "台积电": "TSM",
    
    # ETF
    "半导体ETF": "SOXX",
    "黄金ETF": "GLD",
    "白银ETF": "SLV",
    "美债20年": "TLT",
    "美债10年": "IEF",
    "原油ETF": "USO",
    "能源ETF": "XLE",
    
    # 加密货币
    "比特币": "BTC-USD",
    "以太坊": "ETH-USD",
    "Solana": "SOL-USD",
    
    # 外汇
    "美元指数": "DX-Y.NYB",
    
    # 大宗商品
    "黄金": "GC=F",
    "白银": "SI=F",
    "WTI原油": "CL=F",
    "布伦特原油": "BZ=F",
}


def resolve_symbol(name: str) -> Optional[str]:
    """根据资产名解析 Yahoo Finance symbol"""
    if name.upper() in SYMBOL_MAP.values():
        return name.upper()
    if name in SYMBOL_MAP:
        return SYMBOL_MAP[name]
    # 直接就是 symbol（如 NVDA, AAPL）
    if len(name) <= 5 and name.isalpha():
        return name.upper()
    return None
