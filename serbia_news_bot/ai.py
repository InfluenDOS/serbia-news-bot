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

# 零成本本地替换：常见错译 / 直译（长词优先）
_LOCAL_FIXES: tuple[tuple[str, str], ...] = (
    ("塞尔维亚进步党", "塞尔维亚前进党"),
    ("进步党（SNS）", "前进党（SNS）"),
    ("进步党", "前进党"),
    ("亚历山大·武西奇", "亚历山大·武契奇"),
    ("武西奇", "武契奇"),
    ("安娜·布尔纳比克", "安娜·布尔纳比奇"),
    ("安娜·布尔纳比茨", "安娜·布尔纳比奇"),
    ("德拉甘·迪拉斯", "德拉甘·吉拉斯"),
    ("德拉干·吉拉斯", "德拉甘·吉拉斯"),
    ("自由与公正党", "自由与正义党"),
)

# 摘要目标篇幅（汉字约计，含标点）
_SUMMARY_SOFT_MAX = 550

# 提示词中的标准译法备忘（模型核对用）
_NAME_GLOSSARY = """专名标准译法（须核对，勿自造）：
SNS=塞尔维亚前进党/前进党（严禁“进步党”）；SPS=塞尔维亚社会党；SRS=塞尔维亚激进党；
DS=民主党；SSP=自由与正义党；Narodna stranka=人民党；
Aleksandar Vučić=亚历山大·武契奇；Ana Brnabić=安娜·布尔纳比奇；
Miloš Vučević=米洛什·武切维奇；Đuro Macut/马楚特；Dragan Đilas=德拉甘·吉拉斯；
Marinika Tepić=玛丽妮卡·特皮奇；Zdravko Ponoš=兹德拉夫科·波诺什；
Miloš Jovanović=米洛什·约万诺维奇；学生封锁/学生名单保持中文表述。"""


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

写法（收录时，强制）：
- title_zh：一句概括标题（谁+做了什么），自制，勿直译原标题，勿编号。
- summary_zh：整合成**一个自然段**，约500字（建议400–520字，硬上限550字）。第三人称；首句写清主体、时间、动作；只保留关键事实（数字、机制、场合、结果）；意思重复、铺垫、记者评论、背景堆砌一律删掉。
- 人名、政党、机构等专名必须用中文标准译法；不确定时用最通行新华/外交译法。首次出现人名可在中文后括注拉丁一次，如耶莱娜·帕夫洛维奇（Jelena Pavlović）。政党缩写仅用中文后括号，如前进党（SNS）。括号外禁止英文或西里尔字母。
- {_NAME_GLOSSARY}
- 不写「据报道」「记者」「本文」；不评价、不抒情。

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
        if bad == good:
            continue
        text = text.replace(bad, good)
    return text


def _as_one_paragraph(text: str) -> str:
    """合并为单段，去掉多余空白。"""
    parts = [p.strip() for p in re.split(r"\n+", text or "") if p.strip()]
    if not parts:
        return ""
    chunks: list[str] = []
    for part in parts:
        if chunks and not chunks[-1].endswith(("。", "！", "？", "；", "…")):
            chunks[-1] = f"{chunks[-1]}。"
        chunks.append(part)
    joined = re.sub(r"[ \t]+", "", "".join(chunks))
    return re.sub(r"。{2,}", "。", joined).strip()


def _needs_ai_polish(title_zh: str, summary_zh: str) -> bool:
    """译法可疑、过长、或多段时，二次校对。"""
    blob = f"{title_zh}\n{summary_zh}"
    if "进步党" in blob:
        return True
    if len(summary_zh) > _SUMMARY_SOFT_MAX:
        return True
    if "\n" in summary_zh.strip():
        return True
    stripped = _PAREN_NOTE.sub("", blob)
    return bool(_LATIN_OR_CYRILLIC.search(stripped))


def polish_chinese(title_zh: str, summary_zh: str) -> tuple[str, str]:
    """二次校对：标准译法、去重压缩为约500字单段。"""
    client = _client()
    prompt = f"""校对专报条目：核实人名/机构译法；删掉意思重复与非关键信息；压成一个自然段约500字（400–520，上限550）；标题概括事件。不增造事实。外文仅可在中文后括号。SNS→前进党（严禁进步党）；Vučić→武契奇。
{_NAME_GLOSSARY}
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
    return _apply_local_fixes(new_title), _apply_local_fixes(_as_one_paragraph(new_summary))


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
    verdict.summary_zh = _as_one_paragraph(_apply_local_fixes(verdict.summary_zh))

    if not _needs_ai_polish(verdict.title_zh, verdict.summary_zh):
        return verdict

    try:
        title_zh, summary_zh = polish_chinese(verdict.title_zh, verdict.summary_zh)
        verdict.title_zh = title_zh
        verdict.summary_zh = _as_one_paragraph(summary_zh)
        logger.info("已二次校对译法: %s (%s字)", title_zh[:40], len(verdict.summary_zh))
    except Exception as exc:  # noqa: BLE001
        logger.warning("译法校对失败，沿用初稿: %s", exc)

    return verdict
