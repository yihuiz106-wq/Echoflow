"""
Echoflow CLI - Audio Transcription Module
使用 SiliconFlow (硅基流动) 的 ASR 服务进行音频转文字
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from echoflow.config import CONFIG_PATH

# 优先加载用户配置，避免项目根目录里的旧 .env 抢占配置
load_dotenv(CONFIG_PATH, override=True)


def transcribe_audio(audio_path: str) -> str:
    """
    使用 SiliconFlow 的 FunAudioLLM/SenseVoiceSmall 模型进行音频转录
    
    Args:
        audio_path: 音频文件路径
        
    Returns:
        str: 转录后的文本内容
        
    Raises:
        ValueError: 当 API Key 未配置时
        FileNotFoundError: 当音频文件不存在时
        Exception: 其他 API 调用错误
    """
    # 验证 API Key
    api_key = os.getenv("SILICONFLOW_API_KEY")
    if not api_key:
        raise ValueError(
            "未找到 SILICONFLOW_API_KEY 环境变量。\n"
            "请运行 `echoflow init`，或检查 ~/.echoflow_env 中的 SILICONFLOW_API_KEY"
        )
    
    # 验证文件存在
    audio_file = Path(audio_path)
    if not audio_file.exists():
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")
    
    try:
        # 初始化 OpenAI 客户端 (指向 SiliconFlow 的兼容接口)
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.siliconflow.cn/v1"
        )

        # 打开音频文件并调用转录接口
        with open(audio_path, "rb") as audio_file_obj:
            response = client.audio.transcriptions.create(
                model="FunAudioLLM/SenseVoiceSmall",  # 多语言高精度模型
                file=audio_file_obj
            )
        
        # 提取转录文本
        transcription_text = response.text
        
        if not transcription_text or transcription_text.strip() == "":
            return ""

        return transcription_text
    
    except FileNotFoundError as e:
        raise
    
    except Exception as e:
        # 捕获所有其他错误 (API 调用失败、网络问题等)
        error_message = str(e)
        raise Exception(f"SiliconFlow API 调用失败: {error_message}")


if __name__ == "__main__":
    # 测试代码
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python transcriber.py <音频文件路径>")
        sys.exit(1)
    
    test_audio_path = sys.argv[1]
    try:
        result = transcribe_audio(test_audio_path)
        print("\n" + "="*50)
        print("转录结果:")
        print("="*50)
        print(result)
    except Exception as e:
        print(f"\n测试失败: {e}")
        sys.exit(1)
