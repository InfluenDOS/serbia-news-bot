import os
import time
import datetime
import requests
from bs4 import BeautifulSoup
from newspaper import Article

# === 1. 验证配置 (修正后的 Danas 分类存档路径) ===
# 使用 /rubrika/vesti/ 确保分页逻辑 (page/N/) 有效
BASE_URL = "https://www.danas.rs/rubrika/vesti/"
TARGET_DATE = datetime.date(2026, 2, 10) # 调试建议：先锁定到昨天 2月11日

def extract_links_from_page(page_num):
    """从 Danas 分类存档中抓取特定页码的所有链接"""
    url = f"{BASE_URL}page/{page_num}/" if page_num > 1 else BASE_URL
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    try:
        print(f"📄 正在扫描分类页: {url}")
        res = requests.get(url, headers=headers, timeout=20)
        
        if res.status_code == 404:
            print(f"🏁 翻页结束：已到达页面上限。")
            return None
            
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Danas 文章特征
            if '/vesti/' in href and href.startswith('http'):
                if href not in links:
                    links.append(href)
        return list(set(links))
    except Exception as e:
        print(f"❌ 访问出错: {e}")
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
        if links is None: break # 遇到 404 正常退出
        if not links: break
            
        page_found_count = 0
        for link in links:
            try:
                # 跳过明显的非文章链接
                if any(x in link for x in ['/page/', '/rubrika/']): continue

                article = Article(link, language='sr')
                article.download()
                article.parse()
                
                pub_date = article.publish_date
                if pub_date:
                    article_date = pub_date.date()
                    
                    if article_date == TARGET_DATE:
                        all_matched_articles.append({
                            "title": article.title,
                            "link": link,
                            "text": article.text
                        })
                        page_found_count += 1
                        print(f"✅ 捕获文章: {article.title[:40]}...")
                    
                    # 如果翻到第2页以后，开始出现比目标日期更早的文章，说明可以停了
                    elif article_date < TARGET_DATE and page > 1:
                        print(f"🛑 发现更早的日期 ({article_date})，自动停止扫描。")
                        should_continue = False
                        break
                
                time.sleep(0.3) # 纯测试，速度可以稍微快一点
            except:
                continue
        
        print(f"📊 第 {page} 页处理完毕。")
        page += 1
        if page > 15: break # 安全阀：最多翻 15 页

    # 汇总写入报告
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Danas 原始抓取验证报告\n\n日期: {TARGET_DATE} | 共捕获: {len(all_matched_articles)} 篇\n\n")
        for art in all_matched_articles:
            f.write(f"### {art['title']}\n- **链接**: {art['link']}\n- **原文预览**:\n{art['text'][:1500]}\n\n---\n\n")

    print(f"\n🚀 验证完成。请去 reports/ 查看最终文件。")

if __name__ == "__main__":
    run_scraper = run_validation
    run_validation()
