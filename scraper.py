import os
import time
import datetime
import requests
from newspaper import Article
import google.generativeai as genai

# === 1. 配置 AI 引擎 ===
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
ai_model = genai.GenerativeModel('gemini-1.5-flash')

# === 2. 目标网站配置 ===
# 这里的搜索链接会根据关键词动态生成
SITES = [
    "https://n1info.rs/?s=",
    "https://nova.rs/?s=",
    "https://www.danas.rs/?s=",
    "https://balkaninsight.com/?s=",
    "https://www.slobodnaevropa.org/s?k=",
    "https://serbiantimes.info/en/?s=",
    "https://www.b92.net/specijal/3/english/search.php?q="
]
KEYWORD = "opozicija" # 塞尔维亚语：反对派

def get_ai_summary(title, text):
    """调用 Gemini 生成深度摘要"""
    prompt = f"""
    你是一个深耕巴尔干半岛政治的专业分析师。请为我摘要以下关于塞尔维亚反对派的新闻。
    
    【文章标题】：{title}
    【文章正文】：{text}

    【摘要要求】：
    1. 必须使用中文。
    2. 字数严格控制在 300-800 字之间，细节要极其丰富。
    3. 重点提炼反对派的具体行动、政治诉求、涉及的具体人物、以及对政府（武契奇）的具体批评。
    4. 排除原文中的广告内容、网页导航信息。
    5. 保持客观中立，以深度报道的口吻撰写。
    """
    try:
        response = ai_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 摘要生成失败: {str(e)}"

def run_scraper():
    today = datetime.date.today()
    report_path = f"reports/report_{today}.md"
    os.makedirs('reports', exist_ok=True)
    
    final_report = f"# 🇷🇸 塞尔维亚反对派动态每日深度专报\n\n**生成日期**: {today}\n\n---\n"
    found_any = False

    for base_url in SITES:
        search_url = base_url + KEYWORD
        print(f"正在扫描: {search_url}")
        
        try:
            # 获取搜索页文章链接（此处使用 newspaper 自动化流）
            import newspaper
            paper = newspaper.build(search_url, language='sr', memoize_articles=False)
            
            # 只取前 3 篇今天的文章，避免 API 过载
            count = 0
            for article in paper.articles:
                if count >= 3: break
                
                article.download()
                article.parse()
                
                # 时效性校验（如果是今天发布的，或者没有日期但内容包含关键动态）
                pub_date = article.publish_date
                if pub_date and pub_date.date() != today:
                    continue
                
                print(f"正在处理文章: {article.title}")
                summary = get_ai_summary(article.title, article.text)
                
                final_report += f"## 📰 {article.title}\n"
                final_report += f"**原文链接**: {article.url}\n\n"
                final_report += f"### 深度摘要\n{summary}\n\n"
                final_report += "---\n\n"
                
                found_any = True
                count += 1
                time.sleep(10) # 遵守 API 频率限制

        except Exception as e:
            print(f"处理 {base_url} 时发生错误: {e}")

    if not found_any:
        final_report += "今日在指定源中未发现相关实时新闻。"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)

if __name__ == "__main__":
    run_scraper()
