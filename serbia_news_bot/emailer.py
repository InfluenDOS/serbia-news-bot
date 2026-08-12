"""每日专报邮件发送（SMTP / Resend）。"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

import requests

from . import config

logger = logging.getLogger(__name__)


def _mail_configured() -> bool:
    if not config.REPORT_TO_EMAIL:
        return False
    if config.RESEND_API_KEY:
        return True
    if config.SMTP_USER and config.SMTP_PASSWORD:
        return True
    return False


def _send_via_resend(subject: str, body: str, report_path: Path) -> None:
    from_addr = config.REPORT_FROM_EMAIL or "serbia-news-bot@resend.dev"
    payload = {
        "from": from_addr,
        "to": [addr.strip() for addr in config.REPORT_TO_EMAIL.split(",") if addr.strip()],
        "subject": subject,
        "text": body,
    }
    # Resend 附件可选；正文已含全文，先不传附件以降低依赖
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {config.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Resend 失败 HTTP {resp.status_code}: {resp.text[:300]}")


def _send_via_smtp(subject: str, body: str, report_path: Path) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.REPORT_FROM_EMAIL or config.SMTP_USER
    msg["To"] = config.REPORT_TO_EMAIL
    msg.set_content(body)

    suffix = report_path.suffix.lower()
    if suffix == ".docx":
        maintype, subtype = (
            "application",
            "vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    else:
        maintype, subtype = "text", "plain"

    msg.add_attachment(
        report_path.read_bytes(),
        maintype=maintype,
        subtype=subtype,
        filename=report_path.name,
    )

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)


def send_report_email(report_path: Path, *, kept: int, scanned: int) -> bool:
    """发送报告邮件。未配置发信凭证时跳过并返回 False。"""
    if not _mail_configured():
        logger.info(
            "未配置发信凭证，跳过邮件（需要 RESEND_API_KEY 或 SMTP_USER+SMTP_PASSWORD；收件人=%s）",
            config.REPORT_TO_EMAIL or "(未设置 REPORT_TO_EMAIL)",
        )
        return False

    subject = f"塞尔维亚在野党专报 {report_path.stem.replace('report_', '')}（收录 {kept} 篇）"
    body = (
        f"监测完成。\n"
        f"候选扫描: {scanned} 篇\n"
        f"收录: {kept} 篇\n"
        f"完整报告请查看附件 Word 文档：{report_path.name}\n"
    )

    try:
        if config.RESEND_API_KEY:
            _send_via_resend(subject, body, report_path)
            logger.info("已通过 Resend 发送至 %s", config.REPORT_TO_EMAIL)
        else:
            _send_via_smtp(subject, body, report_path)
            logger.info("已通过 SMTP 发送至 %s", config.REPORT_TO_EMAIL)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("发送邮件失败: %s", exc)
        return False
