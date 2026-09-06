# -*- coding: utf-8 -*-
"""X (Twitter) 采集客户端 —— GraphQL 主路径（移植自仓库内已验证可用的旧采集器）

主路径：GraphQL UserByScreenName + UserTweets
  - queryId 从 x.com 主页 main.js 动态提取，天然免疫 hash 漂移
  - 返回 views（阅读量）
备用：v1.1 REST（2026-08-26 实测对 web session 返回 403，仅保留代码备查）

认证：专用爬虫小号的 auth_token + ct0。⚠️ 不要用主账号。
"""
import json
import re

import requests

BEARER = ("AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
          "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

FEATURES = {
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "view_counts_everywhere_api_enabled": True,
}

FALLBACK_USER_QID = "G3KGOASz96M-Qu0nwmGXNg"
# UserTweets 硬编码兜底：main.js 动态提取失败/解析不出时使用（双保险）。
# TODO(2026-09-06): 暂为占位空值；首轮实跑成功后从日志 [queryId:*] OK 行的 UserTweets= 值回填。
FALLBACK_TWEETS_QID = ""


class RateLimited(Exception):
    """429 限流"""


class AuthRejected(Exception):
    """401/403：cookie 过期或账号被风控"""


def _raise_for(r: requests.Response, ctx: str):
    if r.status_code == 429:
        raise RateLimited(f"429 限流 @ {ctx}")
    if r.status_code in (401, 403):
        raise AuthRejected(f"{r.status_code} 认证被拒 @ {ctx}：cookie 过期或账号被风控")


def build_session(auth_token: str, ct0: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {BEARER}",
        "x-csrf-token": ct0,
        "User-Agent": UA,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
    })
    s.cookies.set("auth_token", auth_token, domain=".x.com")
    s.cookies.set("ct0", ct0, domain=".x.com")
    return s


