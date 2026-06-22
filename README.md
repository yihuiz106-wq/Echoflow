# Echoflow

把 Bilibili 或 YouTube 视频，快速整理成适合本地保存和阅读的 Markdown 笔记。

`Echoflow` 是一个面向 `Typora` 工作流的命令行工具。你只需要给它一个视频链接，它会优先尝试提取现成字幕；如果拿不到字幕，就自动下载音频并做语音转录。之后你可以选择直接导出原始文本，或者进一步整理成一篇结构清晰、适合阅读的 Markdown 文稿。

## 项目特点

- 支持 `Bilibili`、`YouTube` 以及常见分享链接格式
- 支持直接输入 `BV` 号、`av` 号、YouTube 视频 ID
- 自动清洗链接，去掉常见追踪参数
- 优先使用平台字幕，降低耗时和转录成本
- 没有字幕时自动回退到 ASR 转录
- 支持导出原始转录文本 `.txt`
- 支持整理成适合 `Typora` 阅读的 Markdown 笔记
- 摘要区域使用 Typora 原生 `NOTE` alert
- 支持设置统一输出语言，例如 `中文` 或 `English`
- 提供 `yt-dlp` 更新命令，方便处理平台规则变动

## 工作流

### `echoflow run`

这是完整流程：

1. 解析并规范化输入链接
2. 用 `yt-dlp` 探测字幕轨道
3. 如果有可用字幕，直接提取并清洗字幕文本
4. 如果没有字幕，下载音频并调用 ASR 转录
5. 用大模型把转录整理成结构化 Markdown
6. 保存到本地目录

### `echoflow transcript`

这个命令只做前半段：

1. 提取字幕，或者转录音频
2. 保存原始文本为 `.txt`

它不会调用总结模型，适合只想拿到原始文本的时候使用。

## 输出效果

当前输出是为 `Typora` 直接阅读优化的，不是为 Obsidian frontmatter 工作流设计的。

生成的 Markdown 大致会长这样：

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

整理后的正文内容……
```

## 使用的服务

当前版本采用固定服务提供商设计，尽量保持 CLI 简单，不开放模型切换配置：

- 转录：`SiliconFlow` 的 `FunAudioLLM/SenseVoiceSmall`
- 整理与总结：`DeepSeek V4 Pro`

这意味着它开箱即用，但如果你想切换到别的 ASR 或 LLM，目前还不是这个项目的目标。

## 运行要求

- `Python 3.10+`
- 建议安装 `ffmpeg`
- 可用的 `SiliconFlow API Key`
- 可用的 `DeepSeek API Key`

说明：

- 如果视频自带可用字幕，通常不会走音频转录路径
- 如果需要把音频转成 `mp3`，或者源格式不适合直接处理，`ffmpeg` 会更稳

## 安装

```bash
git clone https://github.com/yihuiz106-wq/Echoflow.git
cd Echoflow

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
```

如果你移动过项目目录，导致虚拟环境里的 `echoflow` 入口失效，可以重新安装一次：

```bash
.venv/bin/python -m pip install -e . --no-deps
```

## 快速开始

### 1. 先初始化一次

```bash
echoflow init
```

配置会写入：

```bash
~/.echoflow_env
```

初始化时会让你填写：

- `SiliconFlow API Key`
- `DeepSeek API Key`
- 输出目录

### 2. 生成 Markdown 笔记

```bash
echoflow run "https://www.bilibili.com/video/BV1xxxxxx"
```

### 3. 只导出转录文本

```bash
echoflow transcript "https://www.youtube.com/watch?v=xxxxxx"
```

## 常用命令

### 跳过 mp3 转码，直接使用原始音频

```bash
echoflow run --raw "https://www.youtube.com/watch?v=xxxxxx"
echoflow transcript --raw "https://www.bilibili.com/video/BV1xxxxxx"
```

### 修改配置

```bash
echoflow config dir "/Users/me/Documents/Notes"
echoflow config sf "your-siliconflow-key"
echoflow config ds "your-deepseek-key"
```

缩写对应关系：

- `sf` -> `SILICONFLOW_API_KEY`
- `ds` -> `DEEPSEEK_API_KEY`
- `dir` -> `OUTPUT_DIR`

### 设置输出语言

```bash
echoflow language 中文
echoflow language English
```

这会影响最终整理后的笔记语言，不影响原始字幕或转录文本本身的语言。

### 更新 `yt-dlp`

```bash
echoflow update-yt-dlp
```

当视频下载、字幕提取突然异常时，通常值得先跑一次这个命令。

### 检查本地环境

```bash
echoflow doctor
```

这个命令只检查 Python 版本、依赖、`ffmpeg`、配置文件和输出目录，不会调用 DeepSeek 或 SiliconFlow API。

### 查看帮助

```bash
echoflow --help
```

## 输入兼容性

Echoflow 会尽量容忍“随手粘贴”的输入，比如：

- 完整视频链接
- Markdown 链接，如 `[标题](https://...)`
- 带文案的分享文本
- `BV` 号
- `av` 号
- 11 位 YouTube 视频 ID

它还会自动清理一部分常见追踪参数，例如 `utm_*`。

## 输出文件

### Markdown 笔记

- 默认使用视频标题作为文件名
- 自动处理重名冲突
- 包含作者、发布日期、平台、时长、生成时间和原始链接
- 摘要区使用 Typora 原生 `NOTE` alert

### 原始转录文本

- 默认保存为 `视频标题_transcript.txt`
- 只包含提取或转录后的文本
- 不做摘要，不做二次整理

## 常见问题

### 为什么有时候很快，有时候很慢？

因为它会优先尝试拿字幕，而“有字幕”和“没字幕”是两条完全不同的路径：

- 有字幕：通常很快
- 没字幕：需要下载音频、转录，再交给大模型整理

### 为什么 `transcript` 不需要 DeepSeek？

因为它只负责保存原始文本，不做总结或改写。

### 为什么 `run` 有时还是需要 SiliconFlow？

因为有些视频没有可用字幕，这时就只能回退到 ASR 转录。

### 输出目录之后还能改吗？

可以：

```bash
echoflow config dir "/new/output/path"
```

## 开发说明

CLI 入口定义在 `pyproject.toml`：

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

也可以直接运行模块：

```bash
PYTHONPATH=src .venv/bin/python -m echoflow.main --help
```
