import requests
from newspaper import Article
import datetime
import os

# 1. 目标网站及其搜索地址 (示例列出三个，你可以按格式继续添加)
SITES = {
    "N1 Info": "https://n1info.rs/?s=opozicija",
    "Nova": "https://nova.rs/?s=opozicija",
    "Danas": "https://www.danas.rs/?s=opozicija"
}

def get_today_news():
    today = datetime.date.today().strftime('%Y-%m-%d')
    report = f"# 塞尔维亚反对派动态每日综述 ({today})\n\n"
    has_news = False

    for name, url in SITES.items():
        print(f"正在抓取 {name}...")
        try:
            # 获取搜索结果页面内容
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, headers=headers, timeout=15)
            
            # 使用 newspaper4k 提取页面内的潜在链接
            # 注意：实际运行中，精准提取当天链接可能需要 BeautifulSoup 微调
            # 这里使用 newspaper 的 source 模式作为基础
            from newspaper import build
            site_paper = build(url, language='sr', memoize_articles=False)
            
            for article in site_paper.articles[:5]: # 每次搜索只取前5篇
                article.download()
                article.parse()
                
                # 检查发布日期是否为今天
                # 有些网站不提供发布日期，脚本会尝试根据正文内容或URL判断
                if article.publish_date and article.publish_date.date() == datetime.date.today():
                    report += f"## 标题: {article.title}\n"
                    report += f"**来源网站**: {name}\n"
                    report += f"**原文链接**: {article.url}\n\n"
                    report += f"### 内容摘要\n{article.text[:800]}...\n\n" # 截取前800字
                    report += "---\n\n"
                    has_news = True
        except Exception as e:
            print(f"抓取 {name} 出错: {e}")

    if not has_news:
        report += "今日未检索到相关新闻。"

    # 保存为 Markdown 文件
    filename = f"reports/news_{today}.md"
    os.makedirs('reports', exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report)

if __name__ == "__main__":
    get_today_news()
