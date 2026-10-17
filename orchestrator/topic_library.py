"""题库解析与有限补充消息的共享契约，不依赖 Web 或 Docker。"""
import json
import random
import re
from dataclasses import dataclass, replace
from pathlib import Path

MAX_FOLLOWUPS = 2
MAX_MESSAGE_CHARS = 8000

# 同时兼容旧中文标题与新英文标题，便于旧版材料回滚时继续解析。
_CAT_RE = re.compile(
    r"^##\s+(?:[一二三四五六七八九十百零\d]+、|\d+\.\s+)"
    r"(.+?)(?:（\d+\s*题）|\(\d+\s+topics?\))\s*$",
    re.IGNORECASE,
)
_ITEM_RE = re.compile(r"^-\s+\[[ x]\]\s+(\d+)\.\s+\*\*(.+?)\*\*[:：]?\s*(.*)$")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_HIGH_RISK_PHRASES = (
    "reverse engineering",
    "decompilation",
    "credential harvesting",
    "session hijacking",
    "fingerprint spoofing",
    "account farming",
    "automated registration",
    "model extraction",
    "knowledge distillation",
    "style imitation",
    "style transfer",
    "captcha bypass",
    "auto-booking",
    "auto-purchasing",
    "ticket grabbing",
    "class grabbing",
    "number grabbing",
    "sign-in scripts",
)
_UNNATURAL_PHRASES = (
    "queryer",
    "mutual conversion",
    "desensitization",
    "wrong question",
    "keynote book",
    "precipitate",
    "grayscale release",
    "online time",
    "operation and maintenance",
    "time consuming",
    "card replenishment",
    "variable occupancy",
    "screen recording occupancy",
    "automatic annotation",
    "configure hot update",
    "product promotion pipeline",
    "number taking",
    "enters the warehouse",
    "speech quality inspection",
    "big watermelon",
    "word-marking translation",
    "synonymously",
)

# 这是用户选择的题库范围，不把普通联网应用、文件遍历或课程练习当作排除主题。
_EXCLUDED_TOPIC_PATTERNS = (
    ("大模型相关", re.compile(r"\b(?:llms?|large language models?|large models?|chatgpt|gpt[- ]?\d*|claude|gemini|ollama|langchain|embeddings?|retrieval[- ]augmented|rag|generative ai|language model|chatbots?)\b", re.I)),
    ("逆向或反编译", re.compile(r"\b(?:reverse[- ]engineering|decompil\w*|disassembl\w*|binary analysis|malware)\b", re.I)),
    ("模型训练或微调", re.compile(
        r"\b(?:train(?:ing|ed)?|retrain(?:ing)?|fine[- ]?tun(?:e|ing))\b[^.\n]{0,100}\b(?:models?|llms?|neural)\b"
        r"|\b(?:models?|llms?|neural)\b[^.\n]{0,100}\b(?:train(?:ing|ed)?|retrain(?:ing)?|fine[- ]?tun(?:e|ing))\b", re.I)),
    ("网络协议、代理或扫描", re.compile(
        r"\b(?:dns|mdns|ssh|socks5?|tcp|udp|proxy|proxies|subnets?|packet capture|port forwarding)\b"
        r"|\b(?:lan|network|device|port)\s+(?:scanner|scanning|discovery|protocols?)\b"
        r"|\b(?:scan|scanning)\b[^.\n]{0,80}\b(?:network|ports?|hosts?|domains?)\b"
        r"|\b(?:http load test|webhook|header overwriter|https? certificate|tls certificate|certificate expiration|certificate transparency|cors|traffic switching)\b", re.I)),
    ("安全类", re.compile(
        r"\b(?:security|cybersecurity|vulnerabilit(?:y|ies)|phishing|fingerprint|password|encryption|encrypted|zero[- ]trust)\b"
        r"|\b(?:threat model|secrets? scanner|key leakage|key rotation|access token|two-factor|recovery code|cookie consent)\b", re.I)),
    ("生物或医疗", re.compile(
        r"\b(?:biolog\w*|genom\w*|dna|rna|proteins?|bacteria\w*|viruses?|molecul\w*|drugs?|medical|clinical|clinic|hospital|vaccine\w*|prescriptions?)\b"
        r"|\b(?:health record|health data|heart rate|plant care|pet foster)\b", re.I)),
)


_FOLLOWUP_RE = re.compile(r"^  - Follow-up ([12]): (.+)$")


