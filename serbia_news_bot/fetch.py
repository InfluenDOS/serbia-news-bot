"""HTTP 与链接抽取。"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from bs4 import BeautifulSoup

from .config import CATEGORY_SLUGS, DEFAULT_BLOCKED_PATHS, REQUEST_TIMEOUT, USER_AGENT
from .sources import NewsSource

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "sr,en;q=0.8"})

# RFE / VOA / Demostat 文章常含数字 id
_DIGIT_ID_RE = re.compile(r"^\d{4,}(?:\.html?)?$", re.I)
_TRAILING_TYPE_SLUGS = frozenset({"vest", "vesti", "bi", "rd", "btj", "en", "lat", "cyr", "amp"})
_BLOCKED_HOSTS = frozenset(
    {
        "facebook.com",
        "twitter.com",
        "t.co",
        "x.com",
        "apple.com",
        "instagram.com",
        "tiktok.com",
        "linkedin.com",
        "youtube.com",
        "youtu.be",
    }
)


def fetch_html(url: str) -> str | None:
    try:
        resp = _SESSION.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 404:
            logger.info("404: %s", url)
            return None
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or resp.encoding
        return resp.text
    except requests.RequestException as exc:
        logger.warning("请求失败 %s: %s", url, exc)
        return None


def _normalize_url(href: str, base_url: str) -> str | None:
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
        return None
    absolute = urljoin(base_url, href)
    absolute, _ = urldefrag(absolute)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    return absolute.rstrip("/")


def _path_blocked(url: str, source: NewsSource) -> bool:
    lower = url.lower()
    for part in DEFAULT_BLOCKED_PATHS:
        if part in lower:
            return True
    for part in source.block_path_parts:
        if part.lower() in lower:
            return True
    return False


def _path_allowed(url: str, source: NewsSource) -> bool:
    if not source.allow_path_parts:
        return True
    lower = url.lower()
    return any(part.lower() in lower for part in source.allow_path_parts)


def _same_registrable_hint(url: str, list_url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    base_host = urlparse(list_url).netloc.lower().removeprefix("www.")
    if not host or not base_host:
        return False
    return host == base_host or host.endswith("." + base_host) or base_host.endswith("." + host)


def looks_like_article_url(url: str) -> bool:
    """排除栏目页、过短 slug，保留像正文的路径。"""
    path = urlparse(url).path.strip("/")
    if not path:
        return False
    parts = [p for p in path.split("/") if p]
    if not parts:
        return False
    lower_parts = [p.lower() for p in parts]
    if "komentari" in lower_parts or "svi-komentari" in lower_parts:
        return False
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if host in _BLOCKED_HOSTS or any(host.endswith("." + h) for h in _BLOCKED_HOSTS):
        return False
    if "/topics/" in urlparse(url).path.lower():
        return False

    # B92 / Euronews: .../<id>/<slug>/vest ；BI: .../YYYY/MM/DD/<slug>/bi
    if lower_parts[-1] in _TRAILING_TYPE_SLUGS and len(parts) >= 2:
        parts = parts[:-1]
        lower_parts = lower_parts[:-1]

    slug = lower_parts[-1]
    if slug in CATEGORY_SLUGS:
        return False
    if _DIGIT_ID_RE.match(slug):
        return True
    # 路径中含明显文章 id
    if any(_DIGIT_ID_RE.match(p) for p in lower_parts):
        return True
    # /YYYY/MM/DD/slug
    if (
        len(parts) >= 4
        and lower_parts[0].isdigit()
        and len(lower_parts[0]) == 4
        and lower_parts[1].isdigit()
        and lower_parts[2].isdigit()
        and len(slug) >= 8
    ):
        return True
    if len(slug) >= 20:
        return True
    if "-" in slug and len(slug) >= 12:
        return True
    if any(ch.isdigit() for ch in slug) and len(slug) >= 8:
        return True
    if len(parts) >= 3 and len(slug) >= 16:
        return True
    return False


def extract_links_from_rss(rss_url: str, source: NewsSource) -> list[str]:
    """从 RSS/Atom 抽取文章链接。"""
    xml = fetch_html(rss_url)
    if not xml:
        return []
    soup = BeautifulSoup(xml, "lxml-xml")
    ordered: list[str] = []
    seen: set[str] = set()
    nodes = soup.find_all("item") or soup.find_all("entry")
    for node in nodes:
        link_node = node.find("link")
        href = ""
        if link_node:
            href = (link_node.get("href") or link_node.text or "").strip()
        if not href:
            guid = node.find("guid")
            href = (guid.text or "").strip() if guid else ""
        url = _normalize_url(href, rss_url)
        if not url or url in seen:
            continue
        if _path_blocked(url, source):
            continue
        if not looks_like_article_url(url):
            continue
        seen.add(url)
        ordered.append(url)
        if len(ordered) >= source.max_links:
            break
    return ordered


def extract_article_links(source: NewsSource) -> list[str]:
    """从源的列表页 / RSS 收集候选文章链接（去重、保序）。"""
    seen: set[str] = set()
    ordered: list[str] = []
    list_set = {u.rstrip("/") for u in source.list_urls}

    # 优先 RSS（对 JS 重度站点更稳）
    for rss_url in getattr(source, "rss_urls", ()) or ():
        for url in extract_links_from_rss(rss_url, source):
            if url in seen:
                continue
            seen.add(url)
            ordered.append(url)
            if len(ordered) >= source.max_links:
                logger.info("%s 抽到候选链接 %s 条 (rss)", source.name, len(ordered))
                return ordered

    for list_url in source.list_urls:
        html = fetch_html(list_url)
        if not html:
            continue
        # 若误把 RSS XML 配进 list_urls，也尝试解析
        if "<rss" in html[:200].lower() or "<feed" in html[:200].lower():
            for url in extract_links_from_rss(list_url, source):
                if url not in seen:
                    seen.add(url)
                    ordered.append(url)
            if len(ordered) >= source.max_links:
                break
            continue

        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            url = _normalize_url(a["href"], list_url)
            if not url or url in seen:
                continue
            if url.rstrip("/") in list_set:
                continue
            if not _same_registrable_hint(url, list_url):
                continue
            if _path_blocked(url, source):
                continue
            if not _path_allowed(url, source):
                continue
            if not looks_like_article_url(url):
                continue
            seen.add(url)
            ordered.append(url)
            if len(ordered) >= source.max_links:
                logger.info("%s 抽到候选链接 %s 条", source.name, len(ordered))
                return ordered

    logger.info("%s 抽到候选链接 %s 条", source.name, len(ordered))
    return ordered
