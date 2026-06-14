"""
Echoflow CLI - Audio Downloader Module (Temp/Cache Version)
使用 yt-dlp 下载音频至系统临时目录，并优先尝试下载字幕。

特性：
- Rich 真实下载进度条（不闪烁、不“阅后即焚”）
- 彻底屏蔽 yt-dlp 原生输出
- YouTube 字幕 429 自动降级：字幕失败不影响音频下载
"""

import glob
import io
import os
import re
import tempfile
from contextlib import redirect_stderr
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import yt_dlp
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)


class QuietYtDlpLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def is_bilibili_url(url: str) -> bool:
    return "bilibili.com" in (url or "")


def should_retry_with_browser_cookies(error_message: str, url: str) -> bool:
    normalized = (error_message or "").lower()
    return is_bilibili_url(url) and (
        "412" in normalized or "precondition failed" in normalized
    )


def get_browser_cookie_candidates() -> list[str]:
    configured = (
        os.getenv("BILIBILI_COOKIES_FROM_BROWSER")
        or os.getenv("ECHOFLOW_COOKIES_FROM_BROWSER")
        or ""
    ).strip()
    if configured:
        raw_candidates = [item.strip().lower() for item in configured.split(",")]
    else:
        raw_candidates = ["chrome", "safari", "edge", "firefox"]

    candidates: list[str] = []
    for candidate in raw_candidates:
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def clean_subtitle(file_path: str) -> str:
    """
    清洗 VTT/SRT 字幕文件，提取纯文本。
    - 移除时间戳行（如 00:00:00.000 --> 00:00:00.000）
    - 移除 HTML/XML 标签（如 <c.color>、</c>）
    - 移除单独数字行（SRT 序号）
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
    except Exception:
        return ""

    raw = raw.replace("\r\n", "\n").replace("\r", "\n")

    timestamp_re = re.compile(
        r"^\s*\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?\s*-->\s*\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?.*$"
    )
    index_re = re.compile(r"^\s*\d+\s*$")
    tag_re = re.compile(r"<[^>]+>")

    lines: list[str] = []
    for line in raw.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.upper() == "WEBVTT":
            continue
        if index_re.match(s):
            continue
        if timestamp_re.match(s):
            continue

        s = tag_re.sub("", s).strip()
        if not s:
            continue
        lines.append(s)

    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_video_url(raw: str) -> str:
    """
    规范化用户输入的链接，兼容常见分享格式：
    - Markdown 链接: [title](https://...)
    - 带文案的分享文本: xxx https://... yyy
    - 包裹符号: <https://...>、中文括号、中文引号
    - 未带 scheme 的 www 链接
    - 纯 BV / av / YouTube video id
    """
    if not raw or not raw.strip():
        raise ValueError("视频链接不能为空")

    s = raw.strip()
    s = s.replace("\\/", "/")
    s = re.sub(r"\\([?&=#])", r"\1", s)

    markdown_match = re.search(r"\[[^\]]*\]\((https?://[^)\s]+)\)", s, re.IGNORECASE)
    if markdown_match:
        s = markdown_match.group(1)
    else:
        url_match = re.search(r"(https?://[^\s<>\u3000]+|www\.[^\s<>\u3000]+)", s, re.IGNORECASE)
        if url_match:
            s = url_match.group(1)

    s = s.strip().strip("<>[](){}\"'“”‘’「」『』，。；！？、")
    if s.startswith("www."):
        s = f"https://{s}"

    # 兼容直接粘贴 BV / av / YouTube 视频 ID
    if re.fullmatch(r"BV[0-9A-Za-z]{10}", s):
        return f"https://www.bilibili.com/video/{s}"
    if re.fullmatch(r"av\d+", s, re.IGNORECASE):
        return f"https://www.bilibili.com/video/{s}"
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", s):
        return f"https://www.youtube.com/watch?v={s}"

    parsed = urlparse(s)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            "无法识别视频链接。请直接粘贴完整的 Bilibili / YouTube 链接，"
            "或使用 BV 号、av 号、YouTube 视频 ID。"
        )

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    filtered_query = []
    for key, value in query_pairs:
        if key.lower().startswith("utm_"):
            continue
        if key in {"si", "feature", "spm_id_from", "from_spmid"}:
            continue
        filtered_query.append((key, value))

    normalized_path = parsed.path.replace("\\", "")
    if normalized_path.endswith("/") and "/video/" in normalized_path:
        normalized_path = normalized_path.rstrip("/")

    return urlunparse(
        parsed._replace(
            path=normalized_path,
            query=urlencode(filtered_query, doseq=True),
        )
    )


def download_audio(
    url: str,
    *,
    convert_audio: bool = True,
) -> tuple[str | None, str | None, dict, str]:
    """
    下载音频到系统临时缓存目录，并尽可能下载/提取字幕文本。
    若字幕下载遇到 429 / Too Many Requests / subtitles 相关错误，将自动降级为纯音频下载。

    Returns:
        (audio_path, subtitle_text, metadata, transcript_source)
    """
    normalized_url = normalize_video_url(url)

    temp_dir = Path(tempfile.gettempdir()) / "echoflow_cache"
    temp_dir.mkdir(parents=True, exist_ok=True)

    console = Console()
    used_cookie_retry = False

    # 1) 分离配置：基础配置 + 字幕探测配置 + 音频下载配置
    common_opts: dict = {
        "outtmpl": str(temp_dir / "%(id)s.%(ext)s"),
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "no_color": True,
        "logger": QuietYtDlpLogger(),
    }

    subtitle_probe_opts: dict = {
        **common_opts,
        "download": False,
        "extract_flat": False,
    }

    subtitle_download_opts: dict = {
        **common_opts,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["zh-Hans", "zh-Hant", "zh-CN", "zh-TW", "zh", "en"],
        "subtitlesformat": "vtt/srt/best",
    }

    audio_opts: dict = {
        **common_opts,
        "format": "bestaudio/best",
    }
    if convert_audio:
        audio_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )
    task_id = progress.add_task("正在提取字幕...", total=None)

    def find_subtitle_text(base_filename: str) -> str | None:
        subtitle_text: str | None = None
        candidates = glob.glob(f"{base_filename}.*")
        subtitle_files = [p for p in candidates if p.lower().endswith((".vtt", ".srt"))]

        if subtitle_files:
            subtitle_files.sort(
                key=lambda p: (0 if p.lower().endswith(".vtt") else 1, len(p))
            )
            chosen = subtitle_files[0]
            cleaned = clean_subtitle(chosen)
            if cleaned:
                subtitle_text = cleaned

        for subtitle_file in subtitle_files:
            try:
                os.remove(subtitle_file)
            except Exception:
                pass

        return subtitle_text

    def run_download(
        opts: dict,
        *,
        show_progress: bool,
        should_download: bool = True,
    ) -> tuple[dict, str]:
        """
        所有下载相关阶段复用同一个 Progress，避免堆叠多条进度条。
        """
        def yt_dlp_monitor(d: dict):
            status = d.get("status")

            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes") or 0
                if total:
                    progress.update(task_id, description="正在下载音频...", total=total, completed=downloaded)
                else:
                    progress.update(task_id, description="正在下载音频...", completed=downloaded)

            elif status == "finished":
                progress.update(
                    task_id,
                    description="[bold green]下载完成，正在处理文件...[/bold green]",
                )

        def postprocessor_monitor(d: dict):
            postprocessor = d.get("postprocessor", "")
            status = d.get("status")
            if status == "started" and postprocessor == "ExtractAudio":
                progress.update(task_id, description="正在转换音频为 mp3...")

        def execute_download(ydl_opts: dict) -> tuple[dict, str]:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                with redirect_stderr(io.StringIO()):
                    info = ydl.extract_info(normalized_url, download=should_download)
                filename = ydl.prepare_filename(info)
            return info, filename

        ydl_opts = dict(opts)
        if show_progress:
            ydl_opts["progress_hooks"] = [yt_dlp_monitor]
        if convert_audio:
            ydl_opts["postprocessor_hooks"] = [postprocessor_monitor]

        try:
            return execute_download(ydl_opts)
        except Exception as first_error:
            nonlocal used_cookie_retry
            if not should_retry_with_browser_cookies(str(first_error), normalized_url):
                raise
            if ydl_opts.get("cookiesfrombrowser"):
                raise

            last_error = first_error
            for browser in get_browser_cookie_candidates():
                retry_opts = dict(ydl_opts)
                retry_opts["cookiesfrombrowser"] = (browser, None, None, None)
                try:
                    result = execute_download(retry_opts)
                    if not used_cookie_retry:
                        console.print(f"[yellow]已使用 {browser} 浏览器 Cookie 通过 B 站校验[/yellow]")
                        used_cookie_retry = True
                    return result
                except Exception as cookie_error:
                    last_error = cookie_error

            raise last_error

    def has_subtitle_tracks(info: dict) -> bool:
        subtitles = info.get("subtitles") or {}
        automatic_captions = info.get("automatic_captions") or {}
        preferred_langs = ("zh-Hans", "zh-Hant", "zh-CN", "zh-TW", "zh", "en")
        return any(lang in subtitles or lang in automatic_captions for lang in preferred_langs)

    with progress:
        # 2) 第一次尝试：先快速探测是否存在字幕轨道
        try:
            progress.update(task_id, description="正在提取字幕...", total=None, completed=0)
            info, filename = run_download(
                subtitle_probe_opts,
                show_progress=False,
                should_download=False,
            )
            metadata = extract_metadata(info, normalized_url)
            if has_subtitle_tracks(info):
                info, filename = run_download(
                    subtitle_download_opts,
                    show_progress=False,
                    should_download=True,
                )
                base_filename = os.path.splitext(filename)[0]
                subtitle_text = find_subtitle_text(base_filename)

                if subtitle_text:
                    progress.update(task_id, description="[bold green]字幕下载成功[/bold green]")
                    return None, subtitle_text, metadata, "subtitle"

        # 3) 字幕异常时静默降级到音频；无字幕本身属于正常情况
        except Exception as e:
            error_msg = str(e).lower()
            if ("429" in error_msg) or ("too many requests" in error_msg) or ("subtitles" in error_msg):
                console.print(
                    "\n[bold yellow]⚠️ 字幕获取失败，已自动降级：跳过字幕，采用纯音频+AI听写模式...[/bold yellow]"
                )

        # 4) 第二次尝试：只在确实没有可用字幕时下载音频
        progress.update(task_id, description="正在下载音频...", total=0, completed=0)
        info, filename = run_download(audio_opts, show_progress=True, should_download=True)
        final_filepath = Path(filename).with_suffix(".mp3") if convert_audio else Path(filename)
        metadata = extract_metadata(info, normalized_url)
        progress.update(task_id, description="[bold green]音频下载成功[/bold green]")
        return str(final_filepath.absolute()), None, metadata, "audio"


def extract_metadata(info: dict, original_url: str) -> dict:
    return {
        "title": info.get("title", "Untitled"),
        "author": info.get("uploader") or info.get("uploader_id") or "Unknown",
        "url": info.get("webpage_url", original_url),
        "published": format_date(info.get("upload_date")),
        "source_domain": get_source_domain(info.get("webpage_url", original_url)),
        "duration": info.get("duration"),
        "tags": info.get("tags", []),
    }


def get_source_domain(url: str) -> str:
    if "bilibili.com" in url:
        return "bilibili"
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    return "web"


def format_date(date_str: str) -> str:
    if date_str and len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return datetime.now().strftime("%Y-%m-%d")


if __name__ == "__main__":
    print("=" * 60)
    print("测试 Audio Downloader (Cache Mode)")
    print("=" * 60)

    test_url = "https://www.bilibili.com/video/BV1uT4y1P7CX"

    try:
        path, subtitle, meta, source = download_audio(test_url)
        print("\n测试成功！")
        print(f"临时文件路径: {path}")
        print(f"字幕提取: {'有' if subtitle else '无'}")
        print(f"转录来源: {source}")
        print(f"元数据: {meta['title']}")

        import time

        print("等待 3 秒后模拟清理...")
        time.sleep(3)
        if path and os.path.exists(path):
            os.remove(path)
            print("缓存文件已删除。")

    except Exception as e:
        print(f"测试出错: {e}")
