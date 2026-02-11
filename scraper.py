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

# === 1. 配置 AI 引擎 ===
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL_ID = 'models/gemini-flash-latest' 

# === 2. 目标网站实时新闻流 (Vesti 频道) ===
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
    AI 判定：仅限 2月10日的反对派政治/经济/文化硬新闻
    """
    if not text or len(text.strip()) < 150:
        return None

    # 调试期硬编码目标日期
    target_date = "2026年2月10日"

    prompt = f"""
    你是一个资深的巴尔干政治情报专家。请阅读以下文章并执行任务：

    【判定任务】：
    1. 该文章内容是否主要涉及：塞尔维亚反对派(Serbian opposition/opozicija)在政治、经济或文化领域的动态？
    2. 该事件是否发生在【{target_date}】当天？
    3. 如果文章属于：社会刑事案、纯分析评论（无今日新动态）、国际新闻、或者日期不符，请【仅回复】：SKIP

    【摘要任务】(仅在判定为“是”时执行)：
    - 撰写 300-800 字的详细中文深度摘要。
    - 重点：发生的具体客观事实、重要人物的发言原话、现场细节。
    - 严禁空洞，必须包含硬核情报。
    - 结尾换行附上原文链接：{link}

    标题：{title}
    正文：{text}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=MODEL_ID, contents=prompt)
            res_text = response.text.strip()
            if "SKIP" in res_text.upper() or len(res_text) < 15:
                return None
            return res_text
        except Exception as e:
            if "429" in str(e) or "503" in str(e):
                time.sleep((attempt + 1) * 30)
            else:
                break
    return None

def extract_links(url, target_date_str):
    """从新闻流中提取链接，允许包含目标日期的路径"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
    links = []
    try:
        res = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            # 如果链接包含目标日期字符串（如 /2026/02/10/）或通用的 vesti/news 路径
            if (target_date_str in href) or ('/vesti/' in href) or ('/news/' in href):
                if href.startswith('/') and 'http' not in href:
                    base = "https://" + url.split('/')[2]
                    href = base + href
                if href not in links and 'http' in href:
                    links.append(href)
    except:
        pass
    # 调试期每个站点多看几个链接（前8个），确保能翻到昨天的文章
    return list(set(links))[:8]

def run_scraper():
    # --- 调试设置：锁定为 2月10日 ---
    test_day = datetime.date(2026, 2, 10)
    target_date_str = test_day.strftime('/%Y/%m/%d/')
    
    report_path = f"reports/report_{test_day}.md"
    os.makedirs('reports', exist_ok=True)
    
    final_report = f"# 🇷🇸 塞尔维亚情报测试报告 (回顾: {test_day})\n\n**筛选逻辑**: 全量 Vesti 抓取 + AI 语义过滤\n\n---\n"
    found_any = False

    for config in SITES_CONFIG:
        print(f"📡 扫描站点新闻流: {config['name']}")
        links = extract_links(config['url'], target_date_str)
        
        for link in links:
            try:
                # 过滤掉已知的非新闻板块
                if any(x in link for x in ['/opinion/', '/komentari/', '/stav/']):
                    continue

                article = Article(link, language='sr')
                article.download()
                article.parse()
                
                # 校验日期：必须是 2月10日
                if article.publish_date and article.publish_date.date() != test_day:
                    continue

                print(f"🧐 AI 评估中: {article.title[:45]}...")
                summary = get_ai_decision_and_summary(article.title, article.text, link)
                
                if summary:
                    print(f"✅ 捕获 2月10日 硬新闻!")
                    final_report += f"## 📰 {article.title}\n\n{summary}\n\n---\n\n"
                    found_any = True
                    time.sleep(30) # 调试期稳一点，给 API 留足空间
            except:
                continue

    if not found_any:
        final_report += f"在昨天的搜索流中未发现符合要求的反对派动态。"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)
    print(f"🚀 测试完成: {report_path}")

if __name__ == "__main__":
    run_scraper()
