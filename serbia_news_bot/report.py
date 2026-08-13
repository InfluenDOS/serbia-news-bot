"""报告生成（Word .docx）：仅标题 + 正文 + 原文链接。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from .ai import AIVerdict
from .article import ParsedArticle
from .config import REPORTS_DIR


@dataclass
class ReportItem:
    article: ParsedArticle
    verdict: AIVerdict


def build_docx(target_date: date, items: list[ReportItem], scanned: int) -> Document:
    doc = Document()

    title = doc.add_heading("塞尔维亚在野党动态每日专报", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph(target_date.isoformat())
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if sub.runs:
        sub.runs[0].font.size = Pt(14)
        sub.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    doc.add_paragraph()

    if not items:
        doc.add_paragraph(f"今日（{target_date.isoformat()}）未收录符合口径的在野党相关硬新闻。")
        return doc

    for idx, item in enumerate(items, start=1):
        ver = item.verdict
        heading = ver.title_zh.strip() or item.article.title
        doc.add_heading(f"{idx}. {heading}", level=1)

        for para in ver.summary_zh.strip().split("\n"):
            if para.strip():
                doc.add_paragraph(para.strip())

        link_p = doc.add_paragraph()
        link_run = link_p.add_run(item.article.url)
        link_run.font.color.rgb = RGBColor(0x05, 0x63, 0xC1)
        link_run.underline = True

        if idx < len(items):
            doc.add_paragraph()

    # scanned 仅用于日志侧统计，报告正文不再展示元数据
    _ = scanned
    return doc


def write_report(target_date: date, items: list[ReportItem], scanned: int) -> Path:
    path = Path(REPORTS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    out = path / f"report_{target_date.isoformat()}.docx"
    doc = build_docx(target_date, items, scanned)
    doc.save(out)
    return out
