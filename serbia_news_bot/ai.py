"""Kimi（Moonshot）：判定、摘要、中文译法二次校对。"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date

from openai import OpenAI

from . import config
from .article import ParsedArticle

logger = logging.getLogger(__name__)


@dataclass
class AIVerdict:
    relevant: bool
    reason: str
    actors: list[str]
    title_zh: str
    summary_zh: str
    raw: str = ""


_JSON_RE = re.compile(r"\{[\s\S]*\}")
_LATIN_OR_CYRILLIC = re.compile(r"[A-Za-z\u0400-\u04FF]")


def _client() -> OpenAI:
    if not config.KIMI_API_KEY:
        raise RuntimeError("缺少环境变量 KIMI_API_KEY（或 MOONSHOT_API_KEY）")
    return OpenAI(api_key=config.KIMI_API_KEY, base_url=config.KIMI_BASE_URL)


def _chat(client: OpenAI, system: str, user: str) -> str:
    last_err: Exception | None = None
    for attempt in range(config.AI_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=config.KIMI_MODEL,
                temperature=1,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            msg = str(exc)
            if "429" in msg or "503" in msg or "rate" in msg.lower():
                wait = (attempt + 1) * 20
                logger.warning("Kimi 限流/繁忙，%ss 后重试 (%s)", wait, exc)
                time.sleep(wait)
                continue
            logger.warning("Kimi 调用失败: %s", exc)
            break
    raise RuntimeError(f"Kimi 最终失败: {last_err}")


def _build_prompt(article: ParsedArticle, target_date: date) -> str:
    body = article.text[:8000]
    date_zh = f"{target_date.year}年{target_date.month}月{target_date.day}日"
    return f"""你是巴尔干政治情报分析员。请阅读下面这篇新闻，严格按规则输出 JSON。

【监测目标】
关注塞尔维亚「在野党 / 反执政阵营」相关动态：
- 指与现执政党（以塞尔维亚前进党、武契奇政府为核心的执政同盟）立场对立的政党、联盟、议员、领袖及其组织的政治行动；
- 包括声明、集会、抗议、议会动作、结盟、退党、竞选布局、与执政方的公开冲突等硬新闻；
- 覆盖所有对执政方构成政治对立面的党派与阵营，而非单一反对派。

【收录标准】（须同时满足）
1. 主要内容涉及上述在野/反执政阵营的人物、组织或行动（可同时提及执政方）；
2. 所述具体事件/声明/动作发生在监测日当天（{date_zh} / {target_date.isoformat()}），不得收录仅发生在前一日或更早、当天只是转载/回顾的新闻；
3. 排除：纯执政方宣传且无在野实质内容；娱乐/体育；与塞尔维亚国内政治无关的国际琐闻。

【中文写作硬性要求】
1. title_zh 与 summary_zh 必须以中文为主，正文中不要出现英文单词或西里尔字母；
2. 若某专名确有必要保留英文缩写或原文，只能用中文后括号备注，例如：塞尔维亚前进党（SNS）；
3. summary_zh 控制在 500 个汉字以内；
4. 专名译法遵循新华社等主流中文媒体习惯，例如 SNS 译为「前进党」而非「进步党」。

【输出】只输出一个 JSON 对象，不要 Markdown 代码围栏：
{{
  "relevant": true/false,
  "reason": "一句中文说明为何收录或拒绝（可含日期判断）",
  "actors": ["相关人物或政党的中文名"],
  "title_zh": "若 relevant=true：一句中文标题；否则空字符串",
  "summary_zh": "若 relevant=true：中文正文摘要（≤500字）；否则空字符串"
}}

