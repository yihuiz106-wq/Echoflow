import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from echoflow.downloader import DownloadResult, download_audio, resolve_audio_path
from echoflow.errors import ConfigError, DownloadError, SummaryError, TranscriptionError, WriteError
from echoflow.main import fetch_transcript, format_cli_error
from echoflow.retry import call_with_retry
from echoflow.summarizer import generate_summary
from echoflow.transcriber import transcribe_audio
from echoflow.writer import save_markdown


class FakeYoutubeDL:
    calls = []
    queue = []

    def __init__(self, opts):
        self.opts = opts
        FakeYoutubeDL.calls.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def extract_info(self, url, download=True):
        if not FakeYoutubeDL.queue:
            raise AssertionError("No fake yt-dlp response queued")

        item = FakeYoutubeDL.queue.pop(0)
        if isinstance(item, Exception):
            raise item

        info = dict(item)
        if download and self.opts.get("writesubtitles"):
            filename = self.prepare_filename(info)
            subtitle_path = Path(os.path.splitext(filename)[0] + ".zh.vtt")
            subtitle_path.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n", encoding="utf-8")
        if download and not self.opts.get("skip_download"):
            filename = self.prepare_filename(info)
            audio_path = Path(filename).with_suffix(".mp3")
            audio_path.write_bytes(b"audio")

        return info

    def prepare_filename(self, info):
        tmpl = self.opts["outtmpl"]
        return tmpl.replace("%(id)s", info.get("id", "video")).replace("%(ext)s", info.get("ext", "webm"))


def queue_yt_dlp(*items):
    FakeYoutubeDL.calls = []
    FakeYoutubeDL.queue = list(items)


