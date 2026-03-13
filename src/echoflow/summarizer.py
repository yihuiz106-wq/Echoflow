"""
Echoflow CLI - AI Summary & Rewrite Module
使用 DeepSeek Reasoner 模型 (通过 DeepSeek 官方 API) 进行智能总结与改写
"""

import os
import json
import re
from dotenv import load_dotenv
from openai import OpenAI

# 加载环境变量
load_dotenv()


def generate_summary(text: str) -> tuple[str, str]:
    """
    使用 DeepSeek Reasoner 模型对转录文本进行智能总结与改写
    生成 Obsidian 风格的 Markdown 笔记
    
    Args:
        text: 原始转录文本
        
    Returns:
        tuple: (description, content)
            - description (str): 一句话简介 (30-50字)
            - content (str): Obsidian 风格的 Markdown 正文
        
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
            "请在 .env 文件中配置: DEEPSEEK_API_KEY=你的API密钥"
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
        
        print(f"正在使用 DeepSeek Reasoner 生成总结...")
        print(f"输入文本长度: {len(text)} 字符")
        
        system_prompt = f"""
你是一个专业的视频内容分析与整理专家。无论用户提供的转录文稿是什么语言，你都必须**强制使用 {target_lang}** 来输出最终结果。

请阅读提供的视频转录文稿，并返回一段 JSON 格式的数据，包含 `description` 和 `content` 两个字段。

要求如下：
1. **description**: 一句话概括视频核心内容（用于属性标签）。
2. **content**: 完整的 Markdown 正文，必须严格遵守以下结构：
   - **总结块**: 开头必须使用 Obsidian Callout 语法 `> [!SUMMARY]+ 视频核心总结` 将总结框起来，包含视频的要点，描述这个视频在干什么。
   - **客观详述**: 将文稿转换成一篇可读性极高、逻辑清晰的文章。
   - **客观视角**: 从第三人称客观的角度来描述视频内容（例如“视频指出了...”、“作者展示了...”），不要使用“我”或第一人称口语。
   - **细节丰满**: 尽可能的包含足够多的细节！如果输入的文稿很长，生成的这篇详述文章也应该对应地写得非常长、非常详细。绝对不能只做简单敷衍的概括。
   - **格式要求**: 每次换行或分段时，**必须空一行**（即段落之间必须有两个换行符 `\\n\\n`）。
   - 不要包含 `<think>` 标签的内容。
""".strip()

        # 调用 DeepSeek Reasoner API
        response = client.chat.completions.create(
            model="deepseek-reasoner",  # DeepSeek 官方推理模型
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.6,  # 适中的创造性
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
        
        print(f"✓ 总结生成成功")
        print(f"  简介: {description[:50]}..." if len(description) > 50 else f"  简介: {description}")
        print(f"  正文长度: {len(content)} 字符")
        
        return description, content
    
    except Exception as e:
        error_message = str(e)
        print(f"✗ AI 总结失败: {error_message}")
        
        # 提供友好的错误提示
        if "api_key" in error_message.lower():
            print("提示: 请检查 DEEPSEEK_API_KEY 是否正确配置")
        elif "rate limit" in error_message.lower():
            print("提示: API 调用频率超限,请稍后重试")
        elif "context_length" in error_message.lower():
            print("提示: 输入文本过长,请尝试分段处理")
        
        raise Exception(f"DeepSeek Reasoner API 调用失败: {error_message}")


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
    try:
        obj = json.loads(s)
        return str(obj.get("description", "")).strip(), str(obj.get("content", "")).strip()
    except Exception:
        pass

    # 容错：尝试截取最外层 JSON 对象
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = s[start : end + 1]
        try:
            obj = json.loads(candidate)
            return str(obj.get("description", "")).strip(), str(obj.get("content", "")).strip()
        except Exception:
            return "", ""

    return "", ""


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
            if line.strip() and not line.strip().startswith('>') and not line.strip().startswith('#'):
                description = line.strip()[:100]  # 截取前100字符
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
            model="deepseek-reasoner",
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