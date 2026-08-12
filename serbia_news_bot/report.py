"""报告生成（Word .docx）。"""

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


def _add_meta_line(doc: Document, label: str, value: str) -> None:
    p = doc.add_paragraph()
    run_label = p.add_run(f"{label}：")
    run_label.bold = True
    p.add_run(value)


def build_docx(target_date: date, items: list[ReportItem], scanned: int) -> Document:
    doc = Document()

    # 标题
    title = doc.add_heading(f"塞尔维亚在野党动态每日专报", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph(target_date.isoformat())
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if sub.runs:
        sub.runs[0].font.size = Pt(14)
        sub.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    doc.add_paragraph()
    _add_meta_line(doc, "监测日", target_date.isoformat())
    _add_meta_line(doc, "口径", "与现执政党立场对立的在野党派 / 反执政阵营硬新闻")
    _add_meta_line(doc, "候选文章扫描", f"{scanned} 篇")
    _add_meta_line(doc, "收录", f"{len(items)} 篇")
    doc.add_paragraph()

    if not items:
        doc.add_paragraph(
            f"今日（{target_date.isoformat()}）未收录符合口径的在野党相关硬新闻。"
        )
        return doc

    for idx, item in enumerate(items, start=1):
        art = item.article
        ver = item.verdict
        actors = "、".join(ver.actors) if ver.actors else "—"
        pub = art.publish_date.isoformat() if art.publish_date else "未知"

        doc.add_heading(f"{idx}. {art.title}", level=1)
        _add_meta_line(doc, "来源", art.source_name)
        _add_meta_line(doc, "发布日", pub)
        _add_meta_line(doc, "相关方", actors)

        link_p = doc.add_paragraph()
        link_p.add_run("原文：").bold = True
        link_run = link_p.add_run(art.url)
        link_run.font.color.rgb = RGBColor(0x05, 0x63, 0xC1)
        link_run.underline = True

        _add_meta_line(doc, "筛选说明", ver.reason)
        doc.add_paragraph()

        summary_heading = doc.add_paragraph()
        summary_heading.add_run("摘要").bold = True
        for para in ver.summary_zh.strip().split("\n"):
            if para.strip():
                doc.add_paragraph(para.strip())

        if idx < len(items):
            doc.add_paragraph("—" * 40)

    return doc


def write_report(target_date: date, items: list[ReportItem], scanned: int) -> Path:
    path = Path(REPORTS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    out = path / f"report_{target_date.isoformat()}.docx"
    doc = build_docx(target_date, items, scanned)
    doc.save(out)
    return out
