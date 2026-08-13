"""新闻源配置。

优先使用「新闻列表页」而非搜索页（搜索页结构易变、且常被反爬）。
历史仓库曾配置约 10 个源；此处保留可用源并补充若干高质量塞尔维亚/区域媒体。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NewsSource:
    name: str
    list_urls: tuple[str, ...]
    # 链接需至少命中其一（空则只做域名与黑名单过滤）
    allow_path_parts: tuple[str, ...] = ()
    block_path_parts: tuple[str, ...] = ()
    rss_urls: tuple[str, ...] = ()
    language: str = "sr"
    max_links: int = 12


# 历史源 + 补充源。list_urls 偏向政治/国内新闻频道。
SOURCES: tuple[NewsSource, ...] = (
    NewsSource(
        name="N1 Info",
        list_urls=(
            "https://n1info.rs/vesti/",
            "https://n1info.rs/vesti/politika/",
        ),
        allow_path_parts=("/vesti/",),
        language="sr",
    ),
    NewsSource(
        name="Nova.rs",
        list_urls=(
            "https://nova.rs/vesti/",
            "https://nova.rs/vesti/politika/",
        ),
        allow_path_parts=("/vesti/",),
        language="sr",
    ),
    NewsSource(
        name="Danas",
        list_urls=(
            "https://www.danas.rs/rubrika/vesti/",
            "https://www.danas.rs/rubrika/politika/",
        ),
        allow_path_parts=("/vesti/", "/politika/"),
        language="sr",
    ),
    NewsSource(
        name="Vreme",
        list_urls=(
            "https://vreme.com/",
            "https://vreme.com/vesti/",
        ),
        allow_path_parts=("/vesti/", "/politika/", "/drustvo/"),
        language="sr",
    ),
    NewsSource(
        name="B92",
        list_urls=(
            "https://www.b92.net/najnovije-vesti",
            "https://www.b92.net/info/politika",
        ),
        rss_urls=("https://www.b92.net/info/rss",),
        allow_path_parts=("/info/", "/vesti/", "/politika/", "/drustvo/"),
        block_path_parts=("/sport/", "/zivot/", "/superzena", "/esports/"),
        language="sr",
    ),
    NewsSource(
        name="Euronews Srbija",
        list_urls=(
            "https://www.euronews.rs/srbija/politika",
            "https://www.euronews.rs/najnovije-vesti-dana",
        ),
        allow_path_parts=("/srbija/", "/vesti/"),
        block_path_parts=("/sport/", "/magazin/", "/putovanja/", "/kultura/"),
        language="sr",
    ),
    NewsSource(
        name="Insajder",
        list_urls=(
            "https://www.insajder.net/teme",
            "https://www.insajder.net/",
        ),
        allow_path_parts=("/vesti/",),
        language="sr",
    ),
    NewsSource(
        name="Radar",
        list_urls=(
            "https://radar.nova.rs/",
            "https://radar.nova.rs/politika/",
        ),
        allow_path_parts=("/politika/", "/drustvo/", "/istrazivanja/"),
        language="sr",
    ),
    NewsSource(
        name="Slobodna Evropa",
        list_urls=(
            "https://www.slobodnaevropa.org/z/500",  # Srbija
        ),
        allow_path_parts=("/a/",),
        language="sr",
    ),
    NewsSource(
        name="BBC Serbian",
        list_urls=("https://www.bbc.com/serbian/lat",),
        allow_path_parts=("/serbian/articles/", "/serbian/lat/"),
        block_path_parts=("/topics/", "/popular/"),
        language="sr",
    ),
    NewsSource(
        name="Balkan Insight",
        list_urls=(
            "https://balkaninsight.com/balkan-countries/serbia/",
        ),
        rss_urls=("https://balkaninsight.com/feed/",),
        allow_path_parts=("/20",),  # /2026/...
        block_path_parts=("/reporting-democracy/", "/premium", "/about-"),
        language="en",
    ),
    NewsSource(
        name="Demostat",
        list_urls=(
            "https://demostat.rs/sr/vesti/analize/0",
            "https://demostat.rs/sr/vesti/ekskluziva/0",
        ),
        allow_path_parts=("/vesti/",),
        block_path_parts=("/kolumne/", "/prijava", "/o-nama", "/kontakt"),
        language="sr",
        max_links=8,
    ),
    NewsSource(
        name="Al Jazeera Balkans",
        list_urls=(
            "https://balkans.aljazeera.net/news/balkan",
            "https://balkans.aljazeera.net/tag/srbija/",
        ),
        allow_path_parts=("/news/", "/features/"),
        language="bs",
    ),
    NewsSource(
        name="Serbian Monitor",
        list_urls=("https://www.serbianmonitor.com/",),
        allow_path_parts=("/",),
        language="en",
        max_links=8,
    ),
)


# 粗筛关键词：命中标题/正文时优先送 AI；未命中也可送，但可用来排序
RELEVANCE_HINT_TERMS: tuple[str, ...] = (
    # 通用
    "opozicija",
    "опозиција",
    "opposition",
    "u vlasti",
    "vladajuć",
    "skupštin",
    "protest",
    "blokad",
    "demonstrac",
    "izbor",
    "student",
    "studenti",
    "napad",
    "štrajk",
    "strajk",
    # 执政党/现政权（出现且同时有在野动作时仍可能相关）
    "vučić",
    "vucic",
    "sns",
    "naprednjac",
    # 常见在野力量 / 名单（随政局变化可在此增补）
    "ssp",
    "stranka slobode i pravde",
    "marinika",
    "tepačvić",
    "tepavcevic",
    "đilas",
    "djilas",
    "zlf",
    "zeleno-levi",
    "zeleno levi",
    "jeremić",
    "jeremic",
    "narodni pokret",
    "srbija protiv nasilja",
    "spn",
    "kreni-promeni",
    "kreni promeni",
    "dveri",
    "dss",
    "poks",
    "nds",
    "nova dss",
    "usamljeni",
    "nezavisni poslanik",
    "poslanički klub",
    "srce",
    "pokret",
)
