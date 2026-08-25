"""X/Twitter 采集器 - 基于 UserTweets GraphQL API
通过跟踪指定大V账号的推文来获取投资舆情
"""
import os
import re
import json
import time
import requests
from datetime import datetime, timezone, timedelta

BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

# 投资大V列表 (screen_name: 姓名/机构)
# 精选纯投资/财经类账号，去掉杂讯多的科技CEO和政治人物
DEFAULT_INFLUENCERS = {
    # ── 官方/央行/数据机构（高权重，信息权威）──
    "federalreserve": "美联储",
    "ecb": "欧洲央行",
    "bankofengland": "英格兰银行",
    "BLS_gov": "美国劳工统计局",
    "BEA_News": "美国经济分析局",
    "SecDev": "美国SEC",
    "IMFNews": "IMF",
    "OPEC": "OPEC",
    "GOLDCOUNCIL": "世界黄金协会",
    # ── 快讯/实时新闻（速度优先）──
    "DeItaone": "Delta One",
    "LiveSquawk": "LiveSquawk",
    "financialjuice": "Financial Juice",
    "Reuters": "路透社",
    "Bloomberg": "彭博",
    "WSJ": "华尔街日报",
    "FT": "金融时报",
    "CNBC": "CNBC",
    "MarketWatch": "MarketWatch",
    "SeekingAlpha": "Seeking Alpha",
    "Techmeme": "Techmeme",
    # ── 顶级投资人/基金经理（观点权重高）──
    "RayDalio": "瑞·达利欧",
    "BillAckman": "比尔·阿克曼",
    "michaeljburry": "Michael Burry",
    "chamath": "Chamath",
    "CathieDWood": "木头姐",
    "pmarca": "Marc Andreessen (a16z)",
    "RaoulGMI": "Raoul Pal",
    "Arthur_0x": "Arthur Hayes",
    # ── 宏观策略师/分析师（深度分析）──
    "biancoresearch": "Bianco Research",
    "LynAldenContact": "Lyn Alden",
    "LukeGromen": "Luke Gromen",
    "SoberLook": "Sober Look",
    "charliebilello": "Charlie Bilello",
    "LizAnnSonders": "Liz Ann Sonders",
    "TheStalwart": "The Stalwart",
    "zerohedge": "ZeroHedge",
    "HedgeMind": "HedgeMind",
    "downtownjbrown": "Josh Brown",
    "markminervini": "Mark Minervini",
    # ── 大宗商品/能源──
    "JavierBlas": "Javier Blas (彭博大宗商品)",
    # ── 中国/中概/港股──
    "HaoHongCFA": "洪灏",
    "caixin": "财新网",
    "FTChinese": "FT中文网",
    "SCMPNews": "南华早报",
    "realDawningW": "Dawning W (中概股)",
    # ── 科技/AI（投资视角，非产品视角）──
    "a16z": "a16z",
    "verge": "The Verge",
}

# 投资关键词（旧版，保留兼容）
# v2 版本过滤器在 filter.py 中，使用分级评分系统
INVESTMENT_KEYWORDS = [
    # 强相关（命中即算）
    "fed", "federal reserve", "interest rate", "inflation", "recession",
    "earnings", "revenue", "profit", "dividend", "buyback", "ipo",
    "bitcoin", "ethereum", "gold", "silver", "oil", "bond", "treasury",
    "yield", "cpi", "pce", "unemployment", "gdp", "rate cut", "rate hike",
    "fomc", "jackson hole", "central bank", "monetary policy",
    "semiconductor", "chip", "gpu", "ai chip", "computing",
    "标普", "纳斯达克", "恒生指数", "上证指数", "美债", "国债",
    "美联储", "鲍威尔", "加息", "降息", "通胀", "衰退", "财报",
    "半导体", "芯片", "算力", "大模型", "黄金", "原油", "比特币",
    "牛市", "熊市", "抄底", "做空", "做多", "北向资金", "中概股",
    "美股", "港股", "a股", "创业板", "科创板",
    "vix", "波动率", "恐慌指数", "收益率曲线", "软着陆", "滞胀",
]


def parse_twitter_date(date_str):
    """解析 X 的日期格式：'Tue Aug 25 12:34:56 +0000 2026'"""
    try:
        return datetime.strptime(date_str, "%a %b %d %H:%M:%S %z %Y")
    except:
        return None


