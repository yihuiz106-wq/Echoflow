# EchoFlow

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![AI-Generated](https://img.shields.io/badge/Code_by-AI-FF69B4)
![Lazy-Dev](https://img.shields.io/badge/PyPI-Too_Troublesome-red)

> **视频转笔记，一行命令搞定。**
> *（注：本项目代码均由 AI 生成， 包括这个README文档，我只负责提需求和偷懒。）*

## 这是个啥？

EchoFlow 是一个为 **Obsidian 用户** 设计的命令行工具。

它可以把 Bilibili 或 YouTube 视频变成一篇格式完美的 Markdown 笔记，自动包含元数据、视频简介和 AI 总结。

### ⚠️ 极其“固执”的设计哲学 (必读)

为了保持代码极其简单（其实是我懒得写适配），本项目 **强制** 绑定了以下技术栈，**暂不支持配置其他模型**：

1.  **语音转文字 (ASR)**: 只能用 **SiliconFlow (硅基流动)** 的 API。
    * 默认模型：`FunAudioLLM/SenseVoiceSmall`
    * *原因：Gemini认为这个巨快，且这东西巨便宜。*
2.  **AI 总结 (LLM)**: 只能用 **DeepSeek (深度求索)** 的 API。
    * 默认模型：`deepseek-reasoner` (R1)
    * *原因：Deepseek可便宜，用reasoner是为了防止语音识别质量太差导致总结出一坨不知所云的东西*

## 📦 安装与配置

本项目基于 Python 3.10+。为了不污染你的系统环境，推荐使用虚拟环境安装。

### 1. 克隆与依赖安装

```bash
# 1. 下载代码
git clone [https://github.com/your-username/echoflow.git](https://github.com/your-username/echoflow.git)
cd echoflow

# 2. 创建并激活虚拟环境 (推荐)
python3 -m venv .venv
source .venv/bin/activate  # Windows 用户请使用: .venv\Scripts\activate

# 3. 安装依赖 (开发者模式)
pip install -e .

```

### 2. ⚡️ 让命令全局可用 (关键步骤)

默认情况下，你只能在激活虚拟环境后使用 `echoflow` 命令。
**如果你想在任何地方都能直接敲 `echoflow` 运行**，请将以下“魔法别名”添加到你的 Shell 配置文件（`.zshrc` 或 `.bashrc`）中：

```bash
# 打开你的配置文件 (以 zsh 为例)
nano ~/.zshrc

# 在文件末尾添加这一行 (请确保你当前在 echoflow 项目根目录下)
# 注意：把下面的 /path/to/echoflow 替换成你实际的 echoflow 目录路径
alias echoflow="/path/to/echoflow/.venv/bin/echoflow"

# 保存退出，然后让配置生效
source ~/.zshrc

```

> **极客小贴士**：
> 如果你懒得找路径，直接在 echoflow 项目根目录下运行这就行：
> `echo "alias echoflow=\"$PWD/.venv/bin/echoflow\"" >> ~/.zshrc && source ~/.zshrc`

## 🚀 极速上手

### 1. 初始化 (仅需一次)

```bash
echoflow init

```

*(程序会自动引导你配置 API Key)*

### 2. 验证安装

```bash
# 看看是不是装好了
which echoflow
# 输出类似: .../echoflow/.venv/bin/echoflow 即为成功
```

### 3. 开始剪藏

```bash
echoflow run "[https://www.bilibili.com/video/BV1xxxxxx](https://www.bilibili.com/video/BV1xxxxxx)"
```


🛠 常用命令
```bash
# 哪怕是本地安装，也可以全局调用
which echoflow

# 如果你换了电脑或者重装了 Obsidian，想改保存路径
echoflow config dir "/Users/me/New/Path"

# 看看帮助
echoflow --help
```

🤔 这个项目是怎么来的？
如开头所说，这是一个 AI 辅助编程 的实验产物。
我负责提出需求和“偷懒”，AI 负责写代码和解决 Bug。

如果你觉得代码写得烂……那请去怪 AI，不要怪我。🙈

---

Generated with ❤️ by Human & AI
