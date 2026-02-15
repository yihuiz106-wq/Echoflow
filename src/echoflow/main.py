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

@app.command(name="run", help="开始处理: 下载 -> 转录 -> 总结")
def main(url: str):
    """
    处理视频链接：下载音频 -> 语音转文字 -> AI 总结 -> 生成 Markdown 笔记。
    """
    # --- Step 0: 检查配置 ---
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

        # --- Step 1: 下载 ---
        console.print("\n[bold blue]Step 1: 下载音频[/bold blue]")
        audio_path, metadata = download_audio(url)
        console.print(f"[green]✓[/green] 下载完成: [bold]{metadata.get('title', 'Unknown')}[/bold]")

        # --- Step 2: 转录 ---
        console.print("\n[bold blue]Step 2: 语音转文字[/bold blue]")
        with console.status("[cyan]正在转录音频 (SiliconFlow)...[/cyan]", spinner="dots"):
            transcript = transcribe_audio(audio_path)
        console.print(f"[green]✓[/green] 转录完成 (字数: {len(transcript)})")
        
        if os.path.exists(audio_path):
            os.remove(audio_path)

        # --- Step 3: 总结 ---
        console.print("\n[bold blue]Step 3: AI 总结与改写[/bold blue]")
        with console.status("[purple]DeepSeek 正在思考 (R1)...[/purple]", spinner="dots"):
            description, content = generate_summary(transcript)    
        console.print(f"[green]✓[/green] AI 思考完成")

        # --- Step 4: 保存 ---
        console.print("\n[bold blue]Step 4: 保存文件[/bold blue]")
        
        # 关键修改：将 output_dir 传入 save_markdown
        # 注意：你需要同步修改 src/echoflow/writer.py 接受这个参数
        final_path = save_markdown(metadata, description, content, output_dir=output_dir)

        # --- 结束 ---
        console.print(f"\n[bold green]✓ 全部完成！[/bold green]")
        abs_path = Path(final_path).absolute()
        console.print(f"文件路径: [link=file://{abs_path}]{final_path}[/link]")

    except Exception as e:
        console.print(f"\n[bold red]❌ 发生错误: {e}[/bold red]")
        # console.print_exception() # 调试时打开
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()