class XGraphQLClient:
    def __init__(self, session: requests.Session):
        self.session = session
        self.query_ids = {}
        self._user_cache = {}
        # 上次 queryId 提取失败的异常缓存：失败一次后，后续账号直接快速抛出，不再逐个重复请求
        self._query_ids_failed = None

    _MAIN_JS_RE = re.compile(
        r'https://abs\.twimg\.com/responsive-web/client-web(?:-legacy)?/main\.[a-f0-9]+\.js')

    def fetch_query_ids(self):
        """从 x.com 主页 main.js 提取最新 queryId（免疫 hash 漂移）

        2026-09-06 修复：X 约自 9/5 起对不带 cookie 的匿名 GET /home 不再返回
        含 main.*.js 的页面（疑似重定向登录页），导致全部 KOL 采集失败。
        修复：优先用已认证会话（auth_token+ct0）抓 /home，匿名会话降级兜底；
        全部失败时输出可区分诊断（重定向登录页=cookie 失效；200 无 main.js=前端变更）。
        失败会缓存在 _query_ids_failed，同一 client 后续调用直接快速抛出（2026-09-06 故障教训：
        94 个账号逐个完整重试白烧 17 分钟）。
        """
        if self._query_ids_failed is not None:
            raise self._query_ids_failed
        candidates = [
            ("auth-home", self.session, "https://x.com/home"),
            ("anon-home", None, "https://x.com/home"),
            ("auth-root", self.session, "https://x.com/"),
        ]
        for tag, sess, url in candidates:
            s = sess if sess is not None else requests.Session()
            s.headers.setdefault("User-Agent", UA)
            try:
                resp = s.get(url, timeout=20)
            except Exception as e:
                print(f"[queryId:{tag}] GET {url} 异常: {type(e).__name__}: {str(e)[:120]}")
                continue
            js_urls = self._MAIN_JS_RE.findall(resp.text) or \
                re.findall(r'src="([^"]*main\.[a-f0-9]+\.js)"', resp.text)
            if js_urls:
                main_url = js_urls[0]
                if not main_url.startswith("http"):
                    main_url = "https://abs.twimg.com" + main_url
                js_text = s.get(main_url, timeout=30).text
                qids = {}
                for m in re.finditer(r'queryId\s*:\s*"([^"]+)"[^}]*?operationName\s*:\s*"([^"]+)"', js_text):
                    qids[m.group(2)] = m.group(1)
                for m in re.finditer(r'operationName\s*:\s*"([^"]+)"[^}]*?queryId\s*:\s*"([^"]+)"', js_text):
                    qids[m.group(1)] = m.group(2)
                if qids:
                    self.query_ids = qids
                    self._query_ids_failed = None
                    print(f"[queryId:{tag}] OK：解析出 {len(qids)} 个操作，UserTweets={qids.get('UserTweets', 'N/A')}", flush=True)
                    return qids
                print(f"[queryId:{tag}] main.js 已取到但未解析出 queryId")
                continue
            hint = ""
            if resp.status_code in (302, 303) or "/login" in str(resp.url):
                hint = "被重定向到登录页 → cookie/会话已失效（需换号或刷新 cookie）"
            elif resp.status_code == 200:
                hint = "200 但页面无 main.js → X 前端结构可能变更"
            print(f"[queryId:{tag}] {url} -> HTTP {resp.status_code} final={resp.url} len={len(resp.text)} {hint}")
        self._query_ids_failed = Exception(
            "无法从 x.com 提取 main.js 地址（auth/anon 各路径均失败，见上方 [queryId:*] 诊断行）")
        raise self._query_ids_failed

    def _gql_get(self, qid: str, op: str, variables: dict, ctx: str):
        url = f"https://x.com/i/api/graphql/{qid}/{op}"
        r = self.session.get(url, params={
            "variables": json.dumps(variables),
            "features": json.dumps(FEATURES),
        }, timeout=20)
        _raise_for(r, ctx)
        data = r.json()
        if "errors" in data and data["errors"]:
            raise Exception(f"{op} GraphQL 错误: {data['errors'][0].get('message', '')[:150]}")
        return data

    def get_user_id(self, screen_name: str):
        if screen_name in self._user_cache:
            return self._user_cache[screen_name]
        if not self.query_ids:
            self.fetch_query_ids()
        qid = self.query_ids.get("UserByScreenName", FALLBACK_USER_QID)
        vars_ = {"screen_name": screen_name, "withSafetyModeUserFields": True}
        try:
            data = self._gql_get(qid, "UserByScreenName", vars_, f"UserByScreenName {screen_name}")
        except Exception:
            # 备用 queryId 再试一次
            data = self._gql_get(FALLBACK_USER_QID, "UserByScreenName", vars_,
                                 f"UserByScreenName {screen_name} (fallback)")
        uid = data["data"]["user"]["result"]["rest_id"]
        self._user_cache[screen_name] = uid
        return uid

    def fetch_timeline(self, screen_name: str, count: int = 20):
        """拉取用户时间线。返回 (规范化推文列表, 显示名)。"""
        if not self.query_ids:
            self.fetch_query_ids()
        user_id = self.get_user_id(screen_name)
        qid = self.query_ids.get("UserTweets", "")
        if not qid and FALLBACK_TWEETS_QID:
            qid = FALLBACK_TWEETS_QID
            print(f"UserTweets 动态 queryId 缺失，使用硬编码兜底 {qid}", flush=True)
        if not qid:
            raise Exception("未找到 UserTweets queryId（main.js 结构可能已变；可在 x_client.py 回填 FALLBACK_TWEETS_QID 兜底）")
        vars_ = {
            "userId": user_id,
            "count": count,
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": False,
            "withVoice": False,
            "withV2Timeline": True,
        }
        try:
            data = self._gql_get(qid, "UserTweets", vars_, f"UserTweets {screen_name}")
        except Exception:
            # 双保险：动态 queryId 请求失败时，硬编码兜底再试一次（与 get_user_id 同模式）
            if FALLBACK_TWEETS_QID and qid != FALLBACK_TWEETS_QID:
                print("UserTweets 动态 queryId 请求失败，使用硬编码兜底重试", flush=True)
                data = self._gql_get(FALLBACK_TWEETS_QID, "UserTweets", vars_,
                                     f"UserTweets {screen_name} (fallback)")
            else:
                raise

        tweets, display_name = [], screen_name
        user_result = data["data"]["user"]["result"]
        if not user_result.get("timeline"):
            raise Exception(f"无 timeline（疑似封禁/保护/注销）@ {screen_name}")
        timeline = user_result["timeline"]["timeline"]
        for inst in timeline.get("instructions", []):
            if inst.get("type") != "TimelineAddEntries":
                continue
            for entry in inst.get("entries", []):
                if not entry.get("entryId", "").startswith("tweet-"):
                    continue
                content = entry.get("content", {})
                item = content.get("itemContent", {})
                tr = item.get("tweet_results", item.get("tweetResult", {}))
                result = tr.get("result", {}) if isinstance(tr, dict) else {}
                legacy = result.get("legacy", {})
                if not legacy:
                    continue
                user_legacy = (result.get("core", {}).get("user_results", {})
                               .get("result", {}).get("legacy", {}))
                views = 0
                vd = result.get("views", {})
                if isinstance(vd, dict):
                    try:
                        views = int(vd.get("count", 0) or 0)
                    except (ValueError, TypeError):
                        views = 0
                screen = user_legacy.get("screen_name", screen_name)
                display_name = user_legacy.get("name", screen_name)
                tid = legacy.get("id_str", "")
                tweets.append({
                    "tweet_id": tid,
                    "url": f"https://x.com/{screen}/status/{tid}",
                    "text": legacy.get("full_text", ""),
                    "created_at": legacy.get("created_at", ""),
                    "likes": legacy.get("favorite_count", 0),
                    "retweets": legacy.get("retweet_count", 0),
                    "replies": legacy.get("reply_count", 0),
                    "views": views,
                    "is_retweet": "retweeted_status_result" in legacy,
                    "source": "graphql_UserTweets",
                })
        return tweets, display_name
