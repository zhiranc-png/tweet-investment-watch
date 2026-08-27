# hybrid/（混合采集试点）

大V信号日报的广域采集层试点：每天 12:15 HKT 用专用小号拉取 5 个试点 KOL 的 X 时间线，结果以 JSON 提交回仓库 `data/hybrid_tweets_YYYYMMDD.json`。分析端（Echo）通过 raw.githubusercontent.com 读取，只对筛出的核心信号帖用浏览器做窄深挖（热评 / Trending / URL 实锤）。

与仓库根目录的「投资舆情每日采集」（旧流程，GraphQL + 多源中文）并行运行、互不干扰。

## 试点成功标准（连续 3 天）
1. 每日成功率 ≥ 90%（最好 5/5 全成）
2. 无 429 限流、无 401/403 风控
3. JSON 字段完整：tweet_id / url / text / created_at / likes / retweets 非空

达标后：扩到 54 人全量，并与旧流程输出做对账，确定最终广域采集主链路。

## 采集方式
v1.1 REST（users/show + user_timeline）：无 GraphQL hash 漂移、每天仅 ~10 个请求。缺点：无 views 阅读量。

## Secrets
- `X_AUTH_TOKEN` / `X_CT0`：专用爬虫小号的 cookie（已配置，不要用主账号）
