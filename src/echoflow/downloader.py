"""
Echoflow CLI - Audio Downloader Module (Temp/Cache Version)
使用 yt-dlp 下载音频至系统临时目录，支持原生进度显示
"""

import os
import tempfile
import yt_dlp
from datetime import datetime
from pathlib import Path

def download_audio(url: str) -> tuple[str, dict]:
    """
    下载音频到系统临时缓存目录，并返回路径和元数据。
    
    Args:
        url: 视频/音频链接
        
    Returns:
        tuple: (final_filepath, metadata)
            - final_filepath (str): 下载并转换后的音频文件绝对路径 (.mp3)
            - metadata (dict): 包含 title, author, source_domain 等信息的字典
            
    Raises:
        Exception: 下载失败或处理出错
    """
    # 1. 获取系统临时目录并创建 echoflow 专用缓存文件夹
    # macOS/Linux: usually /tmp/echoflow_cache or /var/folders/...
    # Windows: %TEMP%\echoflow_cache
    temp_dir = Path(tempfile.gettempdir()) / "echoflow_cache"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. yt-dlp 配置
    ydl_opts = {
        'format': 'bestaudio/best',
        # 使用临时目录路径
        'outtmpl': str(temp_dir / '%(id)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        # 关键修改：关闭静默模式，允许 yt-dlp 输出原生进度条
        'quiet': True,
        'no_warnings': True,
        'noprogress': False, 
    }

    try:
        # print(f"正在下载至缓存: {temp_dir} ...") # 调试用，实际可省略
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 提取信息并下载
            # download=True 会直接开始下载，并打印进度到控制台
            info = ydl.extract_info(url, download=True)
            
            # 获取原始文件名并推导最终 MP3 文件名
            # 注意：prepare_filename 返回的是转换前的扩展名（如 .webm），我们需要 .mp3
            filename = ydl.prepare_filename(info)
            final_filepath = Path(filename).with_suffix('.mp3')
            
            # 提取元数据
            metadata = extract_metadata(info, url)
            
            # 返回绝对路径，供 main.py 使用和删除
            return str(final_filepath.absolute()), metadata

    except Exception as e:
        # print(f"✗ 下载失败: {e}") # main.py 会捕获这个异常，这里可以不再打印
        raise Exception(f"音频下载失败: {e}")


def extract_metadata(info: dict, original_url: str) -> dict:
    """
    提取并构建元数据字典
    
    Args:
        info: yt-dlp 返回的信息字典
        original_url: 原始请求 URL
        
    Returns:
        dict: 结构化的元数据
    """
    metadata = {
        'title': info.get('title', 'Untitled'),
        'author': info.get('uploader') or info.get('uploader_id') or "Unknown",
        'url': info.get('webpage_url', original_url),
        'published': format_date(info.get('upload_date')),
        'source_domain': get_source_domain(info.get('webpage_url', original_url)),
        'duration': info.get('duration'),
        'tags': info.get('tags', [])
    }
    return metadata


def get_source_domain(url: str) -> str:
    """
    根据 URL 判断来源域名
    """
    if "bilibili.com" in url:
        return "bilibili"
    elif "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    return "web"


def format_date(date_str: str) -> str:
    """
    格式化日期字符串 (YYYYMMDD -> YYYY-MM-DD)
    """
    if date_str and len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return datetime.now().strftime("%Y-%m-%d")


if __name__ == "__main__":
    # 简单的模块测试
    print("=" * 60)
    print("测试 Audio Downloader (Cache Mode)")
    print("=" * 60)
    
    test_url = "https://www.bilibili.com/video/BV1uT4y1P7CX" # 示例
    
    try:
        path, meta = download_audio(test_url)
        print("\n测试成功！")
        print(f"临时文件路径: {path}")
        print(f"元数据: {meta['title']}")
        
        # 模拟 main.py 的清理操作
        import time
        print("等待 3 秒后模拟清理...")
        time.sleep(3)
        if os.path.exists(path):
            os.remove(path)
            print("缓存文件已删除。")
            
    except Exception as e:
        print(f"测试出错: {e}")