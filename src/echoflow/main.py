"""
Echoflow CLI - Main Entry Point
视频转文字 + AI 总结的完整工作流
"""

import os
import typer
from pathlib import Path
from rich.console import Console

# 导入配置模块
from echoflow import config
from echoflow.config import set_language

# 导入核心模块 (注意：writer 必须更新以接收 output_dir)
from echoflow.downloader import download_audio
from echoflow.transcriber import transcribe_audio
from echoflow.summarizer import generate_summary
from echoflow.writer import save_markdown

# 初始化 Typer 应用和 Rich Console
app = typer.Typer(help="Echoflow CLI - 视频转文字 + AI 总结工具")
console = Console()

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
def main(url: str):
    """
    处理视频链接：下载音频 -> 语音转文字 -> AI 总结 -> 生成 Markdown 笔记。
    """
    # 检查配置
    if not config.load_config():
        console.print("[bold yellow]⚠️ 尚未配置 API Key 或 输出路径。[/bold yellow]")
        if typer.confirm("是否现在进行初始化?", default=True):
            config.init_config()
            config.load_config() # 重新加载
        else:
            console.print("[red]程序退出。请运行 `echoflow init`。[/red]")
            raise typer.Exit(code=1)

    # 获取配置中的输出路径
    output_dir = os.getenv("OUTPUT_DIR")

    try:
        # 1. 启动信息
        console.print(f"[bold cyan]Echoflow 启动[/bold cyan]")
        console.print(f"目标: [underline]{url}[/underline]")
        console.print(f"保存至: [dim]{output_dir}[/dim]")

        console.print("\n[bold cyan]正在解析视频链接并准备下载...[/bold cyan]")
        audio_path, subtitle_text, metadata = download_audio(url)

        console.print(f"[green]✓[/green] 下载完成: [bold]{metadata.get('title', 'Unknown')}[/bold]")

        if subtitle_text:
            transcript = subtitle_text
            console.print(
                f"[green]✓[/green] 发现自带字幕，直接提取文本 (提取字数: {len(transcript)}字)"
            )
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
        else:
            with console.status(
                "[bold blue]未发现字幕，正在连接 AI 语音转写服务...[/bold blue]"
            ):
                transcript = transcribe_audio(audio_path)
            console.print(f"[green]✓[/green] 语音转写完成 (生成字数: {len(transcript)}字)")
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)

        with console.status(
            "[bold purple]正在连接 DeepSeek 进行深度思考与总结...[/bold purple]"
        ):
            description, content = generate_summary(transcript)
            ai_data = {"description": description, "content": content}
        console.print(
            f"[green]✓[/green] AI 总结完成 (生成字数: {len(ai_data.get('content', ''))}字)"
        )

        console.print("[bold yellow]正在排版并保存至 Obsidian 目录...[/bold yellow]")
        final_path = save_markdown(metadata, description, content, output_dir=output_dir)

        # --- 结束 ---
        console.print(f"\n[bold green]✓ 全部完成！[/bold green]")
        abs_path = Path(final_path).absolute()
        console.print(f"文件路径: [link=file://{abs_path}]{final_path}[/link]")

    except Exception as e:
        console.print(f"\n[bold red]❌ 运行失败: {str(e)}[/bold red]")
        console.print("[dim]提示: 请检查网络连接、视频链接是否有效，或 API 余额是否充足。[/dim]")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()