import os
import time
import datetime
import requests
from bs4 import BeautifulSoup
import newspaper # 正确导入整个模块
from newspaper import Article
import google.generativeai as genai

# === 1. 配置 AI 引擎 ===
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
# 使用你调试出的最新模型
MODEL_ID = 'models/gemini-2.5-flash'
ai_model = genai.GenerativeModel(MODEL_ID)

# === 2. 目标网站配置 (严格限定你的 10 个源) ===
SITES_CONFIG = [
    {"name": "N1 Info", "search": "https://n1info.rs/?s=opozicija"},
    {"name": "Nova.rs", "search": "https://nova.rs/?s=opozicija"},
    {"name": "Danas", "search": "https://www.danas.rs/?s=opozicija"},
    {"name": "Balkan Insight", "search": "https://balkaninsight.com/?s=serbia+opposition"},
    {"name": "Slobodna Evropa", "search": "https://www.slobodnaevropa.org/s?k=opozicija"},
    {"name": "B92", "search": "https://www.b92.net/specijal/3/english/search.php?q=opposition"},
    {"name": "Vreme", "search": "https://vreme.com/?s=opozicija"},
    {"name": "Demostat", "search": "https://demostat.rs/sr/pretraga?q=opozicija"},
    {"name": "Serbian Times", "search": "https://serbiantimes.info/en/?s=opposition"},
    {"name": "BBC Serbian", "search": "https://www.bbc.com/serbian/lat/search?q=opozicija"}
]

def get_ai_summary(title, text):
    """调用 Gemini 生成 400-800 字深度摘要"""
    if not text or len(text.strip()) < 100:
        return None

    prompt = f"""
    你是一个资深的巴尔干半岛政治分析师。
    请根据以下原文，写一篇关于“塞尔维亚反对派”今日动态的深度摘要。

    【文章标题】：{title}
    【原文内容】：{text}

    【要求】：
    1. 必须使用中文，字数控制在 400-800 字。
    2. 重点：反对派的具体行动、具体人物、政治诉求、对政府的具体批评。
    3. 细节要详实，不要泛泛而谈。
    4. 剔除一切无关的网页导航或广告信息。
    """
    try:
        response = ai_model.generate_content(prompt)
        return response.text if response.text else None
    except Exception as e:
        print(f"AI 摘要失败: {e}")
        return None

def extract_links(url):
    """手动提取搜索结果中的文章链接"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    links = []
    try:
        res = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 针对新闻站点的链接过滤逻辑
        for a in soup.find_all('a', href=True):
            href = a['href']
            # 过滤出包含 2026/02 或具有新闻特征的路径
            if '/2026/02/' in href or '/vesti/' in href or '/news/' in href:
                if href.startswith('/') and 'http' not in href:
                    # 处理相对路径
                    base = url.split('.com')[0] + '.com' if '.com' in url else url.split('.rs')[0] + '.rs'
                    href = base + href
                if href not in links and 'http' in href:
                    links.append(href)
    except Exception as e:
        print(f"提取链接出错: {e}")
    return list(set(links))[:3] # 每个站取前3个最有潜力的

def run_scraper():
    today = datetime.date.today()
    report_path = f"reports/report_{today}.md"
    os.makedirs('reports', exist_ok=True)
    
    final_report = f"# 🇷🇸 塞尔维亚反对派动态每日深度专报\n\n**生成日期**: {today}\n\n---\n"
    found_any = False

    for config in SITES_CONFIG:
        print(f"🔍 正在扫描 {config['name']}...")
        links = extract_links(config['search'])
        
        for link in links:
            try:
                article = Article(link, language='sr')
                article.download()
                article.parse()
                
                # 时间校验：如果是最近 2 天内的（处理时差和更新延迟）
                pub_date = article.publish_date
                if pub_date and pub_date.date() < today - datetime.timedelta(days=2):
                    continue

                print(f"📝 正在总结: {article.title}")
                summary = get_ai_summary(article.title, article.text)
                
                if summary:
                    final_report += f"## 📰 {article.title}\n"
                    final_report += f"**来源**: {config['name']} | [原文链接]({link})\n\n"
                    final_report += f"{summary}\n\n---\n\n"
                    found_any = True
                    time.sleep(12) # 严格控制频率
            except Exception as e:
                print(f"跳过文章 {link}: {e}")
                continue

    if not found_any:
        final_report += "今日在 10 个指定源中未检索到符合条件的实时新闻（可能今日无更新或搜索结构变化）。"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)
    print(f"✅ 专报已生成: {report_path}")

if __name__ == "__main__":
    run_scraper()