class XCollector:
    def __init__(self, auth_token=None, ct0=None):
        self.auth_token = auth_token or os.environ.get("AUTH_TOKEN", "")
        self.ct0 = ct0 or os.environ.get("CT0", "")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {BEARER_TOKEN}",
            "x-csrf-token": self.ct0,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": "en",
        })
        self.session.cookies.set("auth_token", self.auth_token, domain=".x.com")
        self.session.cookies.set("ct0", self.ct0, domain=".x.com")
        
        self.query_ids = {}
        self._user_cache = {}  # screen_name -> user_id
        self.features = {
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "tweetypie_unmention_optimization_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "view_counts_everywhere_api_enabled": True,
        }
    
    def _fetch_query_ids(self):
        """从 X 主页 JS 中提取最新的 queryId"""
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        
        resp = s.get("https://x.com/home", timeout=20)
        js_urls = re.findall(
            r'https://abs\.twimg\.com/responsive-web/client-web(?:-legacy)?/main\.[a-f0-9]+\.js',
            resp.text
        )
        if not js_urls:
            js_urls = re.findall(r'src="([^"]*main\.[a-f0-9]+\.js)"', resp.text)
        
        if not js_urls:
            raise Exception("无法找到 main.js")
        
        main_url = js_urls[0]
        if not main_url.startswith("http"):
            main_url = "https://abs.twimg.com" + main_url
        
        resp_js = s.get(main_url, timeout=30)
        js_text = resp_js.text
        
        qids = {}
        for m in re.finditer(r'queryId\s*:\s*"([^"]+)"[^}]*?operationName\s*:\s*"([^"]+)"', js_text):
            qids[m.group(2)] = m.group(1)
        for m in re.finditer(r'operationName\s*:\s*"([^"]+)"[^}]*?queryId\s*:\s*"([^"]+)"', js_text):
            qids[m.group(1)] = m.group(2)
        
        self.query_ids = qids
        return qids
    
    def get_user_id(self, screen_name):
        """获取用户 rest_id"""
        if screen_name in self._user_cache:
            return self._user_cache[screen_name]
        
        if not self.query_ids:
            self._fetch_query_ids()
        
        qid = self.query_ids.get("UserByScreenName", "G3KGOASz96M-Qu0nwmGXNg")
        url = f"https://x.com/i/api/graphql/{qid}/UserByScreenName"
        vars_ = {"screen_name": screen_name, "withSafetyModeUserFields": True}
        
        try:
            resp = self.session.get(
                url,
                params={"variables": json.dumps(vars_), "features": json.dumps(self.features)},
                timeout=15
            )
            
            if resp.status_code != 200:
                # 用备用 queryId
                url = f"https://x.com/i/api/graphql/G3KGOASz96M-Qu0nwmGXNg/UserByScreenName"
                resp = self.session.get(
                    url,
                    params={"variables": json.dumps(vars_), "features": json.dumps(self.features)},
                    timeout=15
                )
            
            data = resp.json()
            if "errors" in data:
                raise Exception(data["errors"][0].get("message", ""))
            
            user_id = data["data"]["user"]["result"]["rest_id"]
            self._user_cache[screen_name] = user_id
            return user_id
        except Exception as e:
            raise Exception(f"获取用户 {screen_name} 失败: {e}")
    
    def get_user_tweets(self, screen_name, count=20):
        """获取指定用户的最新推文"""
        if not self.query_ids:
            self._fetch_query_ids()
        
        user_id = self.get_user_id(screen_name)
        qid = self.query_ids.get("UserTweets", "")
        
        if not qid:
            raise Exception("找不到 UserTweets queryId")
        
        url = f"https://x.com/i/api/graphql/{qid}/UserTweets"
        vars_ = {
            "userId": user_id,
            "count": count,
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": False,
            "withVoice": False,
            "withV2Timeline": True,
        }
        
        resp = self.session.get(
            url,
            params={"variables": json.dumps(vars_), "features": json.dumps(self.features)},
            timeout=15
        )
        
        if resp.status_code != 200:
            raise Exception(f"UserTweets HTTP {resp.status_code}")
        
        data = resp.json()
        if "errors" in data:
            raise Exception(f"UserTweets 错误: {data['errors'][0].get('message', '')}")
        
        tweets = []
        timeline = data["data"]["user"]["result"]["timeline"]["timeline"]
        
        for inst in timeline.get("instructions", []):
            if inst.get("type") != "TimelineAddEntries":
                continue
            for entry in inst.get("entries", []):
                eid = entry.get("entryId", "")
                if not eid.startswith("tweet-"):
                    continue
                
                content = entry.get("content", {})
                item = content.get("itemContent", {})
                tr = item.get("tweet_results", item.get("tweetResult", {}))
                result = tr.get("result", {}) if isinstance(tr, dict) else {}
                legacy = result.get("legacy", {})
                
                if not legacy:
                    continue
                
                user_legacy = result.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {})
                
                likes = legacy.get("favorite_count", 0)
                retweets = legacy.get("retweet_count", 0)
                replies = legacy.get("reply_count", 0)
                views = 0
                views_data = result.get("views", {})
                if isinstance(views_data, dict):
                    try:
                        views = int(views_data.get("count", 0))
                    except (ValueError, TypeError):
                        views = 0
                
                # 热度分：转推*3 + 回复*5 + 浏览量//1000 + 点赞//10
                score = retweets * 3 + replies * 5 + views // 1000 + likes // 10
                
                is_retweet = "retweeted_status_result" in legacy
                created_at = legacy.get("created_at", "")
                
                tweets.append({
                    "id": legacy.get("id_str", ""),
                    "text": legacy.get("full_text", ""),
                    "created_at": created_at,
                    "likes": likes,
                    "retweets": retweets,
                    "replies": replies,
                    "views": views,
                    "score": score,
                    "is_retweet": is_retweet,
                    "user_screen": user_legacy.get("screen_name", screen_name),
                    "user_name": user_legacy.get("name", screen_name),
                    "followers": user_legacy.get("followers_count", 0),
                    "url": f"https://x.com/{user_legacy.get('screen_name', screen_name)}/status/{legacy.get('id_str', '')}",
                })
        
        return tweets
    
    def collect(self, influencers=None, per_user_count=20, filter_investment=True, hours=48):
        """
        采集多个大V的推文（增强版）
        - 分级投资相关性过滤
        - 资产/主题自动提取
        - 按质量分排序
        hours: 只保留最近 N 小时的推文
        返回: list of tweet dicts, 按质量分排序
        """
        if influencers is None:
            influencers = DEFAULT_INFLUENCERS
        
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=hours)
        
        all_tweets = []
        success = 0
        failed = []
        
        for screen_name, display_name in influencers.items():
            try:
                tweets = self.get_user_tweets(screen_name, count=per_user_count)
                # 加上大V的显示名
                for t in tweets:
                    t["influencer_name"] = display_name
                    t["source"] = "x"
                    t["source_detail"] = f"@{screen_name}"
                    t["is_kol"] = True
                all_tweets.extend(tweets)
                success += 1
                time.sleep(0.3)  # 限速
            except Exception as e:
                failed.append((screen_name, str(e)))
        
        # 时间过滤
        if hours > 0:
            time_filtered = []
            for t in all_tweets:
                dt = parse_twitter_date(t["created_at"])
                if dt and dt >= cutoff:
                    time_filtered.append(t)
            all_tweets = time_filtered
        
        # ── 投资相关性过滤（增强版 v2）──
        if filter_investment:
            try:
                from .filter import calculate_investment_score
                scored_tweets = []
                for t in all_tweets:
                    score, matched_kw = calculate_investment_score(t["text"], "x")
                    if score >= 15.0:  # 推文阈值稍低
                        t["investment_score"] = round(score, 1)
                        t["matched_keywords"] = matched_kw[:5]
                        scored_tweets.append(t)
                all_tweets = scored_tweets
            except ImportError:
                # 降级到旧版简单过滤
                filtered = []
                for t in all_tweets:
                    text_lower = t["text"].lower()
                    if any(kw.lower() in text_lower for kw in INVESTMENT_KEYWORDS):
                        filtered.append(t)
                all_tweets = filtered
        
        # ── 资产 & 主题提取 ──
        try:
            from .asset_extractor import extract_assets, extract_themes
            for t in all_tweets:
                assets = extract_assets(t["text"])
                themes = extract_themes(t["text"])
                t["assets"] = [list(a) for a in assets]  # [[symbol, name], ...]
                t["themes"] = themes
        except ImportError:
            # 如果提取器不可用，留空
            for t in all_tweets:
                t["assets"] = []
                t["themes"] = []
        
        # 按综合质量分排序（热度分 + 投资相关性加权）
        for t in all_tweets:
            inv_score = t.get("investment_score", 10)
            base_score = t.get("score", 0)
            # 投资相关性越高，排名越靠前（最高 +50% 权重）
            t["quality_score"] = round(base_score * (1 + inv_score / 200), 1)
        
        all_tweets.sort(key=lambda x: x.get("quality_score", x.get("score", 0)), reverse=True)
        
        return {
            "tweets": all_tweets,
            "total": len(all_tweets),
            "success_users": success,
            "failed_users": failed,
            "time_window_hours": hours,
            "kol_count": len(influencers),
        }
    
    def health_check(self):
        """健康检查"""
        try:
            result = self.collect(
                influencers={"elonmusk": "马斯克"},
                per_user_count=5,
                filter_investment=False,
                hours=0,  # 不过滤时间
            )
            return {
                "platform": "x_api",
                "auth_token_set": bool(self.auth_token),
                "ct0_set": bool(self.ct0),
                "api_works": result["total"] > 0,
                "test_results": result["total"],
            }
        except Exception as e:
            return {
                "platform": "x_api",
                "auth_token_set": bool(self.auth_token),
                "ct0_set": bool(self.ct0),
                "api_works": False,
                "error": str(e),
            }


if __name__ == "__main__":
    collector = XCollector()
    result = collector.collect(
        influencers={
            "elonmusk": "马斯克",
            "Reuters": "路透社",
            "jimcramer": "克莱默",
        },
        per_user_count=10,
        filter_investment=False,
        hours=0,
    )
    print(f"采集到 {result['total']} 条推文")
    print(f"成功用户: {result['success_users']}")
    print(f"失败用户: {result['failed_users']}")
    for t in result["tweets"][:5]:
        print(f"  [{t['score']}] @{t['user_screen']}: {t['text'][:70]}")