@dataclass(frozen=True)
class Topic:
    """保存单题原始需求和递进补充。

    :param no: 稳定题号。
    :param title: 英文标题。
    :param description: 可独立交付的初始需求。
    :param category: 英文分类。
    :param followups: 按顺序执行的零至两条补充。
    """

    no: int
    title: str
    description: str
    category: str
    followups: tuple[str, ...] = ()


def validate_followups(value: object) -> list[str]:
    """校验有限英文业务消息，保留用户原文字节语义。

    :param value: 消息数组或元组。
    :return: 校验后的新列表；非法输入抛出 ValueError。
    """
    if not isinstance(value, (list, tuple)) or len(value) > MAX_FOLLOWUPS:
        raise ValueError("补充需求必须是最多两条的列表")
    messages = []
    for text in value:
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_MESSAGE_CHARS:
            raise ValueError("补充需求须为非空文本，且每条不超过 8000 字符")
        if _CJK_RE.search(text) or any((ord(c) < 32 and c not in "\n\t") or ord(c) == 127 for c in text):
            raise ValueError("补充需求须为英文且不能含终端控制字符")
        if text in messages:
            raise ValueError("同题补充需求不能重复")
        messages.append(text)
    return messages


def decode_followups(raw: str | None) -> list[str]:
    """解析旧记录兼容的消息快照，不吞掉损坏 JSON。

    :param raw: 数据库 JSON 字符串；None 仅用于旧记录。
    :return: 校验后的消息列表。
    """
    if raw is None:
        return []
    # JSON 转义最多占六字符；合法上限消息必须能在编码后原样解码。
    if not isinstance(raw, str) or len(raw) > MAX_MESSAGE_CHARS * MAX_FOLLOWUPS * 6 + 32:
        raise ValueError("补充需求快照格式无效或过大")
    try:
        value = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("补充需求快照 JSON 损坏") from exc
    return validate_followups(value)


def encode_followups(messages: object) -> str:
    """生成统一的消息快照表示。

    :param messages: 零至两条业务消息。
    :return: 规范 JSON 文本。
    """
    return json.dumps(validate_followups(messages), ensure_ascii=False, separators=(",", ":"))


def sample_followups(candidates: object) -> list[str]:
    """在新 run 创建时等概率选定候选前缀。

    :param candidates: 已冻结的消息候选。
    :return: 本次运行的消息正文；恢复路径禁止调用本函数。
    """
    messages = validate_followups(candidates)
    return messages[:random.randint(0, len(messages))] if messages else []


def sample_followup_timing(messages: list[str], timeout_sec: int, wrapup_sec: int) -> str:
    """为新运行一次性冻结投递时刻和兼容收尾预算。

    :param messages: 已抽取的补充正文。
    :param timeout_sec: 本次运行总预算秒数。
    :param wrapup_sec: 当前收尾设置，短预算时限制到投递窗口之后。
    :return: 可持久化的规范时间计划 JSON。
    """
    lower, upper = (timeout_sec + 9) // 10, timeout_sec * 6 // 10
    offsets = sorted(random.sample(range(lower, upper + 1), len(messages)))
    # 预留两秒轮询、末尾提交与秒级时钟取整的余量，短任务不能刚到点就被收尾抢先。
    wrapup = min(max(0, wrapup_sec), max(0, timeout_sec - upper - 5)) if messages else max(0, wrapup_sec)
    return json.dumps({'schema': 1, 'offsets_sec': offsets, 'timeout_sec': timeout_sec,
        'wrapup_sec': wrapup}, separators=(',', ':'))


def decode_followup_timing(raw: str | None, count: int) -> dict | None:
    """校验新时间快照，以 NULL 明确区分旧运行。

    :param raw: 原运行时间 JSON，历史记录为 None。
    :param count: 原冻结正文数。
    :return: 时间计划对象或旧模式的 None。
    """
    if raw is None:
        return None
    if not isinstance(raw, str) or len(raw) > 1024:
        raise ValueError('补充时间快照无效')
    value = json.loads(raw)
    if not isinstance(value, dict) or type(value.get('schema')) is not int or value['schema'] != 1:
        raise ValueError('补充时间快照版本无效')
    offsets, timeout, wrapup = value.get('offsets_sec'), value.get('timeout_sec'), value.get('wrapup_sec')
    if type(timeout) is not int or timeout < 1 or type(wrapup) is not int or wrapup < 0 \
            or not isinstance(offsets, list) or len(offsets) != count \
            or any(type(x) is not int or not (timeout + 9) // 10 <= x <= timeout * 6 // 10
                or x >= timeout - wrapup for x in offsets) \
            or offsets != sorted(set(offsets)):
        raise ValueError('补充时间快照预算或顺序无效')
    return value


