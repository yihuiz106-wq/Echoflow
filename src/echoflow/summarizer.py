"""
Echoflow CLI - AI Summary & Rewrite Module
使用 DeepSeek V4 Pro 模型 (通过 DeepSeek 官方 API) 进行智能总结与改写
"""

import os
import json
import re
import ast
from dotenv import load_dotenv
from openai import OpenAI
from echoflow.config import CONFIG_PATH
from echoflow.errors import ConfigError, SummaryError
from echoflow.retry import call_with_retry

# 优先加载用户配置，避免项目根目录里的旧 .env 抢占配置
load_dotenv(CONFIG_PATH, override=True)

SUMMARY_TEMPERATURE = 0.45
SUMMARY_MAX_TOKENS = 4000


def generate_summary(text: str) -> tuple[str, str]:
    """
    使用 DeepSeek V4 Pro 模型对转录文本进行智能总结与改写
    生成偏论文式、适合在 Typora 中阅读的 Markdown 文稿
    
    Args:
        text: 原始转录文本
        
    Returns:
        tuple: (description, content)
            - description (str): 一句话简介 (30-50字)
            - content (str): Typora 友好的 Markdown 正文
        
    Raises:
        ConfigError: 当 API Key 未配置时
        SummaryError: 当输入文本为空或 API 调用失败时
    """
    target_lang = os.getenv("OUTPUT_LANGUAGE", "中文")

    # 验证 API Key
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ConfigError(
            "未找到 DEEPSEEK_API_KEY 环境变量。\n"
            "请运行 `echoflow init`，或检查 ~/.echoflow_env 中的 DEEPSEEK_API_KEY"
        )
    
    # 验证输入文本
    if not text or text.strip() == "":
        raise SummaryError("输入文本不能为空")
    
    try:
        # 初始化 OpenAI 客户端 (指向 DeepSeek 官方 API)
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        
        # 调用 DeepSeek V4 Pro API
        response = call_with_retry(
            lambda: client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=build_summary_messages(target_lang, text),
                temperature=SUMMARY_TEMPERATURE,
                max_tokens=SUMMARY_MAX_TOKENS,
            )
        )
        
        # 获取 AI 返回内容
        raw_content = response.choices[0].message.content
        
        if not raw_content or raw_content.strip() == "":
            raise SummaryError("AI 返回内容为空")
        
        return parse_summary_response(raw_content)
    
    except Exception as e:
        if isinstance(e, (ConfigError, SummaryError)):
            raise
        error_message = str(e)
        raise SummaryError(f"DeepSeek V4 Pro API 调用失败: {error_message}")


def build_summary_system_prompt(target_lang: str) -> str:
    return f"""
你是 Echoflow 的知识文稿编辑引擎。
目标：把可能含 ASR 错误的视频转录整理成 {target_lang} Markdown 文稿。
原则：忠实原意，不添加转录未支持的新事实。
纠错：根据上下文修正明显的语音识别错误、同音/近音词、断句和术语误识别。
边界：不可靠的纠错只做保守概括，不要把猜测写成确定事实。
风格：自然、清楚、有信息密度，删除口头填充和无效重复。
输出：仅返回 JSON 对象，包含 description 和 content 两个字段。
""".strip()


def build_summary_user_message(transcript: str) -> str:
    return f"""
请处理下面的转录文本。

输出约束：
- description: 60-120 字，概括主题、核心问题和结论。
- content: Markdown 正文，可使用 `##` / `###` 标题；不要输出顶层 `#` 标题。
- 只返回 JSON，不要代码块、解释文字或推理过程。

<transcript>
{transcript.strip()}
</transcript>
""".strip()


def build_summary_messages(target_lang: str, transcript: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": build_summary_system_prompt(target_lang)},
        {"role": "user", "content": build_summary_user_message(transcript)},
    ]


def parse_summary_response(raw_content: str) -> tuple[str, str]:
    processed_content = strip_think_tags(raw_content).strip()

    # 优先按 JSON 协议解析
    description, content = parse_json_description_content(processed_content)
    if description and content:
        return description, content

    # 兼容旧协议（DESCRIPTION: + Markdown）
    return split_description_and_content(processed_content)


