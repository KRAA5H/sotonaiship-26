"""Tests for the model payload: text never thinks, images must.

No network. Run: python code/test_llm.py
"""

import os
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm  # noqa: E402


class PayloadTest(unittest.TestCase):
    def setUp(self):
        patcher = unittest.mock.patch.dict(
            os.environ, {"DEEPSEEK_API_KEY": "test-key", "LLM_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _text_candidate(self):
        return llm._candidates(None)[0]

    def _image_candidate(self):
        return llm._candidates((b"png", "image/png"))[0]

    def test_text_turns_thinking_off(self):
        payload = llm._payload("system", "user", None, self._text_candidate())
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertNotIn("reasoning", payload)

    def test_an_image_keeps_the_reasoning_object(self):
        payload = llm._payload("system", "user", (b"png", "image/png"),
                               self._image_candidate())
        self.assertEqual(payload["reasoning"], {"effort": "low"})
        self.assertNotIn("thinking", payload)

    def test_text_can_use_a_short_budget_now(self):
        payload = llm._payload("system", "user", None, self._text_candidate(),
                               max_tokens=120)
        self.assertEqual(payload["max_tokens"], 120)

    def test_an_image_keeps_a_floor_so_the_reply_is_not_empty(self):
        payload = llm._payload("system", "user", (b"png", "image/png"),
                               self._image_candidate(), max_tokens=100)
        self.assertGreaterEqual(payload["max_tokens"], 400)

    def test_temperature_still_reaches_the_payload(self):
        payload = llm._payload("system", "user", None, self._text_candidate(),
                               temperature=0.9)
        self.assertEqual(payload["temperature"], 0.9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
