import os
import time
import datetime
import requests
from bs4 import BeautifulSoup
from newspaper import Article

# === 1. 验证配置 (只看 Danas) ===
SITE_URL = "https://www.danas.rs/vesti/"
# 如果你想测试昨天的，把下面的 today 改成 datetime.date(2026, 2, 11)
TARGET_DATE = datetime.date(2026, 2, 11)
def extract_raw_links(url):
    """从 Danas 新闻流中提取所有潜在链接"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    links = []
    try:
        print(f"🌐 正在请求列表页: {url}")
        res = requests.get(url, headers=headers, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Danas 文章链接通常包含 /vesti/ 且以 http 开头
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/vesti/' in href and href.startswith('http'):
                if href not in links:
                    links.append(href)
        print(f"🔗 共发现 {len(links)} 条原始链接")
    except Exception as e:
        print(f"❌ 列表请求失败: {e}")
    return list(set(links))

def run_validation():
    print(f"🚀 --- 开始抓取能力验证 (目标日期: {TARGET_DATE}) ---")
    
    # 准备报告文件
    report_path = f"reports/validation_{TARGET_DATE}.md"
    os.makedirs('reports', exist_ok=True)
    
    links = extract_raw_links(SITE_URL)
    found_count = 0
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Danas 抓取验证报告 - {TARGET_DATE}\n\n")
        
        for i, link in enumerate(links):
            try:
                # 打印进度，防止 Actions 看起来像卡住了
                print(f"🧐 [{i+1}/{len(links)}] 正在解析: {link}")
                
                article = Article(link, language='sr')
                article.download()
                article.parse()
                
                # 日期校验
                pub_date = article.publish_date
                if pub_date and pub_date.date() == TARGET_DATE:
                    found_count += 1
                    output = f"### 【第 {found_count} 篇匹配文章】\n"
                    output += f"**标题**: {article.title}\n"
                    output += f"**链接**: {link}\n"
                    output += f"**发布时间**: {pub_date}\n\n"
                    output += f"**正文预览 (前 800 字)**:\n{article.text[:800]}...\n\n"
                    output += "---\n\n"
                    
                    # 同时输出到控制台（GitHub Actions 日志）
                    print(f"✅ 匹配成功: {article.title}")
                    f.write(output)
                
                # 即使不匹配日期，如果是我们要找的关键词，也可以在日志里记录一下
                elif "opozicija" in article.text.lower() or "protest" in article.text.lower():
                    print(f"💡 发现相关关键词但日期不符 ({pub_date}): {article.title}")

                # 验证版不需要休眠太久，1秒即可
                time.sleep(1)
                
            except Exception as e:
                print(f"⚠️ 解析失败 {link}: {e}")
                continue

        if found_count == 0:
            f.write(f"\n今日 ({TARGET_DATE}) 在列表页未发现符合日期要求的文章。")
            print("❗ 警告: 未发现任何符合日期的文章，请检查网站是否已更新。")

    print(f"\n🚀 验证结束。共捕获 {found_count} 篇当日文章。")
    print(f"📁 结果已存入: {report_path}")

if __name__ == "__main__":
    run_scraper = run_validation # 为了兼容 workflow 里的调用
    run_validation()
