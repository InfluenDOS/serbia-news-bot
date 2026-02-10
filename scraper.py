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
# 使用稳定的 1.5-flash
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
    带深度重试和日志的情报分析函数
    """
    if not text or len(text.strip()) < 100:
        return None

    prompt = f"""
    你是一个专业的巴尔干时政情报分析师。请针对以下文章，提取【今日（2026年2月10日）发生的客观动作】。

    【提取重点】：
    1. 发生了什么具体事件？（时间、地点、人物、动作）
    2. 核心人物的原话是什么？（请尽量引用原话）
    3. 如果是反对派动作、学生运动或重大的官方表态，请写一篇 400-800 字的深度摘要。
    4. 如果只是普通社会案件或无关旧闻，请简短总结（100字左右）。

    原文标题：{title}
    原文内容：{text}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=MODEL_ID, contents=prompt)
            return response.text if response.text else "AI 生成内容为空"
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "503" in err_msg:
                wait_time = (attempt + 1) * 60 
                print(f"⚠️ API 配额限制，冷却 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                print(f"❌ AI 模块遇到未知错误: {err_msg}")
                break
    return None

def extract_links(url, today_str_list):
    """提取链接并过滤黑名单"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
    links = []
    try:
        res = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            # 板块黑名单过滤
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
    return list(set(links))[:2] # 限制数量，优先保证 API 成功率

def run_scraper():
    today = datetime.date.today()
    # 匹配多种日期格式
    today_str_list = [today.strftime('/%Y/%m/%d/'), today.strftime('/%Y-%m-%d/'), today.strftime('/%d-%m-%Y/')]
    
    report_path = f"reports/report_{today}.md"
    os.makedirs('reports', exist_ok=True)
    
    final_report = f"# 🇷🇸 塞尔维亚反对派动态每日深度专报\n\n**生成日期**: {today} (严格当日动态)\n\n---\n"
    found_any = False

    for config in SITES_CONFIG:
        print(f"🔍 正在扫描站点: {config['name']}")
        links = extract_links(config['search'], today_str_list)
        
        for link in links:
            try:
                article = Article(link, language='sr')
                article.download()
                article.parse()
                
                # 严格校验发布日期是否为今天
                if not article.publish_date or article.publish_date.date() != today:
                    continue

                print(f"📝 正在总结: {article.title}")
                summary = get_ai_summary(article.title, article.text)
                
                if summary:
                    print(f"✅ 摘要成功 (字数: {len(summary)})")
                    final_report += f"## 📰 {article.title}\n"
                    final_report += f"**来源**: {config['name']} | [原文链接]({link})\n\n"
                    final_report += f"{summary}\n\n---\n\n"
                    found_any = True
                    # 强制休眠 45 秒以保护 API 免费配额
                    print("💤 强制冷却 45 秒...")
                    time.sleep(45)
                else:
                    print(f"⚠️ {article.title} 未能返回有效摘要")

            except Exception as e:
                print(f"⚠️ 跳过文章 {link}: {str(e)}")
                continue

    if not found_any:
        final_report += f"今日 ({today}) 在 10 个指定源中未检索到符合条件的当日硬新闻。"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)
    print(f"🚀 任务全线完成: {report_path}")

if __name__ == "__main__":
    run_scraper()
