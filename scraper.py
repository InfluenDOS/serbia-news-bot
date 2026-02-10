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

# === 2. 10个目标网站配置 ===
SITES_CONFIG = [
    {"name": "N1 Info", "search": "https://n1info.rs/?s=opozicija+danas"},
    {"name": "Nova.rs", "search": "https://nova.rs/?s=opozicija+najnovije"},
    {"name": "Danas", "search": "https://www.danas.rs/?s=opozicija+vesti"},
    {"name": "Balkan Insight", "search": "https://balkaninsight.com/?s=serbia+opposition"},
    {"name": "Slobodna Evropa", "search": "https://www.slobodnaevropa.org/s?k=opozicija"},
    {"name": "B92", "search": "https://www.b92.net/specijal/3/english/search.php?q=opposition"},
    {"name": "BBC Serbian", "search": "https://www.bbc.com/serbian/lat/search?q=opozicija"},
    {"name": "Vreme", "search": "https://vreme.com/?s=opozicija"},
    {"name": "Demostat", "search": "https://demostat.rs/sr/pretraga?q=opozicija"},
    {"name": "Serbian Times", "search": "https://serbiantimes.info/en/?s=opposition"}
]

def get_ai_summary(title, text):
    """
    AI 充当情报官：只摘要今日发生的硬新闻
    """
    if not text or len(text.strip()) < 100:
        return None

    prompt = f"""
    你是一个负责实时情报监控的分析师。你的任务是处理以下新闻，并执行严格过滤：

    【判定规则】：
    1. **事件时效性**：这篇文章描述的是今天（2026年2月10日）发生的具体动作、声明、抗议或冲突吗？
    2. **内容属性**：如果是对过去事情的分析、主观评论、历史回顾，请只回答“SKIP”。
    3. **摘要要求**：如果是今日硬新闻，请用中文写一篇400-800字的深度摘要。

    【摘要重点】：
    - 发生了什么具体动作（时间、地点、人物、行为）？
    - 核心人物说了什么（引用原话）？
    - 现场具体细节（人数、冲突、警方动作等）。

    原文标题：{title}
    原文内容：{text}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=MODEL_ID, contents=prompt)
            return response.text if response.text else None
        except Exception as e:
            if "429" in str(e) or "503" in str(e):
                time.sleep((attempt + 1) * 30)
            else:
                break
    return None

def extract_links(url, today_str_list):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
    links = []
    try:
        res = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            # 过滤掉已知的非新闻板块
            blacklist = ['/opinion/', '/komentari/', '/kolumna/', '/stav/', '/pogledi/']
            if any(word in href for word in blacklist):
                continue
                
            if any(date_str in href for date_str in today_str_list) or ('/vesti/' in href) or ('/news/' in href):
                if href.startswith('/') and 'http' not in href:
                    base = "https://" + url.split('/')[2]
                    href = base + href
                if href not in links and 'http' in href:
                    links.append(href)
    except Exception as e:
        print(f"提取链接出错: {e}")
    return list(set(links))[:3]

def run_scraper():
    today = datetime.date.today()
    today_str_list = [today.strftime('/%Y/%m/%d/'), today.strftime('/%Y-%m-%d/')]
    
    report_path = f"reports/report_{today}.md"
    os.makedirs('reports', exist_ok=True)
    
    final_report = f"# 🇷🇸 塞尔维亚反对派动态每日深度专报\n\n**生成日期**: {today} (仅限当日硬新闻)\n\n---\n"
    found_any = False

    for config in SITES_CONFIG:
        print(f"🔍 扫描站点: {config['name']}")
        links = extract_links(config['search'], today_str_list)
        
        for link in links:
            # 链接级黑名单过滤
            blacklist = ['/opinion/', '/komentari/', '/kolumna/', '/stav/', '/pogledi/']
            if any(word in link for word in blacklist):
                continue

            try:
                article = Article(link, language='sr')
                article.download()
                article.parse()
                
                # 严格日期校验
                if not article.publish_date or article.publish_date.date() != today:
                    continue

                print(f"📝 正在评估并摘要: {article.title}")
                summary = get_ai_summary(article.title, article.text)
                
                # --- 新增调试日志 ---
                if not summary:
                    print(f"❌ AI 未返回内容 (可能是 API 错误)")
                elif "SKIP" in summary.upper():
                    print(f"⏩ AI 判定为非硬新闻，已跳过。")
                else:
                    print(f"✅ AI 摘要成功，字数: {len(summary)}")
                    final_report += f"## 📰 {article.title}\n"
                    final_report += f"**来源**: {config['name']} | [原文链接]({link})\n\n"
                    final_report += f"{summary}\n\n---\n\n"
                    found_any = True
                    time.sleep(20) 
            except Exception as e:
                print(f"⚠️ 处理出错: {e}")

    if not found_any:
        final_report += f"今日 ({today}) 未检索到符合要求的硬新闻动态。"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)
    print(f"✅ 任务完成: {report_path}")

if __name__ == "__main__":
    run_scraper()
