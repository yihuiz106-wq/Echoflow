import os
import typer
from pathlib import Path
from dotenv import load_dotenv, set_key
from rich.console import Console
from rich.prompt import Prompt

console = Console()
CONFIG_PATH = Path.home() / ".echoflow_env"

def clean_path(path_str: str) -> str:
    if not path_str:
        return ""
    
    # 移除引号和首尾空格
    s = path_str.strip().strip("'\"")
    
    # 核心修复：如果路径包含 iCloud 且没有波浪号，自动补全它
    # macOS 拖拽有时会丢失这两个关键的 ~
    if "Mobile Documents" in s and "iCloud~md~obsidian" not in s:
        s = s.replace("iCloudmdobsidian", "iCloud~md~obsidian")
    
    # 移除所有反斜杠
    s = s.replace("\\", "")
    
    # 展开 ~ (如果是指代家目录的话)
    return os.path.expanduser(s)

def init_config():
    """
    初始化配置并写入文件
    """
    console.rule("[bold blue]Echoflow 初始化配置[/bold blue]")
    
    silicon_key = Prompt.ask("🔑 SiliconFlow API Key")
    deepseek_key = Prompt.ask("🔑 DeepSeek API Key")
    
    console.print("📂 请拖入笔记保存文件夹:")
    raw_path = Prompt.ask("Path")
    output_dir = clean_path(raw_path)

    # 写入文件（set_key 默认逻辑就是 Key=Value，不带引号）
    CONFIG_PATH.touch(mode=0o600, exist_ok=True)
    
    # 注意：quote_mode="never" 确保写入时不加双引号
    set_key(str(CONFIG_PATH), "SILICONFLOW_API_KEY", silicon_key, quote_mode="never")
    set_key(str(CONFIG_PATH), "DEEPSEEK_API_KEY", deepseek_key, quote_mode="never")
    set_key(str(CONFIG_PATH), "OUTPUT_DIR", output_dir, quote_mode="never")
    set_key(str(CONFIG_PATH), "OUTPUT_LANGUAGE", "中文", quote_mode="never")
    
    console.print(f"\n✅ 配置已保存至: {CONFIG_PATH}")
    console.print(f"📝 最终路径: [bold cyan]{output_dir}[/bold cyan]")

def set_language(lang: str):
    """
    设置全局输出语言（最终笔记输出语言）
    """
    CONFIG_PATH.touch(mode=0o600, exist_ok=True)
    set_key(str(CONFIG_PATH), "OUTPUT_LANGUAGE", lang, quote_mode="never")
    console.print(f"✅ [bold green]输出语言已更新:[/bold green] [cyan]{lang}[/cyan]")

def load_config() -> bool:
    if not CONFIG_PATH.exists():
        return False
    # 加载时 python-dotenv 会自动处理带空格的路径
    load_dotenv(CONFIG_PATH)
    return all(os.getenv(k) for k in ["SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "OUTPUT_DIR"])