class StabilityTests(unittest.TestCase):
    def test_download_subtitle_success_returns_result_and_cleanup_removes_temp_dir(self):
        queue_yt_dlp(
            {
                "id": "v1",
                "title": "Title",
                "webpage_url": "https://www.youtube.com/watch?v=abc123DEF45",
                "subtitles": {"zh": [{}]},
            },
            {
                "id": "v1",
                "title": "Title",
                "webpage_url": "https://www.youtube.com/watch?v=abc123DEF45",
                "subtitles": {"zh": [{}]},
            },
        )

        with patch("echoflow.downloader.yt_dlp.YoutubeDL", FakeYoutubeDL):
            result = download_audio("abc123DEF45", allow_audio_download=False)

        self.assertIsInstance(result, DownloadResult)
        self.assertEqual(result.source, "subtitle")
        self.assertEqual(result.subtitle_text, "hello")
        self.assertIsNone(result.audio_path)
        self.assertTrue(result.temp_dir.exists())

        result.cleanup()
        self.assertFalse(result.temp_dir.exists())

    def test_no_subtitle_without_asr_key_fails_before_audio_download_and_cleans_temp_dir(self):
        queue_yt_dlp(
            {
                "id": "v2",
                "title": "No Subtitle",
                "webpage_url": "https://www.youtube.com/watch?v=abc123DEF45",
                "subtitles": {},
                "automatic_captions": {},
            }
        )

        with patch("echoflow.downloader.yt_dlp.YoutubeDL", FakeYoutubeDL):
            with self.assertRaises(ConfigError):
                download_audio("abc123DEF45", allow_audio_download=False)

        self.assertEqual(len(FakeYoutubeDL.calls), 1)
        temp_dir = Path(FakeYoutubeDL.calls[0]["outtmpl"]).parent
        self.assertFalse(temp_dir.exists())

    def test_subtitle_429_falls_back_to_audio(self):
        queue_yt_dlp(
            Exception("subtitles 429 too many requests"),
            {
                "id": "v3",
                "title": "Audio",
                "webpage_url": "https://www.youtube.com/watch?v=abc123DEF45",
                "ext": "webm",
            },
        )

        with patch("echoflow.downloader.yt_dlp.YoutubeDL", FakeYoutubeDL):
            result = download_audio("abc123DEF45", allow_audio_download=True)

        self.assertEqual(result.source, "audio")
        self.assertTrue(result.audio_path.endswith(".mp3"))
        self.assertTrue(Path(result.audio_path).exists())
        result.cleanup()
        self.assertFalse(result.temp_dir.exists())

    def test_resolve_audio_path_uses_existing_container_when_mp3_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            prepared = temp_dir / "video.webm"
            prepared.write_bytes(b"audio")

            resolved = resolve_audio_path(str(prepared), temp_dir, convert_audio=True)

        self.assertEqual(resolved, prepared)

    def test_resolve_audio_path_errors_when_no_audio_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            (temp_dir / "video.info.json").write_text("{}", encoding="utf-8")

            with self.assertRaises(DownloadError):
                resolve_audio_path(str(temp_dir / "video.webm"), temp_dir, convert_audio=True)

    def test_bilibili_412_retries_with_browser_cookie(self):
        queue_yt_dlp(
            Exception("[Bilibili] 412 Precondition Failed"),
            {
                "id": "bv1",
                "title": "Bili",
                "webpage_url": "https://www.bilibili.com/video/BV1uT4y1P7CX",
                "subtitles": {"zh": [{}]},
            },
            {
                "id": "bv1",
                "title": "Bili",
                "webpage_url": "https://www.bilibili.com/video/BV1uT4y1P7CX",
                "subtitles": {"zh": [{}]},
            },
        )

        with patch.dict(os.environ, {"BILIBILI_COOKIES_FROM_BROWSER": "chrome"}, clear=False):
            with patch("echoflow.downloader.yt_dlp.YoutubeDL", FakeYoutubeDL):
                result = download_audio("https://www.bilibili.com/video/BV1uT4y1P7CX", allow_audio_download=False)

        self.assertEqual(result.source, "subtitle")
        self.assertTrue(any(opts.get("cookiesfrombrowser") for opts in FakeYoutubeDL.calls))
        result.cleanup()

    def test_non_subtitle_probe_error_is_download_error(self):
        queue_yt_dlp(Exception("unsupported url"))

        with patch("echoflow.downloader.yt_dlp.YoutubeDL", FakeYoutubeDL):
            with self.assertRaises(DownloadError):
                download_audio("abc123DEF45", allow_audio_download=True)

        temp_dir = Path(FakeYoutubeDL.calls[0]["outtmpl"]).parent
        self.assertFalse(temp_dir.exists())

    def test_retry_only_retries_transient_errors(self):
        attempts = {"count": 0}

        class FakeRateLimitError(Exception):
            status_code = 429

        def transient_operation():
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise FakeRateLimitError("rate limited")
            return "ok"

        self.assertEqual(call_with_retry(transient_operation), "ok")
        self.assertEqual(attempts["count"], 2)

        attempts["count"] = 0

        def permanent_operation():
            attempts["count"] += 1
            raise ValueError("bad request")

        with self.assertRaises(ValueError):
            call_with_retry(permanent_operation)
        self.assertEqual(attempts["count"], 1)

    def test_writer_raises_typed_error_without_printing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "not-a-dir"
            output_file.write_text("occupied", encoding="utf-8")

            with patch("builtins.print") as print_mock:
                with self.assertRaises(WriteError):
                    save_markdown(
                        {"title": "Title"},
                        "summary",
                        "## Body\ntext",
                        output_dir=str(output_file),
                    )

        print_mock.assert_not_called()

    def test_summary_retries_transient_openai_error(self):
        calls = {"count": 0}

        class FakeRateLimitError(Exception):
            status_code = 429

        class FakeChatCompletions:
            def create(self, **kwargs):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise FakeRateLimitError("rate limited")
                message = SimpleNamespace(content='{"description":"desc","content":"## Body\\ntext"}')
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=FakeChatCompletions())
        )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "key"}, clear=False):
            with patch("echoflow.summarizer.OpenAI", return_value=fake_client):
                description, content = generate_summary("transcript")

        self.assertEqual((description, content), ("desc", "## Body\ntext"))
        self.assertEqual(calls["count"], 2)

    def test_summary_does_not_retry_permanent_openai_error(self):
        calls = {"count": 0}

        class FakeBadRequestError(Exception):
            status_code = 400

        class FakeChatCompletions:
            def create(self, **kwargs):
                calls["count"] += 1
                raise FakeBadRequestError("bad request")

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=FakeChatCompletions())
        )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "key"}, clear=False):
            with patch("echoflow.summarizer.OpenAI", return_value=fake_client):
                with self.assertRaises(SummaryError):
                    generate_summary("transcript")

        self.assertEqual(calls["count"], 1)

    def test_transcriber_retries_transient_openai_error(self):
        calls = {"count": 0}

        class FakeTimeoutError(Exception):
            pass

        FakeTimeoutError.__name__ = "APITimeoutError"

        class FakeTranscriptions:
            def create(self, **kwargs):
                calls["count"] += 1
                if kwargs["file"].tell() != 0:
                    raise AssertionError("audio file was not rewound before retry")
                if calls["count"] == 1:
                    kwargs["file"].read()
                    raise FakeTimeoutError("timed out")
                return SimpleNamespace(text="transcript")

        fake_client = SimpleNamespace(
            audio=SimpleNamespace(transcriptions=FakeTranscriptions())
        )

        with tempfile.NamedTemporaryFile() as audio:
            audio.write(b"audio")
            audio.flush()
            with patch.dict(os.environ, {"SILICONFLOW_API_KEY": "key"}, clear=False):
                with patch("echoflow.transcriber.OpenAI", return_value=fake_client):
                    self.assertEqual(transcribe_audio(audio.name), "transcript")

        self.assertEqual(calls["count"], 2)

    def test_transcriber_wraps_permanent_openai_error(self):
        calls = {"count": 0}

        class FakeUnauthorizedError(Exception):
            status_code = 401

        class FakeTranscriptions:
            def create(self, **kwargs):
                calls["count"] += 1
                raise FakeUnauthorizedError("unauthorized")

        fake_client = SimpleNamespace(
            audio=SimpleNamespace(transcriptions=FakeTranscriptions())
        )

        with tempfile.NamedTemporaryFile() as audio:
            audio.write(b"audio")
            audio.flush()
            with patch.dict(os.environ, {"SILICONFLOW_API_KEY": "key"}, clear=False):
                with patch("echoflow.transcriber.OpenAI", return_value=fake_client):
                    with self.assertRaises(TranscriptionError):
                        transcribe_audio(audio.name)

        self.assertEqual(calls["count"], 1)

    def test_cli_error_messages_are_specific(self):
        message, hint = format_cli_error(ConfigError("missing key"))
        self.assertEqual(message, "missing key")
        self.assertIn("echoflow init", hint)

        message, hint = format_cli_error(DownloadError("[Bilibili] 412 Precondition Failed"))
        self.assertIn("412", message)
        self.assertIn("Cookie", hint)

        message, hint = format_cli_error(SummaryError("DeepSeek failed"))
        self.assertIn("DeepSeek failed", message)
        self.assertIn("DeepSeek", hint)

    def test_fetch_transcript_cleans_download_result(self):
        temp_dir = Path(tempfile.mkdtemp())
        result = DownloadResult(
            audio_path=None,
            subtitle_text="subtitle text",
            metadata={"title": "Title"},
            source="subtitle",
            temp_dir=temp_dir,
        )

        with patch("echoflow.main.config.load_config", return_value=False):
            with patch("echoflow.main.download_audio", return_value=result):
                with patch("echoflow.main.print_video_title"):
                    with patch("echoflow.main.print_success"):
                        metadata, transcript = fetch_transcript("abc123DEF45")

        self.assertEqual(metadata["title"], "Title")
        self.assertEqual(transcript, "subtitle text")
        self.assertFalse(temp_dir.exists())


if __name__ == "__main__":
    unittest.main()
