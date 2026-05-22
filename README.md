# Echoflow

`Echoflow` 是一个面向 `Typora` 工作流的命令行工具：给它一个 Bilibili 或 YouTube 链接，它会尽量先提取字幕；如果没有可用字幕，再下载音频做语音转录；最后可选择输出原始转录文本，或整理成一篇适合直接阅读的 Markdown 文稿。

当前版本的核心目标很明确：

- 把视频内容尽快变成可读、可存档的本地文件
- 优先复用平台现成字幕，减少转录成本和等待时间
- 输出结构对 `Typora` 友好，而不是为 Obsidian frontmatter 做优化
- 尽量保持命令简单，不把一堆模型和提供商配置暴露给用户

## 功能概览

- 支持 `Bilibili`、`YouTube` 以及常见分享链接格式
- 自动清洗链接，兼容 `BV` 号、`av` 号、YouTube 视频 ID
- 优先下载现成字幕；没有字幕时自动降级为音频转录
- 使用 `SiliconFlow` 的 `FunAudioLLM/SenseVoiceSmall` 做 ASR
- 使用 `DeepSeek V4 Pro` 把转录整理成 Markdown 文稿
- 摘要区域默认输出为 Typora 原生 `NOTE` alert
- 支持只导出原始转录文本，不做 AI 总结
- 支持配置输出语言，例如 `中文` 或 `English`
- 支持单独更新当前环境里的 `yt-dlp`

## 当前工作流

### `echoflow run`

完整流程：

1. 解析并清洗视频链接
2. 用 `yt-dlp` 探测字幕轨道
3. 如果有字幕，直接下载并清洗字幕文本
4. 如果没有可用字幕，下载音频并调用 `SiliconFlow` 做转录
5. 把文本交给 `DeepSeek` 生成结构化 Markdown
6. 保存为本地 `.md` 文件

生成的 Markdown 现在大致长这样：

```md
# 视频标题

> 作者：...
> 发布日期：...
> 平台：...
> 时长：...
> 生成时间：...
> 链接：https://...

> [!NOTE]
> 这里是摘要。

## 正文

正文内容……
```

### `echoflow transcript`

这个命令只负责：

1. 提取字幕，或下载音频后转录
2. 把原始文本保存为 `.txt`

它不会调用 `DeepSeek`，适合你只想拿到转录文本的时候用。

## 依赖与限制

项目目前是“固定服务提供商”设计，不支持在 CLI 里切换模型或供应商：

- 语音转录：`SiliconFlow`
- 文稿整理：`DeepSeek`

需要你自行准备：

- `SiliconFlow API Key`
- `DeepSeek API Key`
- 可写入的本地输出目录

系统要求：

- `Python 3.9+`
- 建议本机可用 `ffmpeg`

说明：

- 如果视频有字幕，通常不会走音频转录，所以对 `ffmpeg` 的依赖也更弱
- 如果需要把音频转成 `mp3`，或者平台返回的原始格式不适合直接处理，`ffmpeg` 会更稳

## 安装

建议使用虚拟环境：

```bash
git clone https://github.com/your-username/echoflow.git
cd echoflow

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
```

如果你移动过项目目录，导致虚拟环境里 `echoflow` 的 shebang 失效，可以在项目根目录重新执行一次：

```bash
.venv/bin/python -m pip install -e . --no-deps
```

## 初始化

第一次使用先运行：

```bash
echoflow init
```

它会引导你填写：

- `SiliconFlow API Key`
- `DeepSeek API Key`
- 输出目录

配置会保存到：

```bash
~/.echoflow_env
```

## 常用命令

### 生成 Markdown 文稿

```bash
echoflow run "https://www.bilibili.com/video/BV1xxxxxx"
```

### 只导出原始转录文本

```bash
echoflow transcript "https://www.youtube.com/watch?v=xxxxxx"
```

### 跳过 mp3 转码，直接使用原始音频

```bash
echoflow run --raw "https://www.youtube.com/watch?v=xxxxxx"
```

```bash
echoflow transcript --raw "https://www.bilibili.com/video/BV1xxxxxx"
```

### 修改配置

```bash
echoflow config dir "/Users/me/Documents/Notes"
echoflow config sf "your-siliconflow-key"
echoflow config ds "your-deepseek-key"
```

其中缩写对应关系是：

- `sf` -> `SILICONFLOW_API_KEY`
- `ds` -> `DEEPSEEK_API_KEY`
- `dir` -> `OUTPUT_DIR`

### 设置输出语言

```bash
echoflow language 中文
echoflow language English
```

这会影响最终 AI 整理后的笔记语言，不影响原始字幕或转录文本本身的语言。

### 更新 `yt-dlp`

```bash
echoflow update-yt-dlp
```

当平台规则变化、下载突然失败、或字幕提取行为异常时，这个命令通常值得先跑一次。

### 查看帮助

```bash
echoflow --help
```

## 链接输入兼容性

Echoflow 会尽量容忍“随手粘贴”的输入，例如：

- 完整视频链接
- Markdown 链接，如 `[标题](https://...)`
- 带文案的分享文本
- `BV` 号
- `av` 号
- YouTube 11 位视频 ID

它还会自动清理一部分追踪参数，例如常见的 `utm_*`。

## 输出文件说明

### Markdown 文稿

- 文件名默认使用视频标题
- 自动处理重名冲突
- 顶部附带作者、发布日期、平台、时长、生成时间和原始链接
- 摘要区使用 Typora 原生 `NOTE` alert

### 转录文本

- 文件名默认是 `视频标题_transcript.txt`
- 不做摘要，不做二次整理

## 常见问题

### 为什么有时候很快，有时候很慢？

因为它会先尝试拿字幕。

- 有字幕：通常很快
- 没字幕：需要下载音频并走 ASR，再交给 LLM 整理，整体耗时会明显增加

### 为什么 `transcript` 不需要 DeepSeek Key？

因为 `transcript` 只负责拿到原始文本并保存，不做总结。

### 为什么 `run` 有时仍然要求配置 SiliconFlow Key？

如果视频本身没有可用字幕，`run` 会回退到音频转录，这时就需要 `SiliconFlow API Key`。

### 输出目录可以后面再改吗？

可以：

```bash
echoflow config dir "/new/output/path"
```

## 开发说明

当前入口命令来自 `pyproject.toml` 中的脚本配置：

```toml
[project.scripts]
echoflow = "echoflow.main:app"
```

本地开发常用方式：

```bash
source .venv/bin/activate
pip install -e .
echoflow --help
```

如果你只是想直接调试模块，也可以：

```bash
PYTHONPATH=src .venv/bin/python -m echoflow.main --help
```
