# serbia-news-bot

每日自动抓取塞尔维亚及相关区域媒体，用 **Kimi** 筛选与**在野党 / 反执政阵营**相关的硬新闻，并生成中文专报。

## 监测口径

关注与现执政党（SNS / 武契奇政府为核心的执政同盟）**立场对立**的各党派、联盟、议员与政治行动——不是单一「反对派」品牌，而是所有对执政方构成政治对立面的阵营动态。

## 信源

列表页抓取（比搜索页更稳），当前包括：

| 信源 | 说明 |
|------|------|
| N1 Info / Nova.rs / Danas / Vreme / B92 | 历史核心源 |
| Euronews Srbija / Insajder / Radar | 补充国内源 |
| Slobodna Evropa / BBC Serbian / Balkan Insight / Al Jazeera Balkans / Demostat / Serbian Monitor | 区域与分析源 |

配置见 `serbia_news_bot/sources.py`。

## 流程

1. 拉取各站新闻列表，抽取文章链接  
2. 下载正文，按贝尔格莱德时区过滤发布日（默认今天 + 昨天）  
3. Kimi 判定是否符合在野党口径；符合则写中文事实摘要  
4. 写入 `reports/report_YYYY-MM-DD.md`

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export KIMI_API_KEY=your_key
python main.py
```

常用环境变量：

| 变量 | 含义 |
|------|------|
| `KIMI_API_KEY` | 必填（也可用 `MOONSHOT_API_KEY`；除非 `DRY_RUN=1`） |
| `KIMI_BASE_URL` | 默认 `https://api.moonshot.ai/v1` |
| `KIMI_MODEL` | 默认 `kimi-k2.6` |
| `TARGET_DATE` | `YYYY-MM-DD`，覆盖监测日 |
| `DRY_RUN` | `1` 时不调 Kimi，仅关键词粗筛 |
| `MAX_ARTICLES_PER_SITE` | 每站最多解析篇数，默认 8 |

兼容旧入口：`python scraper.py` 会转发到同一流水线。

## GitHub Actions

`.github/workflows/daily_crawl.yml` 每天约在**贝尔格莱德时间 20:00**运行（UTC 18:00；冬令时会偏到当地 19:00），也可 `workflow_dispatch` 手动触发。仓库需配置 Secret：`KIMI_API_KEY`。

可选邮件（跑完自动发到邮箱）：

| Secret | 说明 |
|--------|------|
| `REPORT_TO_EMAIL` | 收件人，默认 `speechlessgorilla@gmail.com` |
| `SMTP_USER` + `SMTP_PASSWORD` | Gmail 等 SMTP（推荐应用专用密码） |
| 或 `RESEND_API_KEY` | Resend 发信 |
| `REPORT_FROM_EMAIL` | 发件人显示地址（可选） |

## 项目结构

```
main.py
scraper.py                 # 兼容入口
serbia_news_bot/
  config.py                # 日期、限流、开关
  sources.py               # 信源与粗筛词
  fetch.py                 # 列表页链接抽取
  article.py               # 正文与日期
  ai.py                    # Kimi 判定 + 摘要
  report.py                # Markdown 输出
  pipeline.py              # 编排
reports/
```
