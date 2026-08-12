"""端到端流水线：多源抓取 → 日期过滤 → AI 判定摘要 → 写报告。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from . import config
from .ai import evaluate_article
from .article import ParsedArticle, download_article
from .emailer import send_report_email
from .fetch import extract_article_links
from .report import ReportItem, write_report
from .sources import SOURCES

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    links_found: int = 0
    articles_parsed: int = 0
    kept: int = 0
    skipped_ai: int = 0
    errors: int = 0


def _priority_key(article: ParsedArticle) -> tuple:
    # 有明确发布日、关键词命中多的优先送 AI
    has_date = 0 if article.publish_date is not None else 1
    return (has_date, -article.hint_score, article.source_name, article.url)


def run_pipeline() -> Path:
    target = config.resolve_target_date()
    allowed_dates = config.lookback_dates(target, days=1)
    logger.info("监测日=%s 允许发布日=%s DRY_RUN=%s", target, allowed_dates, config.DRY_RUN)

    if not config.DRY_RUN and not config.KIMI_API_KEY:
        raise RuntimeError("缺少环境变量 KIMI_API_KEY（或设置 DRY_RUN=1）")

    stats = PipelineStats()
    candidates: list[ParsedArticle] = []
    seen_urls: set[str] = set()

    for source in SOURCES:
        logger.info("扫描信源: %s", source.name)
        try:
            links = extract_article_links(source)
        except Exception as exc:  # noqa: BLE001
            logger.warning("信源列表失败 %s: %s", source.name, exc)
            stats.errors += 1
            continue

        stats.links_found += len(links)
        limit = min(len(links), config.MAX_ARTICLES_PER_SITE, source.max_links)

        for link in links[:limit]:
            if link in seen_urls:
                continue
            seen_urls.add(link)
            article = download_article(
                link,
                source_name=source.name,
                language=source.language,
                allowed_dates=allowed_dates,
            )
            time.sleep(config.ARTICLE_SLEEP_SEC)
            if not article:
                continue
            # 无发布日时：仅当关键词粗筛命中才进入 AI，降低噪音
            if article.publish_date is None and article.hint_score == 0:
                continue
            candidates.append(article)
            stats.articles_parsed += 1

    candidates.sort(key=_priority_key)
    logger.info("进入 AI 评估的候选: %s", len(candidates))

    kept: list[ReportItem] = []
    for article in candidates:
        logger.info(
            "AI 评估: [%s] %s (hint=%s, date=%s)",
            article.source_name,
            article.title[:60],
            article.hint_score,
            article.publish_date,
        )
        verdict = evaluate_article(article, target)
        if verdict is None:
            stats.errors += 1
            continue
        if not verdict.relevant:
            stats.skipped_ai += 1
            logger.info("跳过: %s", verdict.reason)
            continue
        kept.append(ReportItem(article=article, verdict=verdict))
        stats.kept += 1
        if not config.DRY_RUN:
            time.sleep(config.AI_SLEEP_SEC)

    out = write_report(target, kept, scanned=stats.articles_parsed)
    logger.info(
        "完成 → %s | links=%s parsed=%s kept=%s skipped=%s errors=%s",
        out,
        stats.links_found,
        stats.articles_parsed,
        stats.kept,
        stats.skipped_ai,
        stats.errors,
    )
    if (
        not config.DRY_RUN
        and stats.articles_parsed > 0
        and stats.kept == 0
        and stats.skipped_ai == 0
        and stats.errors > 0
    ):
        raise RuntimeError(
            f"AI 评估全部失败（errors={stats.errors}）。请检查 KIMI_API_KEY / 模型权限。"
        )

    if not config.DRY_RUN:
        send_report_email(out, kept=stats.kept, scanned=stats.articles_parsed)

    return out
