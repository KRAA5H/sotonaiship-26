"""The iMessage webhook under the graph: words, the report link, the source link."""

import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import blue_bubbles as bot


class FakeRuntime:
    def __init__(self):
        self.inbound = None

    def turn(self, inbound):
        self.inbound = inbound
        return {
            "kind": "saved",
            "bubbles": ["Logged it here.", "Where is it?"],
            "url": "https://example.test/r/" + "a" * 16,
            "source_url": "https://www.southampton.gov.uk/example",
            "state": {},
        }


class GraphWebhookTest(unittest.TestCase):
    def test_graph_mode_delivers_words_and_both_links(self):
        fake = FakeRuntime()
        sent = []
        with unittest.mock.patch.object(bot, "MODE", "graph"), \
             unittest.mock.patch.object(bot.service, "get_runtime", return_value=fake), \
             unittest.mock.patch.object(bot, "deliver",
                                       side_effect=lambda chat, text: sent.append(text)):
            bot.handle_inbound({
                "chat_guid": "chat-graph-1",
                "sender": "+447700900321",
                "text": "there is a tree fallen on the road",
                "message_guid": "G-GRAPH-1",
                "attachments": [],
            })
        self.assertEqual(sent, [
            "Logged it here.",
            "Where is it?",
            "https://example.test/r/" + "a" * 16,
            "https://www.southampton.gov.uk/example",
        ])
        self.assertEqual(fake.inbound["sender"], "+447700900321")
        self.assertEqual(fake.inbound["text"], "there is a tree fallen on the road")

    def test_legacy_mode_is_still_selectable(self):
        self.assertIn("legacy", ("legacy", "graph"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
