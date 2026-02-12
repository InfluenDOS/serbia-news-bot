import os
import time
import datetime
import requests
from bs4 import BeautifulSoup
from newspaper import Article

# === 1. 验证配置 (Danas 深度翻页版) ===
BASE_URL = "https://www.danas.rs/vesti/"
TARGET_DATE = datetime.date(2026,2,10) # 默认抓今天，测试可改

def extract_links_from_page(page_num):
    """抓取特定页码中的所有链接"""
    url = f"{BASE_URL}page/{page_num}/" if page_num > 1 else BASE_URL
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    links = []
    try:
        print(f"📄 正在扫描第 {page_num} 页: {url}")
        res = requests.get(url, headers=headers, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Danas 的文章特征：包含 /vesti/
            if '/vesti/' in href and href.startswith('http'):
                if href not in links:
                    links.append(href)
        return list(set(links))
    except Exception as e:
        print(f"❌ 第 {page_num} 页请求失败: {e}")
        return []

def run_validation():
    print(f"🚀 --- 开始 Danas 深度抓取验证 (目标日期: {TARGET_DATE}) ---")
    
    report_path = f"reports/full_scan_{TARGET_DATE}.md"
    os.makedirs('reports', exist_ok=True)
    
    all_matched_articles = []
    page = 1
    should_continue = True

    while should_continue:
        links = extract_links_from_page(page)
        if not links:
            break
            
        page_found_count = 0
        for i, link in enumerate(links):
            try:
                article = Article(link, language='sr')
                article.download()
                article.parse()
                
                pub_date = article.publish_date
                if pub_date:
                    article_date = pub_date.date()
                    
                    # 匹配成功：存入列表
                    if article_date == TARGET_DATE:
                        all_matched_articles.append({
                            "title": article.title,
                            "link": link,
                            "text": article.text
                        })
                        page_found_count += 1
                    
                    # 核心逻辑：如果发现文章日期早于目标日期，说明翻页到头了
                    elif article_date < TARGET_DATE:
                        # 注意：为了防止因为置顶文章导致误判，只有在翻到一定页数后才停止
                        if page > 1:
                            print(f"🛑 发现更早的文章 ({article_date})，停止翻页。")
                            should_continue = False
                            break
                
                time.sleep(0.5) # 轻量抓取
            except:
                continue
        
        print(f"✅ 第 {page} 页扫描完毕，找到 {page_found_count} 篇符合日期的文章。")
        page += 1
        # 安全阀：防止死循环，最多翻 10 页
        if page > 10: 
            break

    # 汇总写入报告
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Danas 全量抓取验证报告 - {TARGET_DATE}\n\n")
        f.write(f"共在 {page-1} 页中提取到 {len(all_matched_articles)} 篇当日文章。\n\n---\n\n")
        
        for article in all_matched_articles:
            f.write(f"### 📰 {article['title']}\n")
            f.write(f"**URL**: {article['link']}\n\n")
            f.write(f"**内容预览**:\n{article['text'][:1000]}...\n\n")
            f.write("---\n\n")
            # 在控制台也输出一下确认
            print(f"📥 已记录: {article['title']}")

    print(f"\n🚀 任务完成。共捕获 {len(all_matched_articles)} 篇当日新闻。")

if __name__ == "__main__":
    run_scraper = run_validation
    run_validation()
