import os
import tempfile
import unittest

from echoflow.downloader import normalize_video_url
from echoflow.main import mask_config_value
from echoflow.summarizer import (
    SUMMARY_TEMPERATURE,
    build_summary_messages,
    build_summary_system_prompt,
    parse_json_description_content,
)
from echoflow.writer import (
    convert_abstract_section_to_callout,
    ensure_note_callout,
    format_duration,
    normalize_markdown_content,
    sanitize_filename,
    save_markdown,
)


class CoreBehaviorTests(unittest.TestCase):
    def test_normalize_video_url_accepts_common_inputs(self):
        self.assertEqual(
            normalize_video_url("BV1uT4y1P7CX"),
            "https://www.bilibili.com/video/BV1uT4y1P7CX",
        )
        self.assertEqual(
            normalize_video_url(
                "[demo](https://www.youtube.com/watch?v=abc123DEF45&utm_source=x&si=y)"
            ),
            "https://www.youtube.com/watch?v=abc123DEF45",
        )

    def test_markdown_callout_fallback(self):
        self.assertEqual(
            convert_abstract_section_to_callout("## 摘要\nhello\n\n## 正文\nbody"),
            "> [!NOTE]\n> hello\n\n## 正文\nbody",
        )
        self.assertEqual(
            ensure_note_callout("## 正文\nbody", "line 1\nline 2"),
            "> [!NOTE]\n> line 1\n> line 2\n\n## 正文\nbody",
        )
        self.assertEqual(
            normalize_markdown_content("## 正文\nbody\n\n\n### 小节\ntext", "简介"),
            "> [!NOTE]\n> 简介\n\n## 正文\n\nbody\n\n### 小节\n\ntext",
        )

    def test_writer_uses_description_when_content_has_no_callout(self):
        metadata = {
            "title": "A/B Test",
            "author": "Tester",
            "url": "https://example.com",
            "published": "2026-06-14",
            "source_domain": "web",
            "duration": 65,
        }
        with tempfile.TemporaryDirectory() as output_dir:
            path = save_markdown(
                metadata,
                "fallback summary",
                "## 正文\nbody",
                output_dir=output_dir,
            )
            with open(path, "r", encoding="utf-8") as f:
                saved = f.read()

        self.assertIn("# A/B Test", saved)
        self.assertIn("> [!NOTE]\n> fallback summary", saved)
        self.assertIn("时长：01:05", saved)
        self.assertTrue(os.path.basename(path).startswith("AE A_B Test"))

    def test_parsers_and_formatters(self):
        self.assertEqual(sanitize_filename('a/b:c*?'), "a_b_c__")
        self.assertEqual(format_duration(3661), "01:01:01")
        self.assertEqual(
            parse_json_description_content('{"description":"d","content":"c"}'),
            ("d", "c"),
        )
        self.assertEqual(mask_config_value("DEEPSEEK_API_KEY", "sk-123456789"), "sk-1...6789")
        self.assertEqual(mask_config_value("OUTPUT_DIR", "/tmp/out"), "/tmp/out")

    def test_summary_harness_stays_compact(self):
        prompt = build_summary_system_prompt("中文")
        self.assertIn("语音识别错误", prompt)
        self.assertIn("同音/近音词", prompt)
        self.assertIn("不要把猜测写成确定事实", prompt)
        self.assertLessEqual(len(prompt.splitlines()), 8)
        self.assertEqual(SUMMARY_TEMPERATURE, 0.45)

        messages = build_summary_messages("中文", "这是一段转录")
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("<transcript>\n这是一段转录\n</transcript>", messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
