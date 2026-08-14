"""Kimi（Moonshot）：判定、使馆内政简报体摘要；译法校对仅在必要时调用。"""

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
_PAREN_NOTE = re.compile(r"（[^）]*）|\([^)]*\)")

# 零成本本地替换：常见错译 / 直译
_LOCAL_FIXES: tuple[tuple[str, str], ...] = (
    ("塞尔维亚进步党", "塞尔维亚前进党"),
    ("进步党", "前进党"),
    ("亚历山大·武西奇", "亚历山大·武契奇"),
    ("武西奇", "武契奇"),
)


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


def _clip_body(text: str, limit: int) -> str:
    """截断正文；尽量在段落/句号处断开，避免无意义超长输入。"""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    chunk = text[:limit]
    for sep in ("\n\n", "\n", "。", ".", "!", "?", "！", "？"):
        pos = chunk.rfind(sep)
        if pos >= int(limit * 0.6):
            return chunk[: pos + len(sep)].strip()
    return chunk.strip()


def _build_prompt(article: ParsedArticle, target_date: date) -> str:
    body = _clip_body(article.text, config.AI_BODY_CHARS)
    date_zh = f"{target_date.year}年{target_date.month}月{target_date.day}日"
    return f"""判定并按使馆内政简报体摘要。只输出 JSON。

监测日：{date_zh}（{target_date.isoformat()}）
目标：与前进党—武契奇执政同盟对立的政党/联盟/议员/领袖行动（声明、抗议、议会、结盟、竞选冲突等）。
收录须同时：①主内容属上述阵营；②事件发生在监测日当天（非旧闻回顾）；③非纯执政宣传/娱乐体育/无关国际琐闻。

写法（收录时）：
- title_zh：自制事件题（谁+做了什么），勿直译原标题，勿加「1.」编号。
- summary_zh：第三人称转述；首句写清主体、时间、动作；写入关键数字、机制、场合；不写记者、不写「据报道」、不评价。
- 中文为主。专名用新华译法，首次可在中文后括注拉丁，如耶莱娜·帕夫洛维奇（Jelena Pavlović）。政党缩写仅用中文后括号，如前进党（SNS）。勿在括号外写英文或西里尔字母。
- SNS=前进党（勿写进步党），Vučić=武契奇。summary_zh≤500字，1–2段。

输出：
{{"relevant":true/false,"reason":"一句中文","title_zh":"...或空","summary_zh":"...或空"}}

标题：{article.title}
来源：{article.source_name}
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


def _apply_local_fixes(text: str) -> str:
    for bad, good in _LOCAL_FIXES:
        text = text.replace(bad, good)
    return text


def _needs_ai_polish(title_zh: str, summary_zh: str) -> bool:
    """仅当本地无法修好时才二次调用模型。"""
    blob = f"{title_zh}\n{summary_zh}"
    if "进步党" in blob:
        return True
    # 括号外仍有拉丁/西里尔 → 需要模型收拾
    stripped = _PAREN_NOTE.sub("", blob)
    return bool(_LATIN_OR_CYRILLIC.search(stripped))


def polish_chinese(title_zh: str, summary_zh: str) -> tuple[str, str]:
    """二次校对：统一主流中文译法，去掉不必要的外文。"""
    client = _client()
    prompt = f"""校对使馆内政简报体：只改译法/外文/体例，不增删事实。标题须为自制事件题（勿像原标题直译）。正文第三人称；外文仅可在中文后括号。SNS→前进党（勿进步党）；Vučić→武契奇。≤500字。
只输出：{{"title_zh":"...","summary_zh":"..."}}

标题：{title_zh}
正文：{summary_zh}
"""
    text = _chat(
        client,
        "只输出合法 JSON，不要代码围栏。",
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
    return _apply_local_fixes(new_title), _apply_local_fixes(new_summary)


def evaluate_article(article: ParsedArticle, target_date: date) -> AIVerdict | None:
    """调用 Kimi 判定并摘要；仅在必要时做译法二次校对。"""
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
        text = _chat(
            _client(),
            "只输出合法 JSON，不要代码围栏。",
            _build_prompt(article, target_date),
        )
        verdict = _parse_verdict(text)
    except Exception as exc:  # noqa: BLE001
        logger.error("评估失败: %s", exc)
        return None

    if not verdict.relevant:
        return verdict

    verdict.title_zh = _apply_local_fixes(verdict.title_zh)
    verdict.summary_zh = _apply_local_fixes(verdict.summary_zh)

    if not _needs_ai_polish(verdict.title_zh, verdict.summary_zh):
        return verdict

    try:
        title_zh, summary_zh = polish_chinese(verdict.title_zh, verdict.summary_zh)
        verdict.title_zh = title_zh
        verdict.summary_zh = summary_zh
        logger.info("已二次校对译法: %s", title_zh[:40])
    except Exception as exc:  # noqa: BLE001
        logger.warning("译法校对失败，沿用初稿: %s", exc)

    return verdict
