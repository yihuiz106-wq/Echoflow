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

# 优先加载用户配置，避免项目根目录里的旧 .env 抢占配置
load_dotenv(CONFIG_PATH, override=True)


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
        ValueError: 当 API Key 未配置或输入文本为空时
        Exception: API 调用失败
    """
    target_lang = os.getenv("OUTPUT_LANGUAGE", "中文")

    # 验证 API Key
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError(
            "未找到 DEEPSEEK_API_KEY 环境变量。\n"
            "请运行 `echoflow init`，或检查 ~/.echoflow_env 中的 DEEPSEEK_API_KEY"
        )
    
    # 验证输入文本
    if not text or text.strip() == "":
        raise ValueError("输入文本不能为空")
    
    try:
        # 初始化 OpenAI 客户端 (指向 DeepSeek 官方 API)
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        
        system_prompt = f"""
你是一位“知识问答类内容编辑”。你的任务是把视频转录文本改写成一篇结构清晰、可读性高的 Markdown 文稿。

无论输入文本是什么语言，你都必须强制使用 {target_lang} 输出。

请返回一个 JSON 对象，且只包含两个字段：
{{
  "description": "...",
  "content": "..."
}}

写作目标与风格：
1. 整体风格要清楚、自然、有信息密度，接近高质量知识博主的讲解文风。
2. 语气可以比学术写作更生动，但不能过度口语化，不要网络梗，不要夸张表达。
3. 严禁添加原文没有明确支持的新事实、比喻、类比、故事或案例。
4. 如果原文证据不足，宁可保守表达，也不要“脑补”。

内容保真要求：
1. 忠实保留原视频核心观点、推理链路和关键细节，不改变原意。
2. 删除口头禅、重复、寒暄和无效停顿，但保留对理解有价值的信息。
3. 对逻辑跳跃处进行整理与衔接，让读者不看视频也能理解。

结构与可读性要求：
1. `description` 写 60-120 字，概括主题、核心问题和结论。
2. `content` 必须先输出一个 Markdown callout 摘要块：
   第一行固定为 `> [!NOTE]`
   后续摘要正文的每一行都放在 callout 内，并以 `> ` 开头
   摘要块结束后，再进入正文
3. 不要再输出 `## 摘要` 或 `## Abstract` 这样的单独大标题。
4. 正文使用标准 Markdown 标题（`##` / `###`）组织。
5. 每段尽量短：建议 1-3 句，优先 2 句；避免大段连续文本。
6. 句子尽量短，减少长串并列和过多从句。
7. 段落之间必须空行，确保 Typora 阅读舒适。

输出协议要求：
1. 不要输出代码块包裹 JSON。
2. 不要输出 JSON 之外的任何解释性文字。
3. 不要输出 `<think>` 标签或推理过程。
""".strip()

        # 调用 DeepSeek V4 Pro API
        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.45,  # 更稳健，减少过度发挥
            max_tokens=4000   # 确保有足够空间输出完整内容
        )
        
        # 获取 AI 返回内容
        raw_content = response.choices[0].message.content
        
        if not raw_content or raw_content.strip() == "":
            raise Exception("AI 返回内容为空")
        
        # 移除 <think>...</think>（防止污染输出协议）
        processed_content = strip_think_tags(raw_content).strip()

        # 优先按 JSON 协议解析
        description, content = parse_json_description_content(processed_content)
        if not description or not content:
            # 兼容旧协议（DESCRIPTION: + Markdown）
            description, content = split_description_and_content(processed_content)
        
        return description, content
    
    except Exception as e:
        error_message = str(e)
        raise Exception(f"DeepSeek V4 Pro API 调用失败: {error_message}")


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
        raise ValueError("未找到 DEEPSEEK_API_KEY 环境变量")
    
    if not text or text.strip() == "":
        raise ValueError("输入文本不能为空")
    
    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        
        print(f"正在使用自定义 Prompt 生成内容...")
        
        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": custom_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.6,
            max_tokens=4000
        )
        
        raw_content = response.choices[0].message.content
        processed_content = process_deepseek_thinking(raw_content)
        
        # 分离 description 和 content
        description, content = split_description_and_content(processed_content)
        
        print(f"✓ 内容生成成功")
        return description, content
    
    except Exception as e:
        print(f"✗ 生成失败: {e}")
        raise


if __name__ == "__main__":
    # 测试代码
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python summarizer.py <转录文本文件路径>")
        print("或者: python summarizer.py --test (使用示例文本测试)")
        sys.exit(1)
    
    # 测试模式
    if sys.argv[1] == "--test":
        test_text = """
        大家好,今天我们来聊一聊人工智能的发展。嗯,首先呢,我想说的是,
        AI 技术在最近几年有了非常大的突破,特别是在大语言模型方面。
        像 GPT 系列、Claude 这些模型,它们能够理解和生成非常自然的文本。
        那么,这些技术会给我们的生活带来什么变化呢?我觉得主要有三个方面。
        第一个是工作效率的提升,比如说写代码、写文档这些事情,AI 都可以帮我们做。
        第二个是创造力的释放,艺术家可以用 AI 来辅助创作,程序员也可以更专注于创新。
        第三个呢,就是知识的普及,每个人都可以通过 AI 学习新的知识。
        当然了,AI 技术也有一些挑战,比如说伦理问题、隐私问题,这些都需要我们认真对待。
        """
        print("=" * 60)
        print("使用测试文本运行...")
        print("=" * 60)
        
        try:
            description, content = generate_summary(test_text)
            print("\n" + "=" * 60)
            print("生成的结果:")
            print("=" * 60)
            print(f"\n一句话简介:\n{description}")
            print(f"\nMarkdown 正文:\n{content}")
        except Exception as e:
            print(f"\n测试失败: {e}")
            sys.exit(1)
    
    # 文件模式
    else:
        text_file = sys.argv[1]
        try:
            with open(text_file, 'r', encoding='utf-8') as f:
                text = f.read()
            
            description, content = generate_summary(text)
            
            # 保存到输出文件
            output_file = text_file.replace('.txt', '_summary.md')
            full_output = f"简介: {description}\n\n{content}"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(full_output)
            
            print(f"\n✓ 总结已保存到: {output_file}")
            print("\n预览:")
            print("=" * 60)
            print(f"简介: {description}")
            print(f"\n{content[:300]}..." if len(content) > 300 else content)
            
        except FileNotFoundError:
            print(f"✗ 文件不存在: {text_file}")
            sys.exit(1)
        except Exception as e:
            print(f"\n处理失败: {e}")
            sys.exit(1)
