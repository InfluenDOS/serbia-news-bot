"""文章下载与日期校验。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from newspaper import Article

from .config import MIN_ARTICLE_CHARS
from .sources import RELEVANCE_HINT_TERMS

logger = logging.getLogger(__name__)


@dataclass
class ParsedArticle:
    source_name: str
    url: str
    title: str
    text: str
    publish_date: date | None
    language: str
    hint_score: int = 0


def _to_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def hint_score(title: str, text: str) -> int:
    blob = f"{title}\n{text}".lower()
    return sum(1 for term in RELEVANCE_HINT_TERMS if term.lower() in blob)


def download_article(
    url: str,
    *,
    source_name: str,
    language: str,
    allowed_dates: Iterable[date],
) -> ParsedArticle | None:
    allowed = set(allowed_dates)
    try:
        article = Article(url, language=language)
        article.download()
        article.parse()
    except Exception as exc:  # newspaper 内部异常类型较杂
        logger.debug("解析失败 %s: %s", url, exc)
        return None

    title = (article.title or "").strip()
    text = (article.text or "").strip()
    if not title or len(text) < MIN_ARTICLE_CHARS:
        return None

    pub = _to_date(article.publish_date)
    # 有明确日期且不在允许窗口内 → 丢弃
    if pub is not None and pub not in allowed:
        return None

    return ParsedArticle(
        source_name=source_name,
        url=url,
        title=title,
        text=text,
        publish_date=pub,
        language=language,
        hint_score=hint_score(title, text),
    )
