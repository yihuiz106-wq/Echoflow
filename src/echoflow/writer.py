"""
Echoflow CLI - Markdown Writer Module
生成适合在 Typora 中直接阅读的 Markdown 文件
"""

import os
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from echoflow.config import CONFIG_PATH

# 优先加载用户配置，避免项目根目录里的旧 .env 抢占输出目录
load_dotenv(CONFIG_PATH, override=True)


def save_markdown(metadata: dict, description: str, content: str, output_dir: str = None) -> str:
    """
    保存 Markdown 文件到指定目录，输出更适合 Typora 阅读的文章结构
    
    Args:
        metadata: 视频元数据字典
        description: 一句话简介
        content: Markdown 正文内容
        output_dir: (新增) 指定输出目录，如果为 None 则读取环境变量或使用默认值
        
    Returns:
        str: 保存的文件完整路径
    """
    try:
        # --- 修改开始: 优先使用传入的 output_dir ---
        if output_dir:
            output_path = Path(output_dir)
        else:
            # 如果没有传入，再尝试读取环境变量
            env_dir = os.getenv("OUTPUT_DIR", "./output")
            output_path = Path(env_dir)
        # --- 修改结束 ---
        
        # 确保目录存在
        output_path.mkdir(parents=True, exist_ok=True)
        # print(f"输出目录: {output_path.absolute()}") # 这一行在 main 中已有提示，可以注释掉保持清爽
        
        # 生成安全的文件名
        title = metadata.get('title', 'Untitled')
        filename = sanitize_filename(title) + '.md'
        filepath = output_path / filename
        
        # 处理文件名冲突
        filepath = handle_filename_conflict(filepath)
        
        metadata_block = build_metadata_block(metadata, description)
        normalized_content = convert_abstract_section_to_callout(content.strip())
        full_content = f"# {title}\n\n{metadata_block}\n\n{normalized_content}"
        
        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_content)
        
        # 这里 print 可以保留用于调试，也可以让 main 去统一输出
        # print(f"✓ Markdown 文件已保存: {filepath.name}")
        
        return str(filepath.absolute())
    
    except Exception as e:
        print(f"✗ 保存文件失败: {e}")
        raise Exception(f"保存 Markdown 文件失败: {e}")


def save_transcript(metadata: dict, transcript: str, output_dir: str = None) -> str:
    """
    保存原始转录文本到指定目录，不做 AI 总结或二次加工。
    """
    try:
        if output_dir:
            output_path = Path(output_dir)
        else:
            env_dir = os.getenv("OUTPUT_DIR", "./output")
            output_path = Path(env_dir)

        output_path.mkdir(parents=True, exist_ok=True)

        title = metadata.get("title", "Untitled")
        filename = sanitize_filename(f"{title}_transcript") + ".txt"
        filepath = handle_filename_conflict(output_path / filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(transcript)

        return str(filepath.absolute())

    except Exception as e:
        print(f"✗ 保存转录文本失败: {e}")
        raise Exception(f"保存转录文本失败: {e}")


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """清理文件名,移除非法字符"""
    illegal_chars = r'[<>:"/\\|?*]'
    safe_name = re.sub(illegal_chars, '_', filename)
    safe_name = safe_name.strip('. ')
    if len(safe_name) > max_length:
        safe_name = safe_name[:max_length]
    if not safe_name:
        safe_name = f"echoflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return safe_name


def handle_filename_conflict(filepath: Path) -> Path:
    """处理文件名冲突,添加数字后缀"""
    if not filepath.exists():
        return filepath
    
    stem = filepath.stem
    suffix = filepath.suffix
    parent = filepath.parent
    
    counter = 1
    while True:
        new_filepath = parent / f"{stem}_{counter}{suffix}"
        if not new_filepath.exists():
            return new_filepath
        counter += 1


def build_metadata_block(metadata: dict, description: str) -> str:
    """构建适合 Typora 阅读的元信息区块"""
    author = metadata.get("author", "Unknown")
    url = metadata.get("url", "")
    published = metadata.get("published", datetime.now().strftime("%Y-%m-%d"))
    platform = metadata.get("source_domain", "unknown")
    duration = format_duration(metadata.get("duration"))
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"> 作者：{author}",
        f"> 发布日期：{published}",
        f"> 平台：{platform}",
        f"> 时长：{duration}",
        f"> 生成时间：{created}",
    ]

    if url:
        lines.append(f"> 链接：{url}")

    return "\n".join(lines)


def format_duration(duration: int | None) -> str:
    """把秒数格式化为更易读的时长文本"""
    if not duration or duration < 0:
        return "未知"

    hours, remainder = divmod(int(duration), 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def convert_abstract_section_to_callout(content: str) -> str:
    """
    将正文中首个“## 摘要 / ## Abstract”段落转换为 Typora 支持的原生 Markdown callout。
    如果模型已经直接输出了支持的 callout，则保持不变。
    """
    if not content:
        return content

    if re.search(r"^\s*>\s*\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", content, re.IGNORECASE | re.MULTILINE):
        return content

    # 捕获从“## 摘要/Abstract”到下一个二级标题前的内容
    pattern = re.compile(
        r"^\s*##\s*(摘要|Abstract)\s*\n+(.+?)(?=\n\s*##\s+|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        return content

    abstract_body = match.group(2).strip()
    if not abstract_body:
        return content

    callout_lines: list[str] = ["> [!NOTE]"]
    for line in abstract_body.splitlines():
        if line.strip():
            callout_lines.append(f"> {line.rstrip()}")
        else:
            callout_lines.append(">")

    if len(callout_lines) == 1:
        return content

    callout = "\n".join(callout_lines)
    start, end = match.span()
    replaced = content[:start].rstrip()
    tail = content[end:].lstrip()

    if replaced and tail:
        return f"{replaced}\n\n{callout}\n\n{tail}".strip()
    if replaced:
        return f"{replaced}\n\n{callout}".strip()
    if tail:
        return f"{callout}\n\n{tail}".strip()
    return callout