原标题：{article.title}
来源：{article.source_name}
链接：{article.url}
发布日：{article.publish_date.isoformat() if article.publish_date else "未知"}
正文：
{body}
"""


def _parse_verdict(text: str) -> AIVerdict:
    raw = (text or "").strip()
    if not raw:
        return AIVerdict(False, "空响应", [], "", "", raw)

    match = _JSON_RE.search(raw)
    if not match:
        upper = raw.upper()
        if upper.startswith("SKIP") or '"relevant": false' in raw.lower():
            return AIVerdict(False, "非 JSON SKIP", [], "", "", raw)
        return AIVerdict(False, "无法解析", [], "", "", raw)

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return AIVerdict(False, "JSON 解析失败", [], "", "", raw)

    relevant = bool(data.get("relevant"))
    reason = str(data.get("reason") or "").strip()
    actors = data.get("actors") or []
    if not isinstance(actors, list):
        actors = [str(actors)]
    actors = [str(a).strip() for a in actors if str(a).strip()]
    title_zh = str(data.get("title_zh") or "").strip()
    summary = str(data.get("summary_zh") or "").strip()
    if relevant and len(summary) < 20:
        return AIVerdict(False, "摘要过短，视为无效", actors, "", "", raw)
    if relevant and not title_zh:
        title_zh = summary[:30]
    return AIVerdict(
        relevant,
        reason,
        actors,
        title_zh if relevant else "",
        summary if relevant else "",
        raw,
    )


def polish_chinese(title_zh: str, summary_zh: str) -> tuple[str, str]:
    """二次校对：统一主流中文译法，去掉不必要的外文。"""
    client = _client()
    prompt = f"""你是中文时政编辑。请校对下面标题和正文，只做译法与用词修正，不增删事实。

【硬性规则】
1. 全文以中文为主；不要出现英文单词或西里尔字母。
2. 确需保留的专名缩写，只能写在中文后的括号内，例如：塞尔维亚前进党（SNS）。
3. 专名译法遵循新华社等主流中文媒体习惯，尤其注意：
   - SNS → 前进党（不要译成进步党）
   - Vučić / Vucic → 武契奇
   - 常见政党、地名、机构名用通用译名
4. 正文尽量控制在 500 个汉字以内；不要改变原意。
5. 只输出 JSON：{{"title_zh":"...","summary_zh":"..."}}

标题：{title_zh}
正文：{summary_zh}
"""
    text = _chat(
        client,
        "你只输出合法 JSON 对象，不要 Markdown 代码围栏，不要额外说明。",
        prompt,
    )
    match = _JSON_RE.search(text)
    if not match:
        return title_zh, summary_zh
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return title_zh, summary_zh
    new_title = str(data.get("title_zh") or title_zh).strip() or title_zh
    new_summary = str(data.get("summary_zh") or summary_zh).strip() or summary_zh
    return new_title, new_summary


def evaluate_article(article: ParsedArticle, target_date: date) -> AIVerdict | None:
    """调用 Kimi 判定并摘要；相关则再做译法校对。失败返回 None。"""
    if config.DRY_RUN:
        return AIVerdict(
            relevant=article.hint_score > 0,
            reason="DRY_RUN：仅按关键词粗筛",
            actors=[],
            title_zh=article.title if article.hint_score > 0 else "",
            summary_zh=(
                f"（DRY_RUN）{article.text[:400]}"
                if article.hint_score > 0
                else ""
            ),
        )

    try:
        client = _client()
        text = _chat(
            client,
            "你只输出合法 JSON 对象，不要 Markdown 代码围栏，不要额外说明。",
            _build_prompt(article, target_date),
        )
        verdict = _parse_verdict(text)
    except Exception as exc:  # noqa: BLE001
        logger.error("评估失败: %s", exc)
        return None

    if not verdict.relevant:
        return verdict

    try:
        title_zh, summary_zh = polish_chinese(verdict.title_zh, verdict.summary_zh)
        verdict.title_zh = title_zh
        verdict.summary_zh = summary_zh
        if _LATIN_OR_CYRILLIC.search(f"{title_zh}\n{summary_zh}"):
            # 再压一次，尽量去掉残留外文（括号内英文缩写仍可能保留）
            title_zh, summary_zh = polish_chinese(title_zh, summary_zh)
            verdict.title_zh = title_zh
            verdict.summary_zh = summary_zh
    except Exception as exc:  # noqa: BLE001
        logger.warning("译法校对失败，沿用初稿: %s", exc)

    return verdict
