# Echoflow

Turn Bilibili or YouTube videos into clean local notes from the command line.

`Echoflow` is a small CLI for people who save knowledge from videos but do not want to manually download, transcribe, clean, and rewrite everything by hand. Give it a video link, and it will try to extract subtitles first. If subtitles are not available, it falls back to audio transcription. Then it can either save the raw transcript or rewrite the content into a Markdown article that reads well in `Typora`.

## What It Does

- Accepts `Bilibili`, `YouTube`, share text, `BV` / `av` IDs, and YouTube video IDs
- Normalizes messy links before processing
- Prefers platform subtitles to reduce cost and waiting time
- Falls back to ASR automatically when subtitles are unavailable
- Saves raw transcript as `.txt`
- Rewrites transcript into a readable Markdown note with metadata and a `NOTE` summary block
- Lets you set a global output language such as `中文` or `English`
- Includes a command to update `yt-dlp` when site rules change

## Workflow

### `echoflow run`

`run` is the full pipeline:

1. Parse and normalize the input link
2. Probe subtitle tracks with `yt-dlp`
3. Use subtitles directly when available
4. Download audio and transcribe it when subtitles are missing
5. Rewrite the transcript into a structured Markdown article
6. Save the final note locally

### `echoflow transcript`

`transcript` stops earlier:

1. Extract subtitles or transcribe audio
2. Save the raw text as `.txt`

It does not call the summarization model.

## Output Style

Generated notes are designed for direct reading in `Typora`, not for Obsidian frontmatter workflows.

Example:

```md
# Video Title

> 作者：...
> 发布日期：...
> 平台：...
> 时长：...
> 生成时间：...
> 链接：https://...

> [!NOTE]
> Summary goes here.

## 正文

整理后的正文内容……
```

## Models and Services

The current design is intentionally opinionated and keeps the provider choices fixed:

- Transcription: `SiliconFlow` with `FunAudioLLM/SenseVoiceSmall`
- Rewriting / summarization: `DeepSeek V4 Pro`

This keeps the CLI simple, but it also means provider switching is not exposed as a user-facing feature right now.

## Requirements

- `Python 3.9+`
- `ffmpeg` recommended
- A valid `SiliconFlow API Key`
- A valid `DeepSeek API Key`

`ffmpeg` is especially useful when audio needs to be converted to `mp3`. If a video already has usable subtitles, the pipeline can often skip the heavier audio path.

## Installation

```bash
git clone https://github.com/yihuiz106-wq/EchoFlow.git
cd EchoFlow

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
```

If you moved the project directory and the virtualenv entrypoint breaks, reinstall the editable package once:

```bash
.venv/bin/python -m pip install -e . --no-deps
```

## Quick Start

### 1. Initialize once

```bash
echoflow init
```

This writes your configuration to:

```bash
~/.echoflow_env
```

You will be asked for:

- `SiliconFlow API Key`
- `DeepSeek API Key`
- output directory

### 2. Generate a Markdown note

```bash
echoflow run "https://www.bilibili.com/video/BV1xxxxxx"
```

### 3. Export only the transcript

```bash
echoflow transcript "https://www.youtube.com/watch?v=xxxxxx"
```

## Common Commands

### Skip mp3 conversion and use the original audio

```bash
echoflow run --raw "https://www.youtube.com/watch?v=xxxxxx"
echoflow transcript --raw "https://www.bilibili.com/video/BV1xxxxxx"
```

### Change config values

```bash
echoflow config dir "/Users/me/Documents/Notes"
echoflow config sf "your-siliconflow-key"
echoflow config ds "your-deepseek-key"
```

Short names:

- `sf` -> `SILICONFLOW_API_KEY`
- `ds` -> `DEEPSEEK_API_KEY`
- `dir` -> `OUTPUT_DIR`

### Set output language

```bash
echoflow language 中文
echoflow language English
```

This affects the final rewritten note, not the original transcript language.

### Update `yt-dlp`

```bash
echoflow update-yt-dlp
```

Useful when video download or subtitle extraction suddenly starts failing.

### Show help

```bash
echoflow --help
```

## Input Flexibility

Echoflow tries to be tolerant about what you paste in:

- full video URLs
- Markdown links like `[title](https://...)`
- share text that contains a URL
- `BV` IDs
- `av` IDs
- 11-character YouTube video IDs

It also strips some common tracking parameters such as `utm_*`.

## Output Files

### Markdown notes

- saved using the video title as filename
- auto-renamed on conflicts
- include author, publish date, platform, duration, generated time, and source link
- include a Typora-native `NOTE` summary block

### Raw transcripts

- saved as `video_title_transcript.txt`
- contain the extracted or transcribed text only

## FAQ

### Why is it fast sometimes and slow other times?

Because subtitle-first and audio-transcription are very different paths:

- subtitles available: usually much faster
- subtitles unavailable: audio must be downloaded, transcribed, then rewritten

### Why does `transcript` not need DeepSeek?

Because it only saves raw text and skips the rewrite step.

### Why might `run` still need SiliconFlow even if I mostly use subtitles?

Because some videos do not expose usable subtitles, so the command must fall back to ASR.

### Can I change the output directory later?

Yes:

```bash
echoflow config dir "/new/output/path"
```

## Development

The CLI entrypoint is defined in `pyproject.toml`:

```toml
[project.scripts]
echoflow = "echoflow.main:app"
```

Typical local development flow:

```bash
source .venv/bin/activate
pip install -e .
echoflow --help
```

Or run the module directly:

```bash
PYTHONPATH=src .venv/bin/python -m echoflow.main --help
```
