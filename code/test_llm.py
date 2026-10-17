"""Tests for the model layer: DeepSeek never thinks, except an image that came back empty.

No network: requests.post is replaced. Run: python code/test_llm.py
"""

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm  # noqa: E402

IMAGE = (b"png", "image/png")


class FakeResponse:
    def __init__(self, content="", status=200, usage=None):
        self.status_code = status
        self.text = "body"
        self._data = {"choices": [{"message": {"content": content, "reasoning_content": "secret thoughts"}}],
                      "usage": usage or {"prompt_tokens": 120, "completion_tokens": 30,
                                         "prompt_cache_hit_tokens": 100}}

    def json(self):
        return self._data


class Case(unittest.TestCase):
    def setUp(self):
        env = unittest.mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key", "LLM_API_KEY": ""})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        log = unittest.mock.patch.object(llm, "USAGE_LOG", Path(self.tmp.name) / "usage.jsonl")
        log.start()
        self.addCleanup(log.stop)
        sleep = unittest.mock.patch.object(llm.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def post(self, *responses):
        replies = list(responses)
        calls = []

        def fake(url, headers=None, json=None, timeout=None):
            calls.append({"url": url, "json": json, "timeout": timeout})
            value = replies.pop(0) if len(replies) > 1 else replies[0]
            if isinstance(value, Exception):
                raise value
            return value

        fake.calls = calls
        return unittest.mock.patch.object(llm.requests, "post", side_effect=fake), calls


class PayloadTest(Case):
    def test_text_turns_thinking_off(self):
        payload = llm._payload("system", "user", None, llm._candidates(None)[0])
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertNotIn("reasoning", payload)
        self.assertNotIn("reasoning_effort", payload)

    def test_an_image_turns_thinking_off_first(self):
        first = llm._candidates(IMAGE)[0]
        payload = llm._payload("system", "user", IMAGE, first)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["messages"][1]["content"][1]["type"], "image_url")

    def test_the_empty_image_retry_is_the_only_thinking_deepseek_call(self):
        thinking = [c for c in llm._candidates(IMAGE) + llm._candidates(None)
                    if c["provider"] == "deepseek" and c["thinking"]]
        self.assertEqual(len(thinking), 1)
        self.assertTrue(thinking[0]["only_after_empty"])
        payload = llm._payload("system", "user", IMAGE, thinking[0], max_tokens=100)
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertGreaterEqual(payload["max_tokens"], 600)

    def test_text_can_use_a_short_budget(self):
        payload = llm._payload("system", "user", None, llm._candidates(None)[0], max_tokens=120)
        self.assertEqual(payload["max_tokens"], 120)

    def test_temperature_reaches_the_payload(self):
        payload = llm._payload("system", "user", None, llm._candidates(None)[0], temperature=0.9)
        self.assertEqual(payload["temperature"], 0.9)


class ChatTest(Case):
    def test_text_answer_and_never_the_reasoning(self):
        patch, calls = self.post(FakeResponse('{"ok": true}'))
        with patch:
            text, mode = llm.chat("system", "user", purpose="triage", timeout=4)
        self.assertEqual((text, mode), ('{"ok": true}', "model"))
        self.assertNotIn("secret", text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["json"]["thinking"], {"type": "disabled"})
        self.assertEqual(calls[0]["timeout"], 4)

    def test_an_image_answered_with_thinking_off_needs_one_call(self):
        patch, calls = self.post(FakeResponse('{"what": "a hole"}'))
        with patch:
            text, mode = llm.chat("system", "user", IMAGE)
        self.assertEqual(mode, "model")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["json"]["thinking"], {"type": "disabled"})

    def test_an_empty_image_retries_once_with_low_thinking(self):
        patch, calls = self.post(FakeResponse(""), FakeResponse('{"what": "a hole"}'))
        with patch:
            text, mode = llm.chat("system", "user", IMAGE)
        self.assertEqual((text, mode), ('{"what": "a hole"}', "model"))
        self.assertEqual([c["json"]["thinking"]["type"] for c in calls], ["disabled", "enabled"])

    def test_a_timeout_moves_on_instead_of_waiting_again(self):
        patch, calls = self.post(llm.requests.Timeout("slow"), FakeResponse("from the fallback"))
        with patch:
            text, mode = llm.chat("system", "user")
        self.assertEqual(text, "from the fallback")
        self.assertEqual([c["json"]["model"] for c in calls], [llm.DS_MODEL, "deepseek-v4-pro"])

    def test_no_provider_gives_the_stub(self):
        with unittest.mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "LLM_API_KEY": ""}):
            self.assertEqual(llm.chat("s", "u"), (llm.STUB_REPLY, "fallback"))
            self.assertEqual(llm.chat("s", "u", IMAGE), (llm.PHOTO_FALLBACK, "fallback"))


class UsageLogTest(Case):
    def test_every_call_is_logged_with_tokens_and_never_the_text(self):
        patch, _ = self.post(FakeResponse("a private reply about 12 Lawn Road"))
        with patch:
            llm.chat("system", "my neighbour at 12 Lawn Road", purpose="reply")
        lines = [json.loads(line) for line in llm.USAGE_LOG.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual((line["purpose"], line["model"], line["thinking"]), ("reply", llm.DS_MODEL, False))
        self.assertEqual((line["prompt_tokens"], line["completion_tokens"], line["cache_hit_tokens"]),
                         (120, 30, 100))
        raw = llm.USAGE_LOG.read_text(encoding="utf-8")
        self.assertNotIn("Lawn Road", raw)
        self.assertNotIn("neighbour", raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
