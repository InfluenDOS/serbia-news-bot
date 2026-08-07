"""Markdown 报告生成。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .ai import AIVerdict
from .article import ParsedArticle
from .config import REPORTS_DIR


@dataclass
class ReportItem:
    article: ParsedArticle
    verdict: AIVerdict


def build_markdown(target_date: date, items: list[ReportItem], scanned: int) -> str:
    lines: list[str] = [
        f"# 塞尔维亚在野党动态每日专报（{target_date.isoformat()}）",
        "",
        f"**监测日**: {target_date.isoformat()}  ",
        "**口径**: 与现执政党立场对立的在野党派 / 反执政阵营硬新闻  ",
        f"**候选文章扫描**: {scanned} 篇 · **收录**: {len(items)} 篇",
        "",
        "---",
        "",
    ]

    if not items:
        lines.append(f"今日（{target_date.isoformat()}）未收录符合口径的在野党相关硬新闻。")
        lines.append("")
        return "\n".join(lines)

    for idx, item in enumerate(items, start=1):
        art = item.article
        ver = item.verdict
        actors = "、".join(ver.actors) if ver.actors else "—"
        pub = art.publish_date.isoformat() if art.publish_date else "未知"
        lines.extend(
            [
                f"## {idx}. {art.title}",
                "",
                f"**来源**: {art.source_name}  ",
                f"**发布日**: {pub}  ",
                f"**相关方**: {actors}  ",
                f"**原文**: {art.url}",
                "",
                f"**筛选说明**: {ver.reason}",
                "",
                ver.summary_zh.strip(),
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines)


def write_report(target_date: date, items: list[ReportItem], scanned: int) -> Path:
    path = Path(REPORTS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    out = path / f"report_{target_date.isoformat()}.md"
    out.write_text(build_markdown(target_date, items, scanned), encoding="utf-8")
    return out
