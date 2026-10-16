"""Offline tests with a fake `claude`. Run with `python3 -m unittest`."""
import io
import json
import os
import stat
import tempfile
import unittest
from unittest import mock

import main

# Prints Claude Code's stream-json for the answer "Hello world", then the
# result line; FAKE_FAIL makes it fail like a logged-out Claude Code.
FAKE_CLAUDE = r"""#!/usr/bin/env python3
import json, os, sys
prompt = sys.stdin.read()
with open(os.environ["FAKE_LOG"], "w") as f:
    json.dump({"argv": sys.argv[1:], "prompt": prompt, "cwd": os.getcwd()}, f)
if os.environ.get("FAKE_FAIL"):
    print(json.dumps({"type": "result", "subtype": "error", "is_error": True,
                      "result": "Not logged in. Run claude to log in."}))
    sys.exit(1)
print(json.dumps({"type": "system", "subtype": "init"}))
for part in ["Hello", " world"]:
    print(json.dumps({"type": "stream_event", "event": {"type": "content_block_delta",
          "delta": {"type": "text_delta", "text": part}}}), flush=True)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                  "result": "Hello world"}))
"""


class Fake(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        path = os.path.join(self.dir.name, "claude")
        with open(path, "w") as f:
            f.write(FAKE_CLAUDE)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        self.log = os.path.join(self.dir.name, "log.json")
        env = {"PATH": f"{self.dir.name}:{os.environ['PATH']}", "FAKE_LOG": self.log}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.out = io.StringIO()
        self.plugin = main.Ask(out=self.out)
        self.plugin.init({"model": "sonnet"})
        # Every line counts as progress in tests.
        self.every = mock.patch.object(main, "PROGRESS_EVERY", 0)
        self.every.start()

    def tearDown(self):
        self.every.stop()
        self.env.stop()
        self.dir.cleanup()

    def called(self):
        with open(self.log) as f:
            return json.load(f)

    def progress(self):
        return [json.loads(l) for l in self.out.getvalue().splitlines()]


class Query(Fake):
    def test_ask_is_instant_and_slow_on_enter(self):
        [item] = self.plugin.query("ask", "undo a pushed commit", None)
        action = item["actions"][0]
        self.assertTrue(action["slow"])
        self.assertEqual(action["browse"], {"mode": "ask", "question": "undo a pushed commit"})
        self.assertFalse(os.path.exists(self.log), "a query must not call the model")

    def test_empty_ask_is_help(self):
        [item] = self.plugin.query("ask", "  ", None)
        self.assertEqual(item["actions"], [])

    def test_fix_needs_the_clipboard(self):
        [item] = self.plugin.query("fix", "", None)
        self.assertEqual(item["title"], "Copy some text first")

    def test_fix_carries_text_and_instruction(self):
        [item] = self.plugin.query("fix", "more formal", "hey can u send it")
        data = item["actions"][0]["browse"]
        self.assertEqual((data["mode"], data["instruction"], data["source"]),
                         ("fix", "more formal", "hey can u send it"))

    def test_plain_fix_uses_the_default_instruction(self):
        [item] = self.plugin.query("fix", "", "teh text")
        self.assertEqual(item["actions"][0]["browse"]["instruction"], main.DEFAULT_FIX)


class Browse(Fake):
    def test_ask_streams_then_answers_with_copy_first(self):
        [item] = self.plugin.browse({"mode": "ask", "question": "hi?"})
        self.assertEqual(item["text"], "Hello world")
        self.assertEqual([a["label"] for a in item["actions"]], ["Copy", "Paste"])
        texts = [m["items"][0]["text"] for m in self.progress()]
        self.assertEqual(texts, ["Hello", "Hello world"])
        call = self.called()
        self.assertEqual(call["prompt"], "hi?")
        self.assertIn("--no-session-persistence", call["argv"])
        self.assertEqual(call["argv"][call["argv"].index("--tools") + 1], "")
        self.assertEqual(call["argv"][call["argv"].index("--model") + 1], "sonnet")
        self.assertTrue(call["cwd"].endswith("parsec-ask"))

    def test_fix_pastes_first_and_wraps_the_text(self):
        [item] = self.plugin.browse({"mode": "fix", "instruction": "shorter", "source": "long text"})
        self.assertEqual([a["label"] for a in item["actions"]], ["Paste", "Copy"])
        self.assertEqual(item["actions"][0]["paste"], "Hello world")
        prompt = self.called()["prompt"]
        self.assertIn("Instruction: shorter", prompt)
        self.assertIn("<text>\nlong text\n</text>", prompt)

    def test_failure_becomes_a_readable_row(self):
        with mock.patch.dict(os.environ, {"FAKE_FAIL": "1"}):
            [item] = self.plugin.browse({"mode": "ask", "question": "hi?"})
        self.assertIn("didn't answer", item["title"])
        self.assertIn("Not logged in", item["text"])

    def test_missing_claude(self):
        with mock.patch.object(main, "find_claude", return_value=None):
            [item] = self.plugin.browse({"mode": "ask", "question": "hi?"})
        self.assertIn("isn't installed", item["text"])

    def test_any_command_streams_its_stdout(self):
        self.plugin.init({"command": ["sh", "-c", "tr a-z A-Z"]})
        [item] = self.plugin.browse({"mode": "ask", "question": "hi"})
        self.assertTrue(item["text"].endswith("HI"))
        self.assertTrue(item["text"].startswith("YOU ANSWER"), "system prompt goes first")

    def test_junk_data_is_ignored(self):
        self.assertEqual(self.plugin.browse({"mode": "ask"}), [])
        self.assertEqual(self.plugin.browse("nope"), [])


class Stream(unittest.TestCase):
    def test_result_wins_over_deltas(self):
        s = main.ClaudeStream()
        s.feed(json.dumps({"type": "stream_event", "event": {
            "type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hel"}}}))
        s.feed(json.dumps({"type": "result", "is_error": False, "result": "Hello"}))
        self.assertEqual(s.answer(), "Hello")

    def test_thinking_and_junk_are_skipped(self):
        s = main.ClaudeStream()
        self.assertFalse(s.feed("not json"))
        self.assertFalse(s.feed(json.dumps({"type": "stream_event", "event": {
            "type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "hm"}}})))
        self.assertEqual(s.answer(), "")


if __name__ == "__main__":
    unittest.main()
