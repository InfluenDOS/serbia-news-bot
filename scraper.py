import os
import time
import datetime
import requests
from bs4 import BeautifulSoup
from newspaper import Article

# 修改这里：使用更直接的导入路径
try:
    import google.genai as genai
except ImportError:
    # 兼容某些特定环境下的导入路径
    from google import genai

# === 1. 配置新版 AI 引擎 ===
# 2026年推荐使用新的 Client 模式
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL_ID = 'gemini-2.0-flash' # 2.0/2.5 flash 在新 SDK 中不需要 models/ 前缀

# === 2. 目标网站配置 ===
SITES_CONFIG = [
    {"name": "N1 Info", "search": "https://n1info.rs/?s=opozicija"},
    {"name": "Nova.rs", "search": "https://nova.rs/?s=opozicija"},
    {"name": "Danas", "search": "https://www.danas.rs/?s=opozicija"},
    {"name": "Balkan Insight", "search": "https://balkaninsight.com/?s=serbia+opposition"},
    {"name": "Slobodna Evropa", "search": "https://www.slobodnaevropa.org/s?k=opozicija"}
]

def get_ai_summary(title, text):
    """使用新版 google-genai SDK 生成摘要"""
    if not text or len(text.strip()) < 100:
        return None

    prompt = f"你是一个资深的巴尔干政治分析师。请为这篇关于‘塞尔维亚反对派’的新闻写一篇400-800字的中文深度摘要。重点关注人物、动作和政治诉求。原文：标题【{title}】，正文【{text}】"
    
    try:
        # 新版 SDK 的调用方式
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        return response.text if response.text else None
    except Exception as e:
        print(f"❌ AI 摘要失败: {e}")
        return None

def extract_links(url):
    """手动提取搜索结果中的文章链接"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
    links = []
    try:
        res = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            # 过滤包含 2026/02 或新闻特征的路径
            if '/2026/02/' in href or '/vesti/' in href or '/news/' in href:
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
    report_path = f"reports/report_{today}.md"
    os.makedirs('reports', exist_ok=True)
    
    final_report = f"# 🇷🇸 塞尔维亚反对派动态每日深度专报\n\n**生成日期**: {today}\n\n---\n"
    found_any = False

    for config in SITES_CONFIG:
        print(f"🔍 扫描站点: {config['name']}")
        links = extract_links(config['search'])
        
        for link in links:
            try:
                article = Article(link, language='sr')
                article.download()
                article.parse()
                
                # 过滤太旧的文章
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
                    time.sleep(5) # 新版 SDK 响应更快，缩短等待
            except Exception as e:
                continue

    if not found_any:
        final_report += "今日未检索到符合条件的实时新闻。"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)
    print(f"✅ 任务完成: {report_path}")

if __name__ == "__main__":
    run_scraper()
