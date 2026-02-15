"""
Echoflow CLI - Markdown Writer Module
生成带 YAML Frontmatter 的 Obsidian 格式 Markdown 文件
"""

import os
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 加载环境变量 (作为后备)
load_dotenv()


def save_markdown(metadata: dict, description: str, content: str, output_dir: str = None) -> str:
    """
    保存 Markdown 文件到指定目录,带有 Obsidian 风格的 YAML Frontmatter
    
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
        
        # 构建 YAML Frontmatter
        frontmatter = build_frontmatter(metadata, description)
        
        # 拼接完整文件内容
        full_content = f"{frontmatter}\n\n# {title}\n\n{content}"
        
        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_content)
        
        # 这里 print 可以保留用于调试，也可以让 main 去统一输出
        # print(f"✓ Markdown 文件已保存: {filepath.name}")
        
        return str(filepath.absolute())
    
    except Exception as e:
        print(f"✗ 保存文件失败: {e}")
        raise Exception(f"保存 Markdown 文件失败: {e}")


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


def build_frontmatter(metadata: dict, description: str) -> str:
    """构建 YAML Frontmatter"""
    title = metadata.get('title', 'Untitled')
    # 处理 title 中的双引号，防止 YAML 格式错误
    title = title.replace('"', '\\"')
    
    author = metadata.get('author', 'Unknown')
    url = metadata.get('url', '')
    published = metadata.get('upload_date', datetime.now().strftime('%Y-%m-%d')) # yt-dlp 通常用 upload_date
    tags = metadata.get('tags', [])
    if not tags:
        tags = ['clippings', 'echoflow']
    
    # 额外字段
    platform = metadata.get('extractor', 'unknown') # yt-dlp 字段为 extractor
    duration = metadata.get('duration', 0)
    
    # 格式化标签列表 (简单的处理，实际可能需要更复杂的转义)
    tags_str = ', '.join([f'"{t}"' for t in tags])
    
    frontmatter = f"""---
title: "{title}"
source: "{url}"
author: "[[{author}]]"
published: {published}
created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
description: "{description}"
platform: {platform}
duration: {duration}
tags: [{tags_str}]
---"""
    
    return frontmatter
