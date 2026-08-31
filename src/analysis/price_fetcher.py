"""
资产价格获取模块 — 多数据源 fallback

主数据源：新浪财经（免费、无需API key、覆盖广）
支持：美股、A股、港股、期货（黄金/原油）、外汇、债券ETF

用法:
    from analysis.price_fetcher import PriceFetcher
    pf = PriceFetcher()
    result = pf.get_price('NVDA')  # {'price': 217.55, 'change_pct': -2.05, 'name': '英伟达', ...}
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Dict, Optional
from urllib.request import urlopen, Request


# 资产代码映射表：统一符号 -> 新浪代码 + 类型
SYMBOL_MAP = {
    # ===== 美股 =====
    'NVDA':   {'sina': 'gb_nvda',   'type': 'us',     'name': '英伟达'},
    'TSLA':   {'sina': 'gb_tsla',   'type': 'us',     'name': '特斯拉'},
    'META':   {'sina': 'gb_meta',   'type': 'us',     'name': 'Meta'},
    'AAPL':   {'sina': 'gb_aapl',   'type': 'us',     'name': '苹果'},
    'MSFT':   {'sina': 'gb_msft',   'type': 'us',     'name': '微软'},
    'AMZN':   {'sina': 'gb_amzn',   'type': 'us',     'name': '亚马逊'},
    'GOOGL':  {'sina': 'gb_googl',  'type': 'us',     'name': '谷歌'},
    'SPY':    {'sina': 'gb_spy',    'type': 'us',     'name': '标普500ETF'},
    'QQQ':    {'sina': 'gb_qqq',    'type': 'us',     'name': '纳指100ETF'},
    'TLT':    {'sina': 'gb_tlt',    'type': 'us',     'name': '美债20年+ETF'},
    
    # ===== A股 =====
    '600519': {'sina': 'sh600519',  'type': 'cn',     'name': '贵州茅台'},
    '300750': {'sina': 'sz300750',  'type': 'cn',     'name': '宁德时代'},
    '000001': {'sina': 'sh000001',  'type': 'cn_idx', 'name': '上证指数'},
    '399001': {'sina': 'sz399001',  'type': 'cn_idx', 'name': '深证成指'},
    '399006': {'sina': 'sz399006',  'type': 'cn_idx', 'name': '创业板指'},
    'SSE':    {'sina': 'sh000001',  'type': 'cn_idx', 'name': '上证指数'},
    
    # ===== 港股 =====
    '00700':  {'sina': 'hk00700',   'type': 'hk',     'name': '腾讯控股'},
    'HSI':    {'sina': 'hkHSI',     'type': 'hk_idx', 'name': '恒生指数'},
    
    # ===== 期货 =====
    'GC=F':   {'sina': 'hf_GC',     'type': 'futures', 'name': 'COMEX黄金'},
    'CL=F':   {'sina': 'hf_CL',     'type': 'futures', 'name': 'WTI原油'},
    'SI=F':   {'sina': 'hf_SI',     'type': 'futures', 'name': 'COMEX白银'},
    'XAU':    {'sina': 'hf_GC',     'type': 'futures', 'name': '黄金'},
    'WTI':    {'sina': 'hf_CL',     'type': 'futures', 'name': '原油'},
    
    # ===== 外汇 =====
    'USDCNY': {'sina': 'fx_susdcny', 'type': 'fx',    'name': '美元/人民币'},
    'EURUSD': {'sina': 'fx_seurusd', 'type': 'fx',    'name': '欧元/美元'},
    'DXY':    {'sina': 'fx_susdcny', 'type': 'fx_proxy', 'name': '美元指数(用USDCNY代理)'},
    
    # ===== 加密货币（Binance / CoinGecko 双 fallback） =====
    'BTC':    {'sina': None, 'type': 'crypto', 'name': '比特币', 'binance': 'BTCUSDT', 'coingecko': 'bitcoin'},
    'ETH':    {'sina': None, 'type': 'crypto', 'name': '以太坊', 'binance': 'ETHUSDT', 'coingecko': 'ethereum'},
    'SOL':    {'sina': None, 'type': 'crypto', 'name': 'Solana', 'binance': 'SOLUSDT', 'coingecko': 'solana'},
    'BNB':    {'sina': None, 'type': 'crypto', 'name': 'BNB', 'binance': 'BNBUSDT', 'coingecko': 'binancecoin'},
    'XRP':    {'sina': None, 'type': 'crypto', 'name': '瑞波币', 'binance': 'XRPUSDT', 'coingecko': 'ripple'},
    'DOGE':   {'sina': None, 'type': 'crypto', 'name': '狗狗币', 'binance': 'DOGEUSDT', 'coingecko': 'dogecoin'},
    'BTC-USD': {'sina': None, 'type': 'crypto', 'name': '比特币', 'binance': 'BTCUSDT', 'coingecko': 'bitcoin'},
    'ETH-USD': {'sina': None, 'type': 'crypto', 'name': '以太坊', 'binance': 'ETHUSDT', 'coingecko': 'ethereum'},
    'SOL-USD': {'sina': None, 'type': 'crypto', 'name': 'Solana', 'binance': 'SOLUSDT', 'coingecko': 'solana'},
}

# 主题 -> 代表资产映射
THEME_REPRESENTATIVE_ASSET = {
    "宏观_利率政策": "TLT",
    "美债_固定收益": "TLT",
    "黄金_贵金属": "GC=F",
    "原油_能源": "CL=F",
    "AI_科技": "NVDA",
    "科技股": "QQQ",
    "美股_大盘": "SPY",
    "加密货币": "BTC",
    "外汇_汇率": "USDCNY",
    "地缘政治": "HSI",
    "公司_财报": "SPY",
    "A股_市场": "000001",
}


class PriceFetcher:
    """多数据源价格获取器"""
    
    def __init__(self, cache_dir: str = "price_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._cache: Dict[str, dict] = {}  # symbol -> price data
    
    def _cache_key(self, symbol: str) -> str:
        return symbol.upper()
    
    def _is_cache_valid(self, symbol: str) -> bool:
        """缓存有效期：5分钟（行情数据要新鲜）"""
        key = self._cache_key(symbol)
        if key not in self._cache:
            return False
        cached_at = self._cache[key].get('_cached_at', 0)
        return time.time() - cached_at < 300  # 5分钟
    
    def get_price(self, symbol: str) -> Optional[dict]:
        """获取资产最新价格
        
        返回: {
            'symbol': 'NVDA',
            'name': '英伟达',
            'price': 217.55,
            'prev_close': 228.0,
            'change_pct': -4.58,
            'change_abs': -10.45,
            'high': 229.26,
            'low': 216.81,
            'source': 'sina',
        }
        """
        key = self._cache_key(symbol)
        
        # 命中缓存
        if self._is_cache_valid(symbol):
            return {k: v for k, v in self._cache[key].items() if not k.startswith('_')}
        
        # 查映射表
        mapping = SYMBOL_MAP.get(key)
        if not mapping:
            # 尝试直接匹配（美股代码）
            mapping = SYMBOL_MAP.get(key, {'sina': f'gb_{key.lower()}', 'type': 'us', 'name': key})
        
        sina_code = mapping.get('sina')
        asset_type = mapping.get('type', 'us')
        name = mapping.get('name', symbol)

        # 加密货币走 Binance / CoinGecko 双 fallback
        if asset_type == 'crypto':
            binance_symbol = mapping.get('binance')
            coingecko_id = mapping.get('coingecko')

            # 先试 Binance
            if binance_symbol:
                result = self._fetch_binance(binance_symbol)
                if result:
                    result['symbol'] = key
                    result['name'] = name
                    result['source'] = 'binance'
                    result['_cached_at'] = time.time()
                    self._cache[key] = result
                    return {k: v for k, v in result.items() if not k.startswith('_')}

            # 再试 CoinGecko
            if coingecko_id:
                result = self._fetch_coingecko(coingecko_id)
                if result:
                    result['symbol'] = key
                    result['name'] = name
                    result['source'] = 'coingecko'
                    result['_cached_at'] = time.time()
                    self._cache[key] = result
                    return {k: v for k, v in result.items() if not k.startswith('_')}

            return None

        if not sina_code:
            # 没有新浪代码，返回 None
            return None
        
        # 从新浪获取
        result = self._fetch_sina(sina_code, asset_type)
        if result:
            result['symbol'] = key
            result['name'] = name
            result['source'] = 'sina'
            result['_cached_at'] = time.time()
            self._cache[key] = result
            return {k: v for k, v in result.items() if not k.startswith('_')}
        
        return None
    
    def _fetch_sina(self, code: str, asset_type: str) -> Optional[dict]:
        """从新浪财经获取行情"""
        url = f'https://hq.sinajs.cn/list={code}'
        req = Request(url, headers={
            'Referer': 'https://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        try:
            with urlopen(req, timeout=10) as resp:
                raw = resp.read().decode('gbk')
        except Exception:
            return None
        
        if '=\"\"' in raw:
            return None
        
        try:
            content = raw.split('"')[1]
            parts = content.split(',')
        except (IndexError, AttributeError):
            return None
        
        if not parts or not parts[0]:
            return None
        
        # 按类型解析
        if asset_type == 'us':
            return self._parse_us(parts)
        elif asset_type in ('cn', 'cn_idx'):
            return self._parse_cn(parts, asset_type)
        elif asset_type in ('hk', 'hk_idx'):
            return self._parse_hk(parts)
        elif asset_type == 'futures':
            return self._parse_futures(parts)
        elif asset_type == 'fx':
            return self._parse_fx(parts)
        elif asset_type == 'fx_proxy':
            # 美元指数用 USDCNY 代理，取反
            data = self._parse_fx(parts)
            if data and data.get('change_pct') is not None:
                data['change_pct'] = -data['change_pct']  # 反向
            return data
        
        return None
    
    def _parse_us(self, parts: list) -> dict:
        """解析美股格式
        [0]名称, [1]现价, [2]涨跌额, [3]日期时间, [4]涨跌额(?), [5]开盘, [6]最高, [7]最低...
        """
        try:
            price = float(parts[1]) if parts[1] else 0
            change_abs = float(parts[2]) if parts[2] else 0
            prev_close = price - change_abs
            change_pct = (change_abs / prev_close * 100) if prev_close else 0
            return {
                'price': round(price, 2),
                'prev_close': round(prev_close, 2),
                'change_pct': round(change_pct, 2),
                'change_abs': round(change_abs, 2),
                'open': float(parts[5]) if len(parts) > 5 and parts[5] else None,
                'high': float(parts[6]) if len(parts) > 6 and parts[6] else None,
                'low': float(parts[7]) if len(parts) > 7 and parts[7] else None,
            }
        except (ValueError, IndexError):
            return None
    
    def _parse_cn(self, parts: list, asset_type: str) -> dict:
        """解析A股格式
        [0]名称, [1]开盘, [2]昨收, [3]现价, [4]最高, [5]最低, ...
        """
        try:
            if asset_type == 'cn_idx':
                # 指数格式
                price = float(parts[3]) if len(parts) > 3 and parts[3] else 0
                prev_close = float(parts[2]) if len(parts) > 2 and parts[2] else 0
            else:
                # 个股格式
                price = float(parts[3]) if len(parts) > 3 and parts[3] else 0
                prev_close = float(parts[2]) if len(parts) > 2 and parts[2] else 0
            
            change_abs = price - prev_close
            change_pct = (change_abs / prev_close * 100) if prev_close else 0
            return {
                'price': round(price, 2),
                'prev_close': round(prev_close, 2),
                'change_pct': round(change_pct, 2),
                'change_abs': round(change_abs, 2),
                'open': float(parts[1]) if len(parts) > 1 and parts[1] else None,
                'high': float(parts[4]) if len(parts) > 4 and parts[4] else None,
                'low': float(parts[5]) if len(parts) > 5 and parts[5] else None,
            }
        except (ValueError, IndexError):
            return None
    
    def _parse_hk(self, parts: list) -> dict:
        """解析港股格式
        [0]英文名称, [1]中文名称, [2]现价, [3]昨收, [4]最高, [5]最低, [6]?, [7]涨跌额, [8]涨跌幅%
        """
        try:
            price = float(parts[2]) if len(parts) > 2 and parts[2] else 0
            prev_close = float(parts[3]) if len(parts) > 3 and parts[3] else 0
            change_pct = float(parts[8]) if len(parts) > 8 and parts[8] else 0
            change_abs = float(parts[7]) if len(parts) > 7 and parts[7] else 0
            return {
                'price': round(price, 2),
                'prev_close': round(prev_close, 2),
                'change_pct': round(change_pct, 2),
                'change_abs': round(change_abs, 2),
                'high': float(parts[4]) if len(parts) > 4 and parts[4] else None,
                'low': float(parts[5]) if len(parts) > 5 and parts[5] else None,
            }
        except (ValueError, IndexError):
            return None
    
    def _parse_futures(self, parts: list) -> dict:
        """解析期货格式
        [0]现价, [1]空, [2]开盘, [3]买价, [4]最高, [5]最低, [6]时间, [7]昨结算, [8]昨收, ...
        """
        try:
            price = float(parts[0]) if parts[0] else 0
            prev_close = float(parts[7]) if len(parts) > 7 and parts[7] else 0
            if not prev_close:
                prev_close = float(parts[8]) if len(parts) > 8 and parts[8] else 0
            change_abs = price - prev_close
            change_pct = (change_abs / prev_close * 100) if prev_close else 0
            return {
                'price': round(price, 2),
                'prev_close': round(prev_close, 2),
                'change_pct': round(change_pct, 2),
                'change_abs': round(change_abs, 2),
                'open': float(parts[2]) if len(parts) > 2 and parts[2] else None,
                'high': float(parts[4]) if len(parts) > 4 and parts[4] else None,
                'low': float(parts[5]) if len(parts) > 5 and parts[5] else None,
            }
        except (ValueError, IndexError):
            return None
    
    def _parse_fx(self, parts: list) -> dict:
        """解析外汇格式
        [0]时间, [1]现价, [2]昨收, [3]今开?, [4]涨跌点, [5]最低, [6]?, [7]?, [8]?, [9]名称
        """
        try:
            # 外汇格式：第一个字段是时间，价格在第二个
            # 如果第一个字段看起来像时间（含冒号），从 [1] 开始读
            if ':' in parts[0]:
                price = float(parts[1]) if len(parts) > 1 and parts[1] else 0
                prev_close = float(parts[2]) if len(parts) > 2 and parts[2] else 0
                high = float(parts[3]) if len(parts) > 3 and parts[3] else None
                low = float(parts[5]) if len(parts) > 5 and parts[5] else None
                open_p = float(parts[6]) if len(parts) > 6 and parts[6] else None
            else:
                price = float(parts[0]) if parts[0] else 0
                prev_close = price - (float(parts[1]) if len(parts) > 1 and parts[1] else 0)
                high = float(parts[3]) if len(parts) > 3 and parts[3] else None
                low = float(parts[4]) if len(parts) > 4 and parts[4] else None
                open_p = float(parts[5]) if len(parts) > 5 and parts[5] else None
            
            change_abs = price - prev_close
            change_pct = (change_abs / prev_close * 100) if prev_close else 0
            return {
                'price': round(price, 4),
                'prev_close': round(prev_close, 4),
                'change_pct': round(change_pct, 2),
                'change_abs': round(change_abs, 4),
                'open': round(open_p, 4) if open_p else None,
                'high': round(high, 4) if high else None,
                'low': round(low, 4) if low else None,
            }
        except (ValueError, IndexError):
            return None
    
    def _fetch_binance(self, symbol: str) -> Optional[dict]:
        """从 Binance 获取加密货币 24h 行情

        API: GET /api/v3/ticker/24hr?symbol=BTCUSDT
        无需 API key，公开接口
        """
        url = f'https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}'
        req = Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
        })
        try:
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception:
            return None

        if not isinstance(data, dict) or 'lastPrice' not in data:
            return None

        try:
            price = float(data['lastPrice'])
            change_pct = float(data.get('priceChangePercent', 0))
            change_abs = float(data.get('priceChange', 0))
            prev_close = price - change_abs
            return {
                'price': round(price, 2),
                'prev_close': round(prev_close, 2),
                'change_pct': round(change_pct, 2),
                'change_abs': round(change_abs, 2),
                'open': float(data.get('openPrice', 0)) or None,
                'high': float(data.get('highPrice', 0)) or None,
                'low': float(data.get('lowPrice', 0)) or None,
                'volume': float(data.get('volume', 0)),
            }
        except (ValueError, KeyError):
            return None

    def _fetch_coingecko(self, coin_id: str) -> Optional[dict]:
        """从 CoinGecko 获取加密货币 24h 行情（Binance 不可用时的 fallback）

        API: GET /api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true
        无需 API key，公开接口（有速率限制）
        """
        url = (f'https://api.coingecko.com/api/v3/simple/price'
               f'?ids={coin_id}&vs_currencies=usd'
               f'&include_24hr_change=true&include_24hr_vol=true&include_last_updated_at=true')
        req = Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
        })
        try:
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception:
            return None

        if not isinstance(data, dict) or coin_id not in data:
            return None

        coin = data[coin_id]
        try:
            price = float(coin.get('usd', 0))
            change_pct = float(coin.get('usd_24h_change', 0))
            change_abs = price * change_pct / 100 if price else 0
            prev_close = price - change_abs
            return {
                'price': round(price, 2),
                'prev_close': round(prev_close, 2),
                'change_pct': round(change_pct, 2),
                'change_abs': round(change_abs, 2),
                'open': None,  # CoinGecko simple API 不提供开盘价
                'high': None,  # 不提供最高价
                'low': None,   # 不提供最低价
                'volume': float(coin.get('usd_24h_vol', 0)),
            }
        except (ValueError, KeyError):
            return None

    def batch_get(self, symbols: list) -> Dict[str, dict]:
        """批量获取价格（合并请求，减少API调用）"""
        results = {}
        # 先检查缓存
        uncached = []
        for sym in symbols:
            if self._is_cache_valid(sym):
                results[sym.upper()] = self.get_price(sym)
            else:
                uncached.append(sym)
        
        # 对新浪支持的资产，按类型分批请求
        # （新浪支持同类型批量，但不同类型格式不同，所以分开处理）
        for sym in uncached:
            result = self.get_price(sym)
            if result:
                results[sym.upper()] = result
            time.sleep(0.1)  # 限速
        
        return results


def enrich_brief_with_prices_v2(brief: dict) -> dict:
    """为 v2 格式简报添加价格数据（新版）
    
    使用新浪财经数据源，支持 top_assets/top_themes 列表格式
    """
    pf = PriceFetcher(cache_dir="price_cache")
    
    assets_with_price = 0
    assets_total = 0
    
    # 1. 为 top_assets 列表添加价格
    if "top_assets" in brief:
        # 收集所有 symbol
        symbols = [a.get('symbol', '') for a in brief['top_assets'] if a.get('symbol')]
        prices = pf.batch_get(symbols)
        
        for asset_data in brief['top_assets']:
            assets_total += 1
            sym = asset_data.get('symbol', '').upper()
            price_data = prices.get(sym)
            if price_data:
                asset_data['price'] = price_data['price']
                asset_data['price_change_1d'] = price_data['change_pct']
                asset_data['price_change_abs'] = price_data.get('change_abs')
                asset_data['prev_close'] = price_data.get('prev_close')
                asset_data['price_symbol'] = price_data.get('symbol', sym)
                asset_data['price_name'] = price_data.get('name', '')
                assets_with_price += 1
    
    # 2. 为 top_themes 列表添加代表资产价格
    if "top_themes" in brief:
        for theme_data in brief['top_themes']:
            theme_name = theme_data.get('theme', '')
            rep_asset = THEME_REPRESENTATIVE_ASSET.get(theme_name)
            if rep_asset:
                price_data = pf.get_price(rep_asset)
                if price_data:
                    theme_data['representative_asset'] = rep_asset
                    theme_data['asset_price'] = price_data['price']
                    theme_data['asset_change_1d'] = price_data['change_pct']
                    theme_data['asset_price_name'] = price_data.get('name', '')
    
    # 3. 更新统计
    if "stats" in brief:
        brief['stats']['assets_with_price'] = assets_with_price
        brief['stats']['assets_total'] = assets_total
    
    return brief