def simplify_title(title: str, max_display_length: int = 44) -> str:
    """
    使用 DeepSeek 将过长的视频标题精简成更适合文件名和文档标题的版本。
    如果标题本身已经足够短，或未配置 API Key，则直接返回原标题。
    """
    original = (title or "").strip()
    if not original:
        return original

    if not title_needs_simplification(original, max_display_length=max_display_length):
        return original

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return original

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )

        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {
                    "role": "system",
                    "content": """
你是一位擅长压缩标题的信息编辑。

你的任务是把一个过长的视频标题压缩成更简洁、更适合文件名和文章标题的版本。

要求：
1. 必须保留原题最核心的主题信息，不要改写原意。
2. 删除冗余的口语化表达、夸张措辞、重复信息、过长的修饰语。
3. 如果原题里有人名、系列名、集数、前后缀宣传语，只保留对理解主题真正必要的部分。
4. 输出结果尽量自然，像一篇笔记的标题，而不是营销标题。
5. 不要加书名号、引号、emoji、括号补充说明。
6. 输出长度尽量控制在 12 到 28 个中文字符，或语义等价的简洁长度。
7. 只输出最终标题本身，不要解释，不要加序号，不要加引号。
""".strip(),
                },
                {"role": "user", "content": original},
            ],
            temperature=0.2,
            max_tokens=80,
        )

        simplified = strip_think_tags(response.choices[0].message.content or "").strip()
        simplified = simplified.strip().strip('"\'')
        simplified = re.sub(r"\s+", " ", simplified)
        simplified = re.sub(r"^[#*\-\d.\s]+", "", simplified).strip()

        if not simplified:
            return original

        if display_length(simplified) > max_display_length:
            return original

        return simplified

    except Exception:
        return original


def title_needs_simplification(title: str, max_display_length: int = 44) -> bool:
    return display_length(title) > max_display_length


def display_length(text: str) -> int:
    length = 0
    for ch in text:
        length += 1 if ch.isascii() else 2
    return length


def strip_think_tags(content: str) -> str:
    """
    移除 <think>...</think> 区块，避免返回内容混入推理过程。
    """
    think_pattern = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
    return think_pattern.sub("", content)


def parse_json_description_content(text: str) -> tuple[str, str]:
    """
    从模型返回中解析 JSON，提取 description/content。
    支持返回内容前后夹杂少量非 JSON 文本的情况。
    """
    s = text.strip()
    if not s:
        return "", ""

    candidates: list[str] = [s]

    # 兼容 ```json ... ``` 包裹
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        candidates.insert(0, fenced_match.group(1).strip())

    # 容错：尝试截取最外层 JSON 对象
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(s[start : end + 1])

    # 去重但保序
    deduped_candidates: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped_candidates:
            deduped_candidates.append(candidate)

    for candidate in deduped_candidates:
        # 1) 严格 JSON
        parsed = _parse_description_content_from_obj(candidate)
        if parsed != ("", ""):
            return parsed

        # 2) 轻度清洗后的 JSON（如尾逗号、智能引号）
        normalized = normalize_json_candidate(candidate)
        parsed = _parse_description_content_from_obj(normalized)
        if parsed != ("", ""):
            return parsed

        # 3) Python 字典风格容错
        parsed = _parse_description_content_from_python_dict(candidate)
        if parsed != ("", ""):
            return parsed

        parsed = _parse_description_content_from_python_dict(normalized)
        if parsed != ("", ""):
            return parsed

        # 4) 最后兜底：宽松正则提取
        parsed = extract_description_content_from_loose_json(candidate)
        if parsed != ("", ""):
            return parsed

        parsed = extract_description_content_from_loose_json(normalized)
        if parsed != ("", ""):
            return parsed

    return "", ""


def _parse_description_content_from_obj(payload: str) -> tuple[str, str]:
    try:
        obj = json.loads(payload)
    except Exception:
        return "", ""

    if not isinstance(obj, dict):
        return "", ""

    return str(obj.get("description", "")).strip(), str(obj.get("content", "")).strip()


def _parse_description_content_from_python_dict(payload: str) -> tuple[str, str]:
    try:
        obj = ast.literal_eval(payload)
    except Exception:
        return "", ""

    if not isinstance(obj, dict):
        return "", ""

    return str(obj.get("description", "")).strip(), str(obj.get("content", "")).strip()


def normalize_json_candidate(payload: str) -> str:
    s = payload.strip()
    if not s:
        return s

    # 智能引号转半角，减少解析失败
    s = (
        s.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
    )

    # 移除对象/数组前的尾逗号（JSON 常见错误）
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    return s


def extract_description_content_from_loose_json(payload: str) -> tuple[str, str]:
    description = extract_loose_value(payload, "description")
    content = extract_loose_value(payload, "content")
    return description, content


