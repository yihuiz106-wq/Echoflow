"""
Echoflow CLI - Main Entry Point
视频转文字 + AI 总结的完整工作流
"""

import os
from pathlib import Path

import typer
from rich.console import Console

# 导入配置模块
from echoflow import config
from echoflow.config import set_language

# 导入核心模块 (注意：writer 必须更新以接收 output_dir)
from echoflow.downloader import download_audio
from echoflow.transcriber import transcribe_audio
from echoflow.summarizer import generate_summary
from echoflow.writer import save_markdown, save_transcript

# 初始化 Typer 应用和 Rich Console
app = typer.Typer(help="Echoflow CLI - 视频转文字 + AI 总结工具")
console = Console()


def ensure_config(required_keys: tuple[str, ...], hint_command: str) -> None:
    if config.load_config(required_keys=required_keys):
        return

    console.print("[bold yellow]⚠️ 尚未完成当前命令所需配置。[/bold yellow]")
    if typer.confirm("是否现在进行初始化?", default=True):
        config.init_config()
        if config.load_config(required_keys=required_keys):
            return

    console.print(f"[red]程序退出。请先运行 `{hint_command}` 或补齐配置。[/red]")
    raise typer.Exit(code=1)


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
    audio_path = None

    try:
        audio_path, subtitle_text, metadata, transcript_source = download_audio(
            url,
            convert_audio=convert_audio,
        )

        if subtitle_text:
            console.print("[green]✓[/green] 字幕下载成功")
            return metadata, subtitle_text

        if transcript_source == "audio":
            console.print("[green]✓[/green] 音频下载成功")
        console.print("[bold cyan]正在上传音频到 SiliconFlow...[/bold cyan]")
        console.print(f"[dim]{Path(audio_path).name} · {format_file_size(audio_path)}[/dim]")
        transcript = transcribe_audio(audio_path)
        return metadata, transcript

    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

@app.command()
def init():
    """
    初始化 Echoflow 配置 (API Keys 和 保存路径)。
    """
    config.init_config()

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
        "output_dir": "OUTPUT_DIR"
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
                console.print(f"[dim]已自动创建目录: {final_value}[/dim]")
            except Exception as e:
                console.print(f"[bold red]无法创建目录: {e}[/bold red]")

    # 3. 写入配置文件，强制不加引号
    try:
        # 确保路径转换为字符串，并指定不使用引号模式
        set_key(str(config.CONFIG_PATH), env_key, final_value, quote_mode="never")
        
        console.print(f"✅ [bold green]配置已更新:[/bold green]")
        console.print(f"   [cyan]{env_key}[/cyan] = [white]{final_value}[/white]")
    except Exception as e:
        console.print(f"[bold red]写入失败: {e}[/bold red]")

@app.command("language")
def language(
    target_lang: str = typer.Argument(..., help="设置输出语言，例如 '中文' 或 'English'")
):
    """
    设置全局输出语言（无论文稿什么语言，最终笔记强制使用该语言输出）。
    """
    raw = (target_lang or "").strip()
    if not raw:
        console.print("[bold red]语言不能为空[/bold red]")
        raise typer.Exit(code=1)

    normalized = raw
    lower = raw.lower()
    if lower in {"英文", "en", "eng", "english"}:
        normalized = "English"
    elif lower in {"中文", "zh", "zh-cn", "zh-hans", "chinese", "cn"}:
        normalized = "中文"

    set_language(normalized)

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
        console.print("[bold cyan]Echoflow[/bold cyan]")

        metadata, transcript = fetch_transcript(url, convert_audio=not raw)

        with console.status(
            "[bold cyan]正在生成总结...[/bold cyan]"
        ):
            description, content = generate_summary(transcript)

        final_path = save_markdown(metadata, description, content, output_dir=output_dir)

        console.print(f"[bold green]✓ 已保存[/bold green] [link=file://{Path(final_path).absolute()}]{final_path}[/link]")

    except Exception as e:
        console.print(f"\n[bold red]❌ 运行失败: {str(e)}[/bold red]")
        console.print("[dim]提示: 请检查网络连接、视频链接是否有效，或 API 余额是否充足。[/dim]")
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
        console.print("[bold cyan]Echoflow Transcript[/bold cyan]")

        metadata, transcript = fetch_transcript(url, convert_audio=not raw)

        final_path = save_transcript(metadata, transcript, output_dir=output_dir)

        console.print(f"[bold green]✓ 已保存[/bold green] [link=file://{Path(final_path).absolute()}]{final_path}[/link]")

    except Exception as e:
        console.print(f"\n[bold red]❌ 运行失败: {str(e)}[/bold red]")
        console.print("[dim]提示: 请检查网络连接、视频链接是否有效，或 API 余额是否充足。[/dim]")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
