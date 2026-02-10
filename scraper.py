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
    调整为：更温柔的总结者，不再动不动就 SKIP
    """
    if not text or len(text.strip()) < 100:
        return None

    # 放宽口径：要求总结，而不是判定
    prompt = f"""
    你是一个专业的巴尔干时政情报分析师。请针对以下文章，重点提取【今日发生的客观动作】。

    【提取重点】：
    1. 发生了什么具体事件？（时间、地点、人物）
    2. 核心人物的原话是什么？
    3. 如果该文章纯属社会杂闻或国际旧闻，请简短总结（100字以内）。
    4. 如果是反对派动作、学生运动或重大的官方表态，请深度总结（400-800字）。

    原文标题：{title}
    原文内容：{text}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=MODEL_ID, contents=prompt)
            return response.text if response.text else "AI 摘要内容为空"
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "503" in err_msg:
                # 遇到限流，我们需要更长时间的冷却
                wait_time = (attempt + 1) * 60 
                print(f"⚠️ API 繁忙 ({err_msg[:20]}...)，进入强制冷却 {wait_time} 秒...")
                time.sleep(wait_time)
            else:
                print(f"❌ API 严重错误: {err_msg}")
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

                print(f"📝 正在总结: {article.title}")
                summary = get_ai_summary(article.title, article.text)
                
                if summary:
                    print(f"✅ 摘要完成 (来源: {config['name']})")
                    final_report += f"## 📰 {article.title}\n"
                    final_report += f"**来源**: {config['name']} | [原文链接]({link})\n\n"
                    final_report += f"{summary}\n\n---\n\n"
                    found_any = True
                    # 【核心修改】强制休眠 45 秒，避开 Google 的监控
                    print("💤 等待 45 秒以保护 API 配额...")
                    time.sleep(45) 
                else:
                    print(f"⚠️ {article.title} 未能生成摘要")

    if not found_any:
        final_report += f"今日 ({today}) 未检索到符合要求的硬新闻动态。"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)
    print(f"✅ 任务完成: {report_path}")

if __name__ == "__main__":
    run_scraper()