def parse_topics(path: Path) -> list[Topic]:
    """解析新题库与无补充的历史 Markdown，拒绝孤立或错序子行。

    :param path: 题库文件。
    :return: 按文档顺序排列的题目。
    """
    topics = []
    category = ""
    current = None
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        heading = _CAT_RE.match(line)
        if heading:
            category = heading.group(1).strip()
            current = None
            continue
        item = _ITEM_RE.match(line)
        if item:
            no, title, description = item.groups()
            topics.append(Topic(int(no), title.strip(), description.strip(), category))
            current = len(topics) - 1
            continue
        followup = _FOLLOWUP_RE.match(line)
        if followup:
            if current is None or int(followup.group(1)) != len(topics[current].followups) + 1:
                raise ValueError(f"第 {line_no} 行补充需求孤立、重复或顺序错误")
            old = topics[current]
            messages = validate_followups((*old.followups, followup.group(2)))
            topics[current] = replace(old, followups=tuple(messages))
        elif "Follow-up" in line and line.lstrip().startswith("-"):
            raise ValueError(f"第 {line_no} 行补充需求格式错误")
        elif line.startswith("## "):
            current = None
    return topics


def validate_topics(topics: list[Topic], require_followups: bool = True) -> None:
    """
    校验完整英文题库的编号、分类、必填字段和安全短语。

    :param topics: 待校验的 topic 列表
    :param require_followups: 正式题库必须恰有两条，历史材料可显式关闭。
    :return: None
    """
    if not topics:
        raise SystemExit("题库为空，未解析到任何题目")
    numbers = [topic.no for topic in topics]
    duplicates = sorted({no for no in numbers if numbers.count(no) > 1})
    if duplicates:
        raise SystemExit(f"题目编号重复: {duplicates}")
    # 文档按分类排列而不是按编号排列，集合仍必须精确覆盖固定的 600 个编号。
    expected = set(range(1, 601))
    actual = set(numbers)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SystemExit(
            f"题目编号不完整: 期望 1..600 共 600 条，"
            f"实际 {len(actual)} 条；缺失 {missing[:10]}{'...' if len(missing) > 10 else ''}；"
            f"多余 {extra[:10]}{'...' if len(extra) > 10 else ''}"
        )
    missing_fields = [
        topic.no for topic in topics
        if not topic.title or not topic.description or not topic.category
    ]
    if missing_fields:
        raise SystemExit(f"题目字段缺失: {missing_fields}")
    categories = {topic.category for topic in topics}
    if len(categories) != 21:
        raise SystemExit(f"题目分类数量错误: 期望 21，实际 {len(categories)}")
    invalid_followups = []
    for topic in topics:
        try:
            validate_followups(topic.followups)
        except ValueError:
            invalid_followups.append(topic.no)
        if require_followups and len(topic.followups) != MAX_FOLLOWUPS:
            invalid_followups.append(topic.no)
    if invalid_followups:
        raise SystemExit(f"题目须有两条有效英文补充: {sorted(set(invalid_followups))[:20]}")
    cjk_fields = [
        topic.no for topic in topics
        if any(_CJK_RE.search(value) for value in (
            topic.title,
            topic.description,
            topic.category,
            *topic.followups,
        ))
    ]
    if cjk_fields:
        raise SystemExit(f"题目字段仍包含 CJK 字符: {cjk_fields[:20]}")
    risky = []
    for topic in topics:
        content = "\n".join((topic.category, topic.title, topic.description, *topic.followups)).casefold()
        matches = [phrase for phrase in _HIGH_RISK_PHRASES if phrase in content]
        if matches:
            risky.append((topic.no, matches))
    if risky:
        raise SystemExit(f"题目包含高风险目标短语: {risky[:20]}")
    excluded = []
    for topic in topics:
        content = "\n".join((topic.category, topic.title, topic.description, *topic.followups))
        matches = [name for name, pattern in _EXCLUDED_TOPIC_PATTERNS if pattern.search(content)]
        if matches:
            excluded.append((topic.no, matches))
    if excluded:
        raise SystemExit(f"题目包含用户排除的主题: {excluded[:20]}")
    unnatural = []
    for topic in topics:
        content = "\n".join((topic.category, topic.title, topic.description, *topic.followups)).casefold()
        matches = [phrase for phrase in _UNNATURAL_PHRASES if phrase in content]
        if matches:
            unnatural.append((topic.no, matches))
    if unnatural:
        raise SystemExit(f"题目包含已知机器直译短语: {unnatural[:20]}")
