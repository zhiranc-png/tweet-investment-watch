# 📊 推特投资舆情监控系统 — 云端版

基于 X/Twitter auth_token 的轻量爬虫，部署在 GitHub Actions 上全自动运行，每天中午12点自动采集大V推文和热点评论，生成投资舆情简报。

## ✨ 功能特点

- 🔄 **全自动运行**：GitHub Actions 定时触发，无需服务器
- 📱 **45+ 位投资大V**：覆盖美股、A股/港股、宏观三大领域
- 🔍 **关键词搜索**：46 个投资相关关键词全网搜索
- 💬 **评论抓取**：自动抓取高互动推文的热门评论
- 📊 **智能分析**：标的识别、主题分类、情感倾向判断
- 🎯 **投资信号**：配合 Agent 生成买入/卖出/观望建议

## 🚀 快速部署（5分钟）

### 第一步：获取 X 的 auth_token 和 ct0

1. 用 Chrome 或 Firefox 打开 https://x.com 并登录
2. 按 `F12` 打开开发者工具
3. 切换到 **Application**（应用）标签
4. 左侧找到 **Cookies** → `https://x.com`
5. 找到以下两个 cookie 的值：
   - `auth_token` — 一长串字母数字（类似 `abc123def456...`）
   - `ct0` — CSRF token（类似 `abc123def456...`）
6. 把这两个值复制保存好

> ⚠️ **注意**：auth_token 相当于你的账号密码，不要分享给别人，不要提交到公开仓库。

### 第二步：Fork 这个仓库

1. 点击右上角的 **Fork** 按钮
2. Fork 到你自己的 GitHub 账号

### 第三步：配置 Secrets

1. 进入你 Fork 的仓库
2. 点击 **Settings** → **Secrets and variables** → **Actions**
3. 点击 **New repository secret**，添加以下两个 secret：
   - Name: `AUTH_TOKEN`，Value: 你刚才复制的 auth_token 值
   - Name: `CT0`，Value: 你刚才复制的 ct0 值

### 第四步：手动测试一次

1. 点击 **Actions** 标签
2. 左侧选择 "推特投资舆情每日采集"
3. 点击 **Run workflow** → 选择 main 分支 → 点击 Run
4. 等几分钟，看是否成功

如果成功了，以后每天中午12点会自动运行。

## 📋 每日数据在哪里？

每次运行后，数据保存在 Actions 的 Artifacts 中：

1. 进入 **Actions** 标签
2. 点击最近一次成功的 workflow run
3. 在页面底部 **Artifacts** 区域可以下载：
   - `brief-data` — 简报 JSON（用于投资信号分析）
   - `daily-report` — 基础 Markdown 报告
   - `tweets-raw` — 原始推文数据

## 🔧 自定义配置

### 修改 KOL 名单

编辑 `src/config/kol_list.py`，在对应分类的列表里添加或删除账号。

### 修改搜索关键词

编辑 `src/config/keywords.py`，添加或删除搜索词。

### 修改运行时间

编辑 `.github/workflows/daily-collect.yml`，修改 cron 表达式：

```yaml
schedule:
  - cron: '0 4 * * *'  # UTC 时间，北京时间 = UTC + 8
```

常用时间：
- 北京时间 8:00 → `0 0 * * *`
- 北京时间 12:00 → `0 4 * * *`
- 北京时间 18:00 → `0 10 * * *`
- 北京时间 22:00 → `0 14 * * *`

## 📁 项目结构

```
tweet-watch-cloud/
├── main.py                          # 主入口
├── requirements.txt                 # 依赖
├── README.md                        # 说明文档
├── .github/
│   └── workflows/
│       └── daily-collect.yml        # GitHub Actions 配置
└── src/
    ├── collectors/
    │   ├── x_api_collector.py       # X API 爬虫（核心）
    │   ├── asset_extractor.py       # 标的与主题提取
    │   └── models.py                # 数据模型
    ├── analysis/
    │   └── signal_aggregator.py     # 信号聚合与统计
    ├── config/
    │   ├── kol_list.py              # KOL 名单
    │   └── keywords.py              # 搜索关键词
    └── output/
        └── report_generator.py      # 报告生成
```

## ⚠️ 注意事项

1. **账号安全**：auth_token 是敏感信息，只放在 GitHub Secrets 里，不要提交到代码
2. **频率控制**：代码已经做了限速（每次请求间隔 0.5-1 秒），不要随意调快
3. **Token 过期**：X 的 auth_token 可能会过期，如果爬虫失败了，重新获取一次即可
4. **免费额度**：GitHub Actions 免费版每月 2000 分钟，每天跑一次完全够用
5. **投资建议**：本系统仅供参考，不构成任何投资建议

## 🔄 投资信号分析流程

1. GitHub Actions 每天自动采集 → 生成 brief.json
2. 将 brief.json 上传到飞书或发给 Agent
3. Agent 分析 brief.json → 生成投资信号和完整报告
4. 报告输出到飞书文档

## 🆘 常见问题

**Q: 运行失败了怎么办？**
A: 进入 Actions → 点击失败的 run → 查看日志，根据错误信息排查。最常见的是 auth_token 过期，重新获取即可。

**Q: 能抓到多少条推文？**
A: 默认配置下，每次大约 100-150 条推文 + 10 条高互动推文的评论。

**Q: 会被 X 封号吗？**
A: 正常使用（一天一次、限速合理）不会封。但不建议用你的主账号，可以注册一个小号专门用来爬数据。

**Q: 怎么加更多 KOL？**
A: 编辑 `src/config/kol_list.py`，添加账号名即可。

## 📨 飞书日报推送

`feishu_notify.py` 会在每天两次自动运行后，把当日精简版日报推送到飞书。

### 推送内容（精简版）

- **7 大资产速览**：美债/黄金/原油/A股/科技/加密/美元，含实时价格和涨跌幅
- **🔥 价格异动**：与上次快照对比，超过 0.5% 的价格变化
- **🆕 新晋热门主题**：新进入 Top 5 的主题
- **🔄 情绪转向**：同一主题多空方向发生变化
- **🏷️ 热门主题 Top 5**：按强度排序
- **📰 重要资讯**：实时财经快讯 Top 3
- **📖 查看完整报告按钮**：一键跳转到完整版飞书文档

### 配置方法

1. 在飞书群里添加「自定义机器人」（带签名校验的卡片机器人）
2. 复制机器人的 webhook URL
3. 在 GitHub 仓库 **Settings → Secrets and variables → Actions** 里添加：
   - Name: `FEISHU_WEBHOOK`
   - Value: 你的 webhook URL
4. 下次定时任务触发时就会自动推送

### 推送时间

- **午间版**：北京时间 12:00（UTC 04:00）触发，覆盖 0-12 点行情
- **晚间版**：北京时间 24:00（UTC 16:00）触发，覆盖全天总结

### 手动测试

```bash
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
python feishu_notify.py
```
