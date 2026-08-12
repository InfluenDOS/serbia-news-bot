"""运行时配置（可通过环境变量覆盖）。"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BELGRADE_TZ = ZoneInfo("Europe/Belgrade")

# Kimi / Moonshot（OpenAI 兼容）
KIMI_API_KEY = (
    os.environ.get("KIMI_API_KEY", "").strip()
    or os.environ.get("MOONSHOT_API_KEY", "").strip()
)
KIMI_BASE_URL = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
KIMI_MODEL = os.environ.get("KIMI_MODEL", "kimi-k2.6")

# 行为开关
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in {"1", "true", "yes"}
MAX_ARTICLES_PER_SITE = int(os.environ.get("MAX_ARTICLES_PER_SITE", "8"))
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "20"))
ARTICLE_SLEEP_SEC = float(os.environ.get("ARTICLE_SLEEP_SEC", "0.4"))
AI_SLEEP_SEC = float(os.environ.get("AI_SLEEP_SEC", "3"))
AI_MAX_RETRIES = int(os.environ.get("AI_MAX_RETRIES", "3"))
MIN_ARTICLE_CHARS = int(os.environ.get("MIN_ARTICLE_CHARS", "180"))
REPORTS_DIR = os.environ.get("REPORTS_DIR", "reports")

# 邮件（可选）：配齐凭证后每日自动发送
REPORT_TO_EMAIL = os.environ.get("REPORT_TO_EMAIL", "speechlessgorilla@gmail.com").strip()
REPORT_FROM_EMAIL = os.environ.get("REPORT_FROM_EMAIL", "").strip()
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# 评论/专栏/导航等非正文路径片段
DEFAULT_BLOCKED_PATHS = (
    "/opinion/",
    "/opinions/",
    "/komentari/",
    "/komentari",
    "/kolumna/",
    "/kolumne/",
    "/stav/",
    "/pogledi/",
    "/blog/",
    "/kultura/",
    "/zabava/",
    "/sport/",
    "/lifestyle/",
    "/horoskop/",
    "/tag/",
    "/autor/",
    "/author/",
    "/page/",
    "/category/",
    "/rubrika/",
    "/video/",
    "/live/",
    "/liveblog/",
)

# 末级路径等于这些时，多半是栏目页而非文章
CATEGORY_SLUGS = frozenset(
    {
        "vesti",
        "politika",
        "drustvo",
        "ekonomija",
        "biznis",
        "svet",
        "info",
        "news",
        "srbija",
        "hronika",
        "region",
        "balkan",
        "analize",
        "tema",
        "teme",
        "naslovna",
        "home",
        "latest",
        "najnovije",
        "serbia",
        "english",
        "lat",
        "cyr",
        "sr",
        "en",
        "bs",
        "komentari",
        "nase-price",
        "specijal",
    }
)


def resolve_target_date() -> date:
    """目标监测日：默认贝尔格莱德本地“今天”，可用 TARGET_DATE=YYYY-MM-DD 覆盖。"""
    raw = os.environ.get("TARGET_DATE", "").strip()
    if raw:
        return date.fromisoformat(raw)
    return datetime.now(BELGRADE_TZ).date()


def date_url_tokens(target: date) -> tuple[str, ...]:
    """常见 URL 日期片段，用于辅助匹配当日文章。"""
    y, m, d = target.year, target.month, target.day
    return (
        f"/{y}/{m:02d}/{d:02d}/",
        f"/{y}-{m:02d}-{d:02d}/",
        f"/{d:02d}-{m:02d}-{y}/",
        f"/{d:02d}.{m:02d}.{y}/",
        f"{y}/{m:02d}/{d:02d}",
    )


def lookback_dates(target: date, days: int = 1) -> list[date]:
    """允许收录的发布日（默认含目标日及前一天，应对跨日/晚发）。"""
    return [target - timedelta(days=i) for i in range(days + 1)]