def extract_loose_value(text: str, key: str) -> str:
    key_pattern = re.compile(rf'["\']{re.escape(key)}["\']\s*:\s*', re.IGNORECASE)
    key_match = key_pattern.search(text)
    if not key_match:
        return ""

    i = key_match.end()
    length = len(text)
    while i < length and text[i].isspace():
        i += 1
    if i >= length:
        return ""

    # 支持字符串值（含转义）与非字符串值（兜底）
    if text[i] in {"'", '"'}:
        quote = text[i]
        i += 1
        buf: list[str] = []
        escaped = False
        while i < length:
            ch = text[i]
            if escaped:
                buf.append(ch)
                escaped = False
                i += 1
                continue
            if ch == "\\":
                escaped = True
                buf.append(ch)
                i += 1
                continue
            if ch == quote:
                break
            buf.append(ch)
            i += 1
        raw_value = "".join(buf)
    else:
        j = i
        while j < length and text[j] not in ",}":
            j += 1
        raw_value = text[i:j]

    return decode_loose_string(raw_value).strip()


def decode_loose_string(s: str) -> str:
    # 仅做最常见转义恢复，避免误伤中文
    return (
        s.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\'", "'")
    )


def split_description_and_content(text: str) -> tuple[str, str]:
    """
    从 AI 返回的文本中分离一句话简介和正文内容
    
    Args:
        text: AI 返回的完整文本
        
    Returns:
        tuple: (description, content)
    """
    lines = text.strip().split('\n')
    
    # 查找 DESCRIPTION: 开头的行
    description = ""
    content_start_index = 0
    
    for i, line in enumerate(lines):
        if line.strip().startswith("DESCRIPTION:"):
            description = line.replace("DESCRIPTION:", "").strip()
            content_start_index = i + 1
            break
    
    # 如果没有找到 DESCRIPTION 标记,使用第一段作为简介
    if not description:
        # 尝试从内容中提取第一个非空段落作为简介
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # 避免把 JSON 骨架误判为简介
            if stripped in {"{", "}"}:
                continue
            if stripped.startswith((">", "#", '"description"', '"content"', "'description'", "'content'")):
                continue
            if stripped.endswith((": {", ":")) and stripped.lower().startswith(("description", "content")):
                continue
            description = stripped[:100]  # 截取前100字符
            break
        
        if not description:
            description = "视频内容总结与分析"
        
        content_start_index = 0
    
    # 提取正文内容
    content = '\n'.join(lines[content_start_index:]).strip()
    
    return description, content


def process_deepseek_thinking(content: str) -> str:
    """
    处理 DeepSeek Reasoner 的思考过程标签
    将 <think>...</think> 转换为 Obsidian Callout 折叠块
    
    Args:
        content: 原始 AI 返回内容
        
    Returns:
        str: 处理后的 Markdown 内容
    """
    # 检查是否包含思考标签
    if "<think>" not in content.lower():
        return content
    
    # 使用正则表达式提取思考内容
    think_pattern = re.compile(r'<think>(.*?)</think>', re.DOTALL | re.IGNORECASE)
    
    def replace_think_tag(match):
        """替换函数: 将思考内容转换为 Obsidian Callout"""
        think_content = match.group(1).strip()
        
        # 将每一行添加 "> " 前缀
        lines = think_content.split('\n')
        callout_lines = ['> [!THOUGHT]- AI 深度思考过程']
        for line in lines:
            if line.strip():
                callout_lines.append(f"> {line}")
            else:
                callout_lines.append(">")
        
        return '\n'.join(callout_lines) + "\n\n"
    
    # 替换所有思考标签
    processed = think_pattern.sub(replace_think_tag, content)
    
    return processed.strip()


def generate_summary_with_custom_prompt(text: str, custom_prompt: str) -> tuple[str, str]:
    """
    使用自定义 Prompt 生成总结 (高级功能)
    
    Args:
        text: 原始转录文本
        custom_prompt: 用户自定义的 System Prompt
        
    Returns:
        tuple: (description, content)
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ConfigError("未找到 DEEPSEEK_API_KEY 环境变量")
    
    if not text or text.strip() == "":
        raise SummaryError("输入文本不能为空")
    
    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        
        response = call_with_retry(
            lambda: client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[
                    {"role": "system", "content": custom_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.6,
                max_tokens=4000,
            )
        )
        
        raw_content = response.choices[0].message.content
        processed_content = process_deepseek_thinking(raw_content)
        
        # 分离 description 和 content
        description, content = split_description_and_content(processed_content)
        
        return description, content
    
    except Exception as e:
        if isinstance(e, (ConfigError, SummaryError)):
            raise
        raise SummaryError(f"DeepSeek V4 Pro API 调用失败: {e}")
