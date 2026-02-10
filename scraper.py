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
    {"name": "N1 Info", "search": "https://n1info.rs/?s=opozicija+danas"}, # danas 表示“今天”
    {"name": "Nova.rs", "search": "https://nova.rs/?s=opozicija+najnovije"}, # najnovije 表示“最新”
    {"name": "Danas", "search": "https://www.danas.rs/?s=opozicija+vesti"},
    # ... 其他站点保持类似逻辑   
]

def get_ai_summary(title, text):
    """带重试机制的 AI 摘要生成"""
    if not text or len(text.strip()) < 100:
        return None

   # 核心 Prompt 升级：增加时效性判定
    prompt = f"""
    你是一个负责实时情报监控的分析师。你的任务是处理以下新闻稿，并执行严格过滤：

    【判定规则】：
    1. **事件时效性**：这篇文章描述的是【今天（2026年2月10日）】发生的具体事件、声明、抗议或冲突吗？
    2. **内容属性**：如果是对过去一周的总结、历史回顾、或者纯粹的评论分析（没有今日新增动作），请直接回答“SKIP”。
    3. **摘要要求**：如果通过判定，请用中文写一篇400-800字的深度摘要。

    【摘要重点】：
    - 发生了什么具体动作（谁、在哪、做了什么）？
    - 重要人物的原始表述（他说原话是什么，而不是别人对他的评价）。
    - 现场细节（人数、氛围、警方动作等）。

    【文章标题】：{title}
    【文章正文】：{text}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=MODEL_ID, contents=prompt)
            content = response.text.strip()
            
            # 如果 AI 判定不是今日新闻，则不输出
            if content.upper() == "SKIP":
                print(f"⏩ 跳过分析类或非今日事件文章: {title}")
                return None
            return content
        except Exception as e:
            # (保持原有的 429/503 重试逻辑...)
            time.sleep(30)
    return None

def extract_links(url, today_str_list):
    """提取链接，且链接必须包含今天的日期特征"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
    links = []
    
    try:
        res = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            # 严格筛选：链接必须包含今天的日期字符串（如 /2026/02/10/）
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
    # 获取今天日期
    today = datetime.date.today()
    # 构造多种日期格式以匹配不同的 URL 结构
    today_str_list = [
        today.strftime('/%Y/%m/%d/'),  # /2026/02/10/
        today.strftime('/%Y-%m-%d/'),  # /2026-02-10/
        today.strftime('/%d-%m-%Y/')   # /10-02-2026/
    ]
    
    report_path = f"reports/report_{today}.md"
    os.makedirs('reports', exist_ok=True)
    
    final_report = f"# 🇷🇸 塞尔维亚反对派动态每日深度专报\n\n**生成日期**: {today} (严格当日新闻)\n\n---\n"
    found_any = False

    for config in SITES_CONFIG:
        print(f"🔍 扫描站点: {config['name']}")
        links = extract_links(config['search'], today_str_list)
        
        for link in links:
            # --- 核心修改：在此处插入黑名单过滤 ---
            blacklist = ['/opinion/', '/komentari/', '/kolumna/', '/svet-oko-nas/', '/izbori-2023/', '/stav/']
            if any(word in href for word in blacklist):
                continue # 如果链接包含这些词，直接跳过，看下一个
                
            try:
                article = Article(link, language='sr')
                article.download()
                article.parse()
                
                # 【核心修改点】严格校验：必须是今天发布的文章
                # 如果没有抓到日期，或者日期不是今天，坚决跳过
                if not article.publish_date or article.publish_date.date() != today:
                    continue

               
                print(f"📝 正在总结今日新闻: {article.title}")
                summary = get_ai_summary(article.title, article.text)
                
                if summary:
                    final_report += f"## 📰 {article.title}\n"
                    final_report += f"**来源**: {config['name']} | [原文链接]({link})\n\n"
                    final_report += f"{summary}\n\n---\n\n"
                    found_any = True
                    time.sleep(20) 
            except:
                continue

    if not found_any:
        final_report += f"今日 ({today}) 在指定源中未检索到符合条件的实时新闻。"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)
    print(f"✅ 任务完成: {report_path}")

if __name__ == "__main__":
    run_scraper()
