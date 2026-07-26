# 📡 AI 情报雷达

零依赖的 AI 信息搜集程序:自动抓取 **AI 羊毛优惠 / 新品发布 / 热点话题 / 技巧灵感**,按热度打分归类,生成每日 Markdown 简报,为 X(Twitter) 创作提供选题素材。

纯 Python 标准库实现,无需安装任何第三方包。

## 🚀 推荐部署:GitHub Actions(免费,无需服务器)

本仓库自带 Actions 配置,推上 GitHub 就完成部署:

1. 在 GitHub 新建一个仓库(Private 也可以)
2. 把本项目推上去:

   ```bash
   git remote add origin https://github.com/你的用户名/ai-radar.git
   git push -u origin main
   ```

3. 打开仓库的 **Actions** 标签页 → 如提示则点击启用 → 选择 "AI Radar Daily" → **Run workflow** 手动跑一次测试

之后每天北京时间早 8 点左右自动运行,当日简报自动提交到 `reports/` 目录,手机打开 GitHub(App 或网页)即可查看。

想要微信/Telegram 推送:仓库 **Settings → Secrets and variables → Actions** 里添加 `SERVERCHAN_KEY`(Server酱,[sct.ftqq.com](https://sct.ftqq.com) 免费申请)或 `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`。

> 注:GitHub 定时任务在高峰期可能延迟几分钟到半小时;仓库连续 60 天无活动会暂停定时(本项目每天自动提交简报,正常不会触发)。

## 💻 备选部署:自己的机器

```bash
python3 ai_radar.py --demo    # 离线自检(无需联网)
python3 ai_radar.py           # 真实抓取,简报输出到 reports/
```

- **Linux 服务器**: `bash setup_linux.sh` — 自动注册 crontab,自动换算北京时间早 8 点
- **Mac**: `bash setup_mac.sh` — 注册 launchd 每日任务,睡眠错过会补跑
- **Windows**: 任务计划程序 → 每天 8:00 运行 `python ai_radar.py`

本地推送配置:目录下建 `.env` 文件,写入 `export SERVERCHAN_KEY="SCTxxx"` 等环境变量。

## ⚙️ 自定义 (config.json)

- `rss_sources`: 增删 RSS 源(推荐补充:你关注的博主、RSSHub 生成的机器之心/量子位等国内源)
- `hn_queries`: Hacker News 搜索词,羊毛类建议保留 "free credits"
- `reddit_subs`: 监控的 Reddit 板块(如 OpenAI、singularity)
- `hours`: 扫描窗口(默认 26 小时);`min_score`: 收录门槛,嫌噪音多调到 2-3
- 四类分类关键词在 `ai_radar.py` 的 `DEFAULT_CONFIG["categories"]`,中英文均可直接加词

## 🔍 工作原理

抓取(RSS/Atom + Hacker News 搜索 API + Reddit JSON)→ 时间窗口过滤 → 四类关键词打分归类(羊毛类权重 ×2)→ 去重(`seen.json` 记住 30 天内已见链接)→ 生成简报(含按热度排序的"创作候选 Top 5")→ 可选推送。单个源抓取失败不影响其它源。

## ❓ 常见问题

- **Reddit 429/403**: 无认证请求被限流,稍后再跑,或从 `config.json` 删掉 `reddit_subs`(GitHub Actions 的 IP 偶尔也会被 Reddit 限流,属正常)
- **国内网络部分海外源失败**: 换代理环境运行,或改用 RSSHub 镜像源;GitHub Actions 跑则无此问题
- **想重新收录已见过的内容**: 删掉 `seen.json`

## License

MIT
