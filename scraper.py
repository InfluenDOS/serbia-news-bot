import os
import time
import datetime
import requests
from bs4 import BeautifulSoup
from newspaper import Article
try:
    import google.genai as genai
except ImportError:
    from google import genai

# === 1. 配置 AI 引擎 (当前时间: 2026年2月11日) ===
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL_ID = 'models/gemini-flash-latest' 

# === 2. 目标网站实时新闻频道 (直接爬取 Vesti 列表) ===
SITES_CONFIG = [
    {"name": "N1 Info", "url": "https://n1info.rs/vesti/"},
    {"name": "Nova.rs", "url": "https://nova.rs/vesti/"},
    {"name": "Danas", "url": "https://www.danas.rs/vesti/"},
    {"name": "Balkan Insight", "url": "https://balkaninsight.com/news/"},
    {"name": "Slobodna Evropa", "url": "https://www.slobodnaevropa.org/z/500"},
    {"name": "B92 English", "url": "https://www.b92.net/specijal/english/12/news"},
    {"name": "BBC Serbian", "url": "https://www.bbc.com/serbian/lat"},
    {"name": "Vreme", "url": "https://vreme.com/category/vesti/"},
    {"name": "Demostat", "url": "https://demostat.rs/sr/vesti/analize/0"},
    {"name": "Serbian Times (EN)", "url": "https://serbiantimes.info/en/category/serbia/"}
]

def get_ai_decision_and_summary(title, text, link):
    """
    让 AI 充当双重角色：
    1. 判断是否与“塞尔维亚反对派”及“今日事件”相关
    2. 如果相关，生成 300-800 字深度摘要
    """
    if not text or len(text.strip()) < 150:
        return None

    today_str = datetime.date.today().strftime('%Y-%m-%d')

    prompt = f"""
    你是一个资深的巴尔干政治情报专家。请阅读以下文章并执行任务：

    【判定任务】：
    - 该文章内容是否主要涉及：塞尔维亚反对派(Serbian opposition/opozicija)的政治、经济或文化动态？
    - 该事件是否发生在今天（{today_str}）？
    - 如果以上两个回答中有一个为“否”，请仅回复：SKIP

    【总结任务】(仅在判定为“是”时执行)：
    - 撰写 300-800 字的详细中文摘要。
    - 重点：谁参与了、具体动作、涉及的经济/文化影响、以及政府方的反应。
    - 严禁空洞的描述，必须包含事实细节。
    - 结尾必须换行并附上原文链接：{link}

    文章标题：{title}
    文章正文：{text}
    """
    
    try:
        response = client.models.generate_content(model=MODEL_ID, contents=prompt)
        res_text = response.text.strip()
        if res_text.upper() == "SKIP" or len(res_text) < 10:
            return None
        return res_text
    except Exception as e:
        print(f"⚠️ AI 处理失败: {str(e)[:50]}")
        return None

def extract_all_links(url):
    """抓取页面上所有看起来像文章的链接"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
    links = []
    try:
        res = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        # 寻找今天可能的新闻路径
        today_path = datetime.date.today().strftime('%Y/%m/%d')
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            # 基本过滤：排除主页、分类页，且包含今日日期或 vesti/news 路径
            if (today_path in href) or ('/vesti/' in href) or ('/news/' in href):
                if href.startswith('/') and 'http' not in href:
                    base = "https://" + url.split('/')[2]
                    href = base + href
                if href not in links and 'http' in href:
                    links.append(href)
    except:
        pass
    return list(set(links))[:5] # 每个站点扫前5条最新的，保证时效性

def run_scraper():
    today = datetime.date.today()
    report_path = f"reports/report_{today}.md"
    os.makedirs('reports', exist_ok=True)
    
    final_report = f"# 🇷🇸 塞尔维亚动态每日深度情报 (AI 智能筛选版)\n\n**监测日期**: {today}\n**逻辑**: 全量抓取新闻流 -> AI 判定反对派相关度 -> 深度摘要\n\n---\n"
    found_any = False

    for config in SITES_CONFIG:
        print(f"📡 正在监控站点新闻流: {config['name']}")
        links = extract_all_links(config['url'])
        
        for link in links:
            try:
                article = Article(link, language='sr')
                article.download()
                article.parse()
                
                # 即使没有自动解析出日期，我们也交给 AI 判断
                print(f"🧐 AI 评估中: {article.title[:40]}...")
                summary = get_ai_summary_and_decision(article.title, article.text, link)
                
                if summary:
                    print(f"✅ 捕获重要情报!")
                    final_report += f"## 📰 {article.title}\n\n{summary}\n\n---\n\n"
                    found_any = True
                    # 频率控制：每篇 10 秒，保证 15RPM 限额
                    time.sleep(10)
            except:
                continue

    if not found_any:
        final_report += f"今日 ({today}) 暂未监测到与反对派相关的硬新闻动作。"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)
    print(f"🚀 任务全线完成: {report_path}")

if __name__ == "__main__":
    run_scraper()
