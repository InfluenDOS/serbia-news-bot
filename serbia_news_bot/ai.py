"""Gemini：判定是否与在野党/反执政阵营相关，并生成中文摘要。"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date

from . import config
from .article import ParsedArticle

logger = logging.getLogger(__name__)

try:
    import google.genai as genai
except ImportError:  # pragma: no cover
    from google import genai  # type: ignore


@dataclass
class AIVerdict:
    relevant: bool
    reason: str
    actors: list[str]
    summary_zh: str
    raw: str = ""


_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _client():
    if not config.GEMINI_API_KEY:
        raise RuntimeError("缺少环境变量 GEMINI_API_KEY")
    return genai.Client(api_key=config.GEMINI_API_KEY)


def _build_prompt(article: ParsedArticle, target_date: date) -> str:
    # 正文截断，控制 token
    body = article.text[:8000]
    return f"""你是巴尔干政治情报分析员。请阅读下面这篇新闻，严格按规则输出 JSON。

【监测目标】
关注塞尔维亚「在野党 / 反执政阵营」相关动态：
- 指与现执政党（以 SNS / 武契奇政府为核心的执政同盟）立场对立的政党、联盟、议员、领袖及其组织的政治行动；
- 包括声明、集会、抗议、议会动作、结盟、退党、竞选布局、与执政方的公开冲突等硬新闻；
- 不是只盯某一个反对派，而是所有对执政方构成政治对立面的党派与阵营。

【收录标准】（须同时大致满足）
1. 主要内容涉及上述在野/反执政阵营的人物、组织或行动（可同时提及执政方）；
2. 是接近监测日（{target_date.isoformat()}）的具体事件/声明/动作，而非纯历史回顾或空泛时评；
3. 排除：纯执政方宣传稿且无在野阵营实质内容；娱乐/体育；与塞尔维亚国内政治无关的国际琐闻。

【输出】只输出一个 JSON 对象，不要 Markdown 代码围栏，字段如下：
{{
  "relevant": true/false,
  "reason": "一句中文说明为何收录或拒绝",
  "actors": ["出现的在野相关人物或政党简称"],
  "summary_zh": "若 relevant=true：用中文写 300-700 字事实型摘要，含谁/何时/何地/做了什么/关键原话；若 false：空字符串"
}}

标题：{article.title}
来源：{article.source_name}
链接：{article.url}
发布日：{article.publish_date.isoformat() if article.publish_date else "未知"}
正文：
{body}
"""


def _parse_verdict(text: str) -> AIVerdict:
    raw = (text or "").strip()
    if not raw:
        return AIVerdict(False, "空响应", [], "", raw)

    match = _JSON_RE.search(raw)
    if not match:
        upper = raw.upper()
        if upper.startswith("SKIP") or "\"relevant\": false" in raw.lower():
            return AIVerdict(False, "非 JSON SKIP", [], "", raw)
        # 容错：模型直接写了摘要
        if len(raw) > 80 and "SKIP" not in upper:
            return AIVerdict(True, "非 JSON 摘要回退", [], raw, raw)
        return AIVerdict(False, "无法解析", [], "", raw)

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return AIVerdict(False, "JSON 解析失败", [], "", raw)

    relevant = bool(data.get("relevant"))
    reason = str(data.get("reason") or "").strip()
    actors = data.get("actors") or []
    if not isinstance(actors, list):
        actors = [str(actors)]
    actors = [str(a).strip() for a in actors if str(a).strip()]
    summary = str(data.get("summary_zh") or "").strip()
    if relevant and len(summary) < 40:
        return AIVerdict(False, "摘要过短，视为无效", actors, "", raw)
    return AIVerdict(relevant, reason, actors, summary if relevant else "", raw)


def evaluate_article(article: ParsedArticle, target_date: date) -> AIVerdict | None:
    """调用 Gemini；失败返回 None（调用方可选择跳过）。"""
    if config.DRY_RUN:
        return AIVerdict(
            relevant=article.hint_score > 0,
            reason="DRY_RUN：仅按关键词粗筛",
            actors=[],
            summary_zh=(
                f"（DRY_RUN）{article.title}\n\n{article.text[:500]}…"
                if article.hint_score > 0
                else ""
            ),
        )

    client = _client()
    prompt = _build_prompt(article, target_date)
    last_err: Exception | None = None

    for attempt in range(config.AI_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
            )
            text = getattr(response, "text", None) or ""
            return _parse_verdict(text)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            msg = str(exc)
            if "429" in msg or "503" in msg or "RESOURCE_EXHAUSTED" in msg:
                wait = (attempt + 1) * 30
                logger.warning("Gemini 限流/繁忙，%ss 后重试 (%s)", wait, exc)
                time.sleep(wait)
                continue
            logger.warning("Gemini 调用失败: %s", exc)
            break

    logger.error("Gemini 最终失败: %s", last_err)
    return None
