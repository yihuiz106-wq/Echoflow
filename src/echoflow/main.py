"""
Echoflow CLI - Main Entry Point
视频转文字 + AI 总结的完整工作流
"""

import os
import re
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# 导入配置模块
from echoflow import config
from echoflow.config import set_language
from echoflow.errors import (
    ConfigError,
    DownloadError,
    SummaryError,
    TranscriptionError,
    WriteError,
)

# 导入核心模块 (注意：writer 必须更新以接收 output_dir)
from echoflow.downloader import DownloadResult, download_audio
from echoflow.transcriber import transcribe_audio
from echoflow.summarizer import generate_summary, simplify_title
from echoflow.writer import save_markdown, save_transcript

# 初始化 Typer 应用和 Rich Console
app = typer.Typer(help="Echoflow CLI - 视频转文字 + AI 总结工具")
console = Console(highlight=False)

ACCENT = "cyan"


def print_header(title: str, subtitle: str | None = None) -> None:
    title_text = Text(title, style=f"bold {ACCENT}")
    if subtitle:
        title_text.append("\n")
        title_text.append(subtitle, style="dim")
    console.print(
        Panel.fit(
            title_text,
            border_style=ACCENT,
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def print_status(symbol: str, style: str, message: str) -> None:
    console.print(f"[bold {style}]{symbol}[/bold {style}] {message}")


def print_step(message: str) -> None:
    print_status("›", ACCENT, message)


def print_success(message: str) -> None:
    print_status("✓", "green", message)


def print_warning(message: str) -> None:
    print_status("!", "yellow", message)


def print_error(message: str) -> None:
    print_status("×", "red", message)


def print_key_value(label: str, value: str) -> None:
    console.print(f"  [dim]{label:<12}[/dim] [white]{value}[/white]")


def print_output_path(title: str, path: str) -> None:
    absolute_path = Path(path).absolute()
    body = Text()
    body.append("Saved to\n", style="dim")
    body.append(str(absolute_path), style=f"bold {ACCENT} link file://{absolute_path}")
    console.print(
        Panel.fit(
            body,
            title=title,
            title_align="left",
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def print_video_title(metadata: dict) -> None:
    title = (metadata or {}).get("title", "").strip()
    if title:
        print_key_value("Title", title)


def maybe_simplify_metadata_title(metadata: dict) -> dict:
    if not metadata:
        return metadata

    original_title = (metadata.get("title") or "").strip()
    if not original_title:
        return metadata

    simplified_title = simplify_title(original_title)
    if not simplified_title or simplified_title == original_title:
        return metadata

    updated = dict(metadata)
    updated["original_title"] = original_title
    updated["title"] = simplified_title

    print_key_value("Short title", simplified_title)
    return updated


def get_package_version(package_name: str) -> str:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "not installed"


def clean_terminal_text(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text or "").strip()


def is_bilibili_412_error(text: str) -> bool:
    normalized = (text or "").lower()
    return "[bilibili]" in normalized and (
        "412" in normalized or "precondition failed" in normalized
    )


def ensure_config(required_keys: tuple[str, ...], hint_command: str) -> None:
    if config.load_config(required_keys=required_keys):
        return

    print_warning("尚未完成当前命令所需配置。")
    if typer.confirm("是否现在进行初始化?", default=True):
        config.init_config()
        if config.load_config(required_keys=required_keys):
            return

    print_error(f"程序退出。请先运行 `{hint_command}` 或补齐配置。")
    raise typer.Exit(code=1)


def mask_config_value(env_key: str, value: str) -> str:
    if "API_KEY" not in env_key:
        return value
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def format_file_size(path: str) -> str:
    size = Path(path).stat().st_size
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    return f"{size / 1024:.2f} KB"


def fetch_transcript(url: str, *, convert_audio: bool = True) -> tuple[dict, str]:
    """
    下载视频并返回元数据与文本。
    优先使用现成字幕；没有字幕时再调用 ASR。
    """
    download_result: DownloadResult | None = None

    try:
        allow_audio_download = config.load_config(required_keys=("SILICONFLOW_API_KEY",))
        download_result = download_audio(
            url,
            convert_audio=convert_audio,
            allow_audio_download=allow_audio_download,
        )
        metadata = download_result.metadata

        print_video_title(metadata)
        metadata = maybe_simplify_metadata_title(metadata)

        if download_result.subtitle_text:
            print_success("已提取视频字幕")
            return metadata, download_result.subtitle_text

        if download_result.source == "audio":
            print_success("已下载音频")
        if not download_result.audio_path:
            raise TranscriptionError("未找到可用于转录的音频文件")
        if not Path(download_result.audio_path).exists():
            raise TranscriptionError(f"音频文件不存在: {download_result.audio_path}")
        print_step(
            f"上传音频到 SiliconFlow: {Path(download_result.audio_path).name} "
            f"· {format_file_size(download_result.audio_path)}"
        )
        transcript = transcribe_audio(download_result.audio_path)
        return metadata, transcript

    finally:
        if download_result:
            download_result.cleanup()


def format_cli_error(error: Exception) -> tuple[str, str]:
    error_text = clean_terminal_text(str(error))
    if isinstance(error, ConfigError):
        return error_text, "提示: 请运行 `echoflow init` 或使用 `echoflow config` 补齐配置。"
    if isinstance(error, DownloadError):
        if is_bilibili_412_error(error_text):
            return (
                error_text,
                "提示: 当前更像是 B 站风控或登录态问题。可先关闭浏览器后重试，"
                "或运行 `echoflow config cookie chrome` 指定从 Chrome 读取 Cookie。",
            )
        return error_text, "提示: 请检查网络连接、视频链接是否有效，或运行 `echoflow update-yt-dlp`。"
    if isinstance(error, TranscriptionError):
        return error_text, "提示: 请检查 SiliconFlow API Key、余额、网络连接或音频文件格式。"
    if isinstance(error, SummaryError):
        return error_text, "提示: 请检查 DeepSeek API Key、余额、网络连接，或稍后重试。"
    if isinstance(error, WriteError):
        return error_text, "提示: 请检查输出目录是否存在、可写，或文件名是否有效。"
    return error_text, "提示: 请检查网络连接、视频链接是否有效，或 API 余额是否充足。"


def print_cli_error(prefix: str, error: Exception) -> None:
    error_text, hint = format_cli_error(error)
    body = Text()
    body.append(error_text or "未知错误", style="bold red")
    body.append("\n")
    body.append(hint, style="dim")
    console.print(
        Panel.fit(
            body,
            title=prefix,
            title_align="left",
            border_style="red",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )

@app.command()
def init():
    """
    初始化 Echoflow 配置 (API Keys 和 保存路径)。
    """
    try:
        config.init_config()
    except ConfigError as e:
        print_cli_error("初始化失败", e)
        raise typer.Exit(code=1)

@app.command(name="config")
def config_update(
    key: str = typer.Argument(..., help="配置项名称 (支持缩写: sf, ds, dir)"),
    value: str = typer.Argument(..., help="新的配置值")
):
    """
    快速更新配置。
    用法示例: 
    echoflow config dir /Users/path/to/save
    echoflow config sf sk-xxxxxx
    """
    from dotenv import set_key
    
    # 1. 建立缩写映射
    key_map = {
        "sf": "SILICONFLOW_API_KEY",
        "ds": "DEEPSEEK_API_KEY",
        "dir": "OUTPUT_DIR",
        "output_dir": "OUTPUT_DIR",
        "cookie": "BILIBILI_COOKIES_FROM_BROWSER",
        "cookies": "BILIBILI_COOKIES_FROM_BROWSER",
        "bili_cookie": "BILIBILI_COOKIES_FROM_BROWSER",
        "bili_cookies": "BILIBILI_COOKIES_FROM_BROWSER",
    }
    
    # 转换 key 为标准的大写格式
    target_key = key.lower()
    env_key = key_map.get(target_key, key.upper())
    
    # 2. 如果是修改路径，进行智能清洗
    final_value = value
    if env_key == "OUTPUT_DIR":
        final_value = config.clean_path(value)
        # 顺便检查一下路径是否存在
        if not os.path.exists(final_value):
            try:
                os.makedirs(final_value, exist_ok=True)
                print_key_value("Created", final_value)
            except Exception as e:
                print_cli_error("配置失败", ConfigError(f"无法创建目录: {e}"))
                raise typer.Exit(code=1)

    # 3. 写入配置文件，强制不加引号
    try:
        config.ensure_config_file()
        # 确保路径转换为字符串，并指定不使用引号模式
        set_key(str(config.CONFIG_PATH), env_key, final_value, quote_mode="never")

        print_success("配置已更新")
        print_key_value(env_key, mask_config_value(env_key, final_value))
    except Exception as e:
        print_cli_error("配置失败", ConfigError(f"写入失败: {e}"))
        raise typer.Exit(code=1)

@app.command("language")
def language(
    target_lang: str = typer.Argument(..., help="设置输出语言，例如 '中文' 或 'English'")
):
    """
    设置全局输出语言（无论文稿什么语言，最终笔记强制使用该语言输出）。
    """
    raw = (target_lang or "").strip()
    if not raw:
        print_error("语言不能为空")
        raise typer.Exit(code=1)

    normalized = raw
    lower = raw.lower()
    if lower in {"英文", "en", "eng", "english"}:
        normalized = "English"
    elif lower in {"中文", "zh", "zh-cn", "zh-hans", "chinese", "cn"}:
        normalized = "中文"

    try:
        set_language(normalized)
    except ConfigError as e:
        print_cli_error("语言设置失败", e)
        raise typer.Exit(code=1)


@app.command("update-yt-dlp", help="更新当前虚拟环境里的 yt-dlp")
def update_yt_dlp():
    """
    更新当前 Python 环境中的 yt-dlp 包。
    """
    current_version = get_package_version("yt-dlp")
    print_header("Update yt-dlp", f"当前版本: {current_version}")
    print_key_value("Python", sys.executable)

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as e:
        print_error(f"无法启动更新命令: {e}")
        raise typer.Exit(code=1)

    if result.returncode != 0:
        error_text = (result.stderr or result.stdout or "").strip()
        print_cli_error("yt-dlp 更新失败", DownloadError(error_text or "pip install --upgrade yt-dlp failed"))
        raise typer.Exit(code=1)

    new_version = get_package_version("yt-dlp")
    print_success(f"yt-dlp 已更新到 {new_version}")
    output_text = (result.stdout or "").strip()
    if output_text:
        last_line = output_text.splitlines()[-1]
        print_key_value("pip", last_line)


def doctor_checks() -> list[tuple[str, bool, str]]:
    config.load_config(required_keys=())

    checks: list[tuple[str, bool, str]] = []
    python_ok = sys.version_info >= (3, 10)
    checks.append(("Python", python_ok, sys.version.split()[0]))

    for package in ("typer", "rich", "yt-dlp", "openai", "python-dotenv"):
        package_version = get_package_version(package)
        checks.append((package, package_version != "not installed", package_version))

    ffmpeg_path = shutil.which("ffmpeg")
    checks.append(("ffmpeg", bool(ffmpeg_path), ffmpeg_path or "not found"))

    checks.append(
        (
            "config file",
            config.CONFIG_PATH.exists(),
            str(config.CONFIG_PATH),
        )
    )

    for env_key in ("SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "OUTPUT_DIR"):
        value = os.getenv(env_key)
        checks.append((env_key, bool(value), "set" if value else "missing"))

    output_dir = os.getenv("OUTPUT_DIR")
    if output_dir:
        output_path = Path(output_dir)
        writable = output_path.exists() and os.access(output_path, os.W_OK)
        checks.append(("output writable", writable, str(output_path)))
    else:
        checks.append(("output writable", False, "OUTPUT_DIR missing"))

    return checks


def print_doctor_report(checks: list[tuple[str, bool, str]]) -> bool:
    table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style=f"bold {ACCENT}",
        pad_edge=False,
    )
    table.add_column("Status", width=8, no_wrap=True)
    table.add_column("Check", style="white", no_wrap=True)
    table.add_column("Detail", style="dim")

    failed = False
    for name, ok, detail in checks:
        if ok:
            table.add_row("[bold green]OK[/bold green]", name, detail)
        else:
            failed = True
            table.add_row("[bold yellow]WARN[/bold yellow]", name, detail)

    console.print(table)
    return failed


@app.command("doctor", help="检查本地环境与配置，不调用外部 API")
def doctor():
    print_header("Echoflow Doctor", "本地环境检查，不验证 API Key 有效性")
    failed = print_doctor_report(doctor_checks())

    if failed:
        raise typer.Exit(code=1)


@app.command(name="run", help="开始处理: 下载 -> 转录 -> 总结")
def main(
    url: str,
    raw: bool = typer.Option(False, "--raw", "--no-convert", help="跳过 mp3 转码，直接使用原始音频文件"),
):
    """
    处理视频链接：下载音频 -> 语音转文字 -> AI 总结 -> 生成 Markdown 笔记。
    """
    # 检查配置
    ensure_config(
        required_keys=("DEEPSEEK_API_KEY", "OUTPUT_DIR"),
        hint_command="echoflow init",
    )

    # 获取配置中的输出路径
    output_dir = os.getenv("OUTPUT_DIR")

    try:
        print_header("Echoflow", "下载、转录并整理视频内容")
        print_step("开始获取视频内容")

        metadata, transcript = fetch_transcript(url, convert_audio=not raw)

        with console.status(
            "[bold cyan]正在整理文稿...[/bold cyan]"
        ):
            description, content = generate_summary(transcript)

        final_path = save_markdown(metadata, description, content, output_dir=output_dir)

        print_success("文稿已保存")
        print_output_path("Markdown note", final_path)

    except Exception as e:
        print_cli_error("运行失败", e)
        raise typer.Exit(code=1)


@app.command(name="transcript", help="开始处理: 下载 -> 转录/提取字幕 -> 保存原始文本")
def transcript_only(
    url: str,
    raw: bool = typer.Option(False, "--raw", "--no-convert", help="跳过 mp3 转码，直接使用原始音频文件"),
):
    """
    处理视频链接：下载音频 -> 提取字幕或语音转写 -> 保存原始文本。
    """
    ensure_config(
        required_keys=("OUTPUT_DIR",),
        hint_command="echoflow init",
    )

    output_dir = os.getenv("OUTPUT_DIR")

    try:
        print_header("Echoflow Transcript", "下载并导出原始转录文本")
        print_step("开始获取视频内容")

        metadata, transcript = fetch_transcript(url, convert_audio=not raw)

        final_path = save_transcript(metadata, transcript, output_dir=output_dir)

        print_success("转录文本已保存")
        print_output_path("Transcript", final_path)

    except Exception as e:
        print_cli_error("运行失败", e)
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
