import os
import time
import datetime
import requests
from newspaper import Article
import google.generativeai as genai

# === 1. 配置 AI 引擎 (基于调试结果) ===
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
# 使用你调试出的最新稳定模型 ID
MODEL_ID = 'models/gemini-2.5-flash'
ai_model = genai.GenerativeModel(MODEL_ID)

# === 2. 目标网站配置 ===
SITES = [
    "https://n1info.rs/?s=",
    "https://nova.rs/?s=",
    "https://www.danas.rs/?s=",
    "https://balkaninsight.com/?s=",
    "https://www.slobodnaevropa.org/s?k=",
    "https://serbiantimes.info/en/?s=",
    "https://www.b92.net/specijal/3/english/search.php?q="
]
KEYWORD = "opozicija" 

def get_ai_summary(title, text):
    """调用 Gemini 2.5 生成深度摘要"""
    if not text or len(text.strip()) < 100:
        return "原文内容过短，无法生成高质量摘要。"

    prompt = f"""
    你是一个深耕巴尔干半岛政治的专业分析师。请为我摘要以下关于塞尔维亚反对派的新闻。
    
    【文章标题】：{title}
    【文章正文】：{text}

    【摘要要求】：
    1. 必须使用中文。
    2. 字数在 400-800 字之间，细节要极其丰富。
    3. 重点提炼：反对派的具体行动、具体的人物姓名、具体的时间点、政治诉求以及对执政当局的批评。
    4. 排除广告、无关推荐信息。
    5. 采用专业、冷静的调查记者口吻。
    """
    try:
        response = ai_model.generate_content(prompt)
        return response.text if response.text else "AI 未能生成内容。"
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
            # 使用更稳健的链接抓取方式
            from newspaper import build
            paper = newspaper.build(search_url, language='sr', memoize_articles=False)
            
            # 每次搜索只取前 2 篇今天的文章，确保摘要质量和 API 稳定
            count = 0
            for article in paper.articles:
                if count >= 2: break
                
                try:
                    article.download()
                    article.parse()
                    
                    # 检查日期：如果是今天或昨天（考虑到时差）
                    pub_date = article.publish_date
                    is_recent = False
                    if pub_date:
                        is_recent = (pub_date.date() >= today - datetime.timedelta(days=1))
                    else:
                        # 如果抓不到日期，暂时默认抓取以供查看（或根据关键词判断）
                        is_recent = True 

                    if is_recent:
                        print(f"✅ 正在生成摘要: {article.title}")
                        summary = get_ai_summary(article.title, article.text)
                        
                        final_report += f"## 📰 {article.title}\n"
                        final_report += f"**原文链接**: {article.url}\n\n"
                        final_report += f"### 深度摘要\n{summary}\n\n"
                        final_report += "---\n\n"
                        
                        found_any = True
                        count += 1
                        time.sleep(12) # 严格遵守免费版频率限制
                except:
                    continue

        except Exception as e:
            print(f"⚠️ 站点 {base_url} 抓取跳过: {e}")

    if not found_any:
        final_report += "今日在指定源中未发现符合条件的实时新闻。"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)
    print(f"🚀 报告已生成: {report_path}")

if __name__ == "__main__":
    run_scraper